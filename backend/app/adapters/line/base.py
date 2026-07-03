"""LINE adapter Protocol + HMAC-SHA256 sign/verify helpers + outbound transforms.

LINE's webhook auth scheme: a header `X-Line-Signature`` carries a
base64(HMAC-SHA256(channel_secret, raw_request_body)). Verifying the
signature against the raw bytes (BEFORE JSON parsing) is the single
thing that prevents spoofed events.

Outbound transforms (``strip_markdown``, ``split_for_line``) are shared
between mock and real adapters. LINE cannot render Markdown and caps
each bubble at 5000 chars + 5 messages per Reply/Push call.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from typing import Protocol, runtime_checkable

SIGNATURE_HEADER = "X-Line-Signature"
WEBHOOK_BODY_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB — memory-exhaustion guard

# LINE Messaging API limits (https://developers.line.biz/en/reference/messaging-api/).
LINE_MAX_MESSAGES_PER_CALL = 5
LINE_SAFE_BUBBLE_CHARS = 4500  # leave margin under the 5000 hard cap

# Reply-token lifetime per LINE docs — about 60s. Shared between mock
# and real so the cache TTL is consistent.
REPLY_TOKEN_TTL_SECONDS = 60


def sign_line_webhook(body: bytes, channel_secret: str) -> str:
    """base64(HMAC-SHA256(secret, body)) — what LINE itself produces."""
    digest = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_line_webhook(body: bytes, signature: str | None, channel_secret: str) -> bool:
    """Constant-time compare. Returns False on any mismatch or missing signature."""
    if not isinstance(signature, str) or not signature:
        return False
    expected = sign_line_webhook(body, channel_secret)
    try:
        return hmac.compare_digest(expected.encode("ascii"), signature.encode("ascii"))
    except (UnicodeDecodeError, AttributeError):
        return False


# ─── Outbound transforms (used by both mock and real adapters) ─────────
_MD_HEADING = re.compile(r"^#{1,6}\s+", flags=re.MULTILINE)
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*", flags=re.DOTALL)
_MD_ITALIC_STAR = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", flags=re.DOTALL)
_MD_BOLD_UNDER = re.compile(r"__(.+?)__", flags=re.DOTALL)
_MD_ITALIC_UNDER = re.compile(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", flags=re.DOTALL)
_MD_CODE_FENCE = re.compile(r"```([\s\S]*?)```")
_MD_CODE_INLINE = re.compile(r"`([^`\n]+)`")
_MD_BULLET = re.compile(r"^\s*[-*+]\s+", flags=re.MULTILINE)
_MD_BLOCKQUOTE = re.compile(r"^\s*>\s?", flags=re.MULTILINE)


def strip_markdown(text: str) -> str:
    """Strip the Markdown marks LINE cannot render. URLs are preserved as-is.

    LINE renders a small subset of formatting on iOS/Android clients but
    not consistently across the web/desktop/macOS clients. To be safe,
    we strip the marks and keep the text. Bare URLs render as tappable
    links automatically.

    Strips: ATX headings, **bold**, *italic* (and __/underscore__), `code`,
    code fences, leading list bullets, leading blockquote markers.
    Does not touch: line breaks, tables, links (we leave the URL bare).
    """
    text = _MD_CODE_FENCE.sub(lambda m: m.group(1).strip("\n"), text)
    text = _MD_CODE_INLINE.sub(r"\1", text)
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_BOLD_UNDER.sub(r"\1", text)
    text = _MD_ITALIC_STAR.sub(r"\1", text)
    text = _MD_ITALIC_UNDER.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BULLET.sub("", text)
    text = _MD_BLOCKQUOTE.sub("", text)
    return text.strip()


def split_for_line(text: str, *, max_chars: int = LINE_SAFE_BUBBLE_CHARS) -> list[str]:
    """Split ``text`` into at most ``LINE_MAX_MESSAGES_PER_CALL`` chunks.

    Strategy: prefer paragraph boundaries; on overflow within a
    paragraph, prefer sentence boundaries (period, Thai ``。``); if a
    single sentence is still over ``max_chars``, hard-cut. The caller
    should treat the truncated remainder as lost — we never return more
    than the LINE API allows.
    """
    text = text or ""
    if len(text) <= max_chars:
        return [text]

    # First pass: paragraph boundaries.
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        candidate = (current + "\n\n" + p).strip() if current else p.strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # Paragraph too big — push it through the sentence splitter.
            chunks.extend(_split_long(p.strip(), max_chars))
            current = ""
    if current:
        chunks.append(current)

    return chunks[:LINE_MAX_MESSAGES_PER_CALL]


def _split_long(text: str, max_chars: int) -> list[str]:
    """Sentence-or-hard-cut splitter for a single over-long paragraph."""
    out: list[str] = []
    rest = text
    while len(rest) > max_chars and len(out) < LINE_MAX_MESSAGES_PER_CALL:
        window = rest[:max_chars]
        # Prefer sentence terminators (Western ``. `` + Thai ``。``).
        boundary = max(window.rfind(". "), window.rfind("。"))
        if boundary == -1 or boundary < max_chars // 2:
            # No good sentence boundary — hard cut.
            boundary = max_chars - 1
        out.append(rest[: boundary + 1].strip())
        rest = rest[boundary + 1 :].strip()
    if rest and len(out) < LINE_MAX_MESSAGES_PER_CALL:
        out.append(rest)
    return out


@runtime_checkable
class LineAdapter(Protocol):
    """LINE messaging adapter — mock + real.

    Concrete implementations live in ``mock.py`` and ``real.py``. Every
    router depends on this Protocol only — never on a concrete class.
    """

    @property
    def channel_secret(self) -> str: ...

    @property
    def bot_user_id(self) -> str | None:
        """Own channel's LINE userId.

        Used to filter self-echoes: when the bot userId is known,
        ``send_reply(line_user_id, text)`` short-circuits if
        ``line_user_id == bot_user_id`` (prevents infinite loops). The
        mock returns None (no echo filter); the real adapter populates
        this from ``GET /v2/bot/info`` when wiring lands.
        """
        ...

    def sign(self, body: bytes) -> str:
        """Sign `body` with the channel secret. Used by tests/dev tooling."""
        ...

    def verify(self, body: bytes, signature: str) -> bool:
        """Verify a request signature. Returns False on any mismatch."""
        ...

    def set_reply_token(
        self, chat_id: str, token: str, *, ttl_seconds: int = REPLY_TOKEN_TTL_SECONDS
    ) -> None:
        """Cache a Reply token off an inbound ``message`` event.

        The Reply API is free; Push is metered. Inbound webhook
        dispatchers call this when an event has a ``replyToken`` so
        ``send_reply`` can later try the Reply path first and fall
        back to Push if missing/expired.

        ``chat_id`` is the LINE chat identifier (userId for DMs,
        groupId/roomId for groups/rooms). For our MVP single-tenant
        setup it's always the userId.
        """
        ...

    def send_reply(self, line_user_id: str, text: str) -> dict[str, object]:
        """Send a reply to a LINE user.

        Mock records the call (after applying ``strip_markdown`` /
        ``split_for_line`` for parity with the real adapter's outgoing
        shape). Real calls LINE's Reply API (preferring the cached
        ``replyToken``) and falls back to Push.

        Self-message filter: when ``bot_user_id`` is set and
        ``line_user_id == bot_user_id``, returns
        ``{"skipped": "self-message", ...}`` instead of sending.
        """
        ...
