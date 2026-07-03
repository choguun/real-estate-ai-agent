"""Real LINE Messaging API adapter — stub for MVP.

Wires to the LINE Messaging API when the user provides credentials.
For Month-1 MVP, every method that would actually hit the network
raises ``NotImplementedError`` so the test suite stays offline.

The structural pieces (bot user-id cache, reply-token cache,
self-message filter) live here as the bones that the eventual
``httpx`` wiring will need. They are exercised by
``tests/test_line_helpers.py::TestLineRealAdapterStructure``; the mock
maintains the same surface so routers can call these methods
blindly. Outbound transforms (``strip_markdown``, ``split_for_line``)
live in ``base.py`` — both adapters import them.
"""

from __future__ import annotations

import time

from app.adapters.line.base import (
    REPLY_TOKEN_TTL_SECONDS,
    sign_line_webhook,
    verify_line_webhook,
)


class LineRealAdapter:
    def __init__(
        self,
        channel_secret: str,
        channel_access_token: str,
        *,
        bot_user_id: str | None = None,
        api_base: str = "https://api.line.me",
    ) -> None:
        self._secret = channel_secret
        self._token = channel_access_token
        self._api_base = api_base

        # Self-message filter — when real HTTP is wired, the adapter
        # calls ``get_bot_user_id()`` at register-time to learn its own
        # userId and ignore outbound echoes. Until then, callers can
        # pass ``bot_user_id`` explicitly via __init__.
        self._bot_user_id = bot_user_id

        # Reply-token cache: chat_id → (token, expires_at_epoch).
        # Inbound events call ``set_reply_token(chat_id, token)`` and
        # ``send_reply`` consumes the entry when it actually uses the
        # Reply API. Tokens are single-use and expire in ~60s.
        self._reply_tokens: dict[str, tuple[str, float]] = {}

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

    # ─── Reply-token plumbing (consumed by future wiring) ────────────
    def set_reply_token(
        self, chat_id: str, token: str, *, ttl_seconds: int = REPLY_TOKEN_TTL_SECONDS
    ) -> None:
        """Cache a Reply token off an inbound ``message`` event.

        Line's Reply API is free; Push is metered. The dispatcher in
        ``routers/line_webhook`` calls this when a real webhook is
        wired, and ``send_reply`` consumes the entry on the Reply path.
        """
        self._reply_tokens[chat_id] = (token, time.time() + ttl_seconds)

    def consume_reply_token(self, chat_id: str) -> tuple[str | None, bool]:
        """Pop a stashed Reply token if present and unexpired.

        Returns ``(token, used_reply)``. ``used_reply`` is False on
        token-missing or token-expired; the caller falls back to Push.
        """
        entry = self._reply_tokens.pop(chat_id, None)
        if not entry:
            return None, False
        token, expires_at = entry
        if not token or time.time() >= expires_at:
            return None, False
        return token, True

    def send_reply(self, line_user_id: str, text: str) -> dict[str, object]:
        """Send a reply to a LINE user.

        When the real adapter is wired (post-MVP), the call site is
        expected to:

        1. Run the self-message filter (``line_user_id == self._bot_user_id``).
        2. Apply outbound transforms: ``strip_markdown(text)`` then
           ``split_for_line(...)`` — LINE can't render Markdown and
           caps each bubble at 5 messages × 4500 chars.
        3. Try Reply via the cached reply-token (free). On
           missing-or-rejected, fall back to Push (metered).

        The mock records both code paths. The real adapter raises
        NotImplementedError until httpx wiring ships.
        """
        import uuid as _uuid

        # Self-message filter — would short-circuit when wired.
        if self._bot_user_id is not None and line_user_id == self._bot_user_id:
            return {
                "id": f"reply-{_uuid.uuid4().hex[:12]}",
                "line_user_id": line_user_id,
                "skipped": "self-message",
            }

        # The line below is the path real wiring will execute. Until then,
        # raise so callers know the stub is intentional.
        raise NotImplementedError(
            "LineRealAdapter.send_reply is not wired in MVP. "
            "Set use_real_line=false to use mocks. Real wiring will: "
            "(1) strip_markdown(text), (2) split_for_line(text), "
            "(3) consume_reply_token(chat_id), (4) Reply if token else Push."
        )
