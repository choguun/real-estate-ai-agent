"""In-memory LINE adapter.

The mock applies the same outbound transforms (``strip_markdown`` +
``split_for_line``) that the real adapter will apply when wired. This
keeps mock ↔ real parity on the recorded text — tests can assert on
``mock.sent_replies[-1].text`` as the "what LINE would receive" value.

Sign + verify work identically to a real client; the mock also keeps
sent-reply + reply-token logs so tests can inspect outbound state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.adapters.line.base import (
    REPLY_TOKEN_TTL_SECONDS,
    sign_line_webhook,
    split_for_line,
    strip_markdown,
    verify_line_webhook,
)


@dataclass
class _SentReply:
    line_user_id: str
    text: str
    sent_at: str
    chunk_index: int  # 0-based; -1 for "skipped" replies


class LineMockAdapter:
    def __init__(self, channel_secret: str, *, bot_user_id: str | None = None) -> None:
        self._secret = channel_secret
        self.received_events: list[dict[str, object]] = []
        self.sent_replies: list[_SentReply] = []
        # Reply-token cache — keyed by chat_id, with a TTL. Used by the
        # mock to exercise the same Reply-token flow the real adapter
        # will use. Tests can inspect via ``cached_reply_tokens``.
        self._reply_tokens: dict[str, tuple[str, float]] = {}
        self._bot_user_id = bot_user_id

    @property
    def channel_secret(self) -> str:
        return self._secret

    @property
    def bot_user_id(self) -> str | None:
        return self._bot_user_id

    def sign(self, body: bytes) -> str:
        return sign_line_webhook(body, self._secret)

    def verify(self, body: bytes, signature: str) -> bool:
        return verify_line_webhook(body, signature, self._secret)

    def set_reply_token(
        self, chat_id: str, token: str, *, ttl_seconds: int = REPLY_TOKEN_TTL_SECONDS
    ) -> None:
        """Cache a Reply token off an inbound ``message`` event.

        Mirrors ``LineRealAdapter.set_reply_token`` so the webhook
        dispatcher can call the method blindly. The cache is in-process
        and best-effort — production wiring would persist to DB.
        """
        import time

        self._reply_tokens[chat_id] = (token, time.time() + ttl_seconds)

    def cached_reply_tokens(self) -> dict[str, str]:
        """Snapshot of the current cache, key → token (for tests)."""
        return {chat_id: token for chat_id, (token, _exp) in self._reply_tokens.items()}

    def send_reply(self, line_user_id: str, text: str) -> dict[str, object]:
        """Record a sent reply after applying the outbound transforms.

        Real adapter will do the same ``strip_markdown`` + ``split_for_line``
        + Reply-or-Push flow when wired. For mock↔real parity on the
        recorded text we apply the same transforms here.

        Self-message filter: when ``bot_user_id`` is set and the reply
        is to that userId, records a single ``skipped='self-message'``
        entry and returns early (no Reply, no Push). Real adapter
        behaves the same way.
        """
        sent_at = datetime.now(timezone.utc).isoformat()

        # Self-message filter — same path as the real adapter's stub.
        if self._bot_user_id is not None and line_user_id == self._bot_user_id:
            sent = _SentReply(
                line_user_id=line_user_id,
                text="",
                sent_at=sent_at,
                chunk_index=-1,
            )
            self.sent_replies.append(sent)
            return {
                "id": f"reply-skipped-{uuid.uuid4().hex[:8]}",
                "line_user_id": line_user_id,
                "sent_at": sent_at,
                "skipped": "self-message",
            }

        # Apply the same outbound transforms the real adapter will.
        cleaned = strip_markdown(text)
        chunks = split_for_line(cleaned)

        # Reply-token routing: tokens are single-use. The mock consumes
        # on use (so the second send falls back to push), matching the
        # real adapter's behaviour. The real adapter's send_reply
        # will call ``consume_reply_token(chat_id)`` then either Reply
        # (if a usable token remains) or fall back to Push.
        if self._reply_tokens.get(line_user_id):
            # Token present — record as 'reply' and consume (single-use).
            self._reply_tokens.pop(line_user_id, None)
            mode = "reply"
        else:
            mode = "push"

        sent_ids: list[str] = []
        for i, chunk in enumerate(chunks):
            reply_id = uuid.uuid4().hex[:12]
            self.sent_replies.append(
                _SentReply(
                    line_user_id=line_user_id,
                    text=chunk,
                    sent_at=sent_at,
                    chunk_index=i,
                )
            )
            sent_ids.append(reply_id)
        return {
            "id": f"reply-{sent_ids[0]}" if sent_ids else f"reply-empty-{uuid.uuid4().hex[:8]}",
            "line_user_id": line_user_id,
            "sent_at": sent_at,
            "mode": mode,
            "chunks": sent_ids,
        }
