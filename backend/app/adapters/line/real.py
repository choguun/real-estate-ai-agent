"""Real LINE Messaging API adapter.

Wires to the LINE Reply API (free, single-bubble-or-multi) and falls
back to Push (metered) when no reply token is cached. All outbound text
goes through ``strip_markdown`` (LINE can't render Markdown reliably
across iOS/Android/web/macOS) and ``split_for_line`` (5 bubbles max
per call, 5000 chars per bubble).

Tests use ``httpx.MockTransport`` to fake the network; CI is offline.
Real wiring runs against ``https://api.line.me`` with the channel
access token from the LINE Developers Console.
"""

from __future__ import annotations

import time
import uuid

import httpx

from app.adapters.line.base import (
    REPLY_TOKEN_TTL_SECONDS,
    LineAdapter,
    split_for_line,
    strip_markdown,
)
from app.adapters.line.errors import LineAPIError, LineAuthError, LineRateLimitError


class LineRealAdapter(LineAdapter):
    """Real LINE adapter — implements the LineAdapter Protocol."""

    def __init__(
        self,
        channel_secret: str,
        channel_access_token: str,
        *,
        bot_user_id: str | None = None,
        api_base: str = "https://api.line.me",
        transport: httpx.MockTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._secret = channel_secret
        self._token = channel_access_token
        self._api_base = api_base.rstrip("/")
        if transport is not None:
            self._client = httpx.Client(transport=transport, timeout=timeout)
            self._owns_client = True
        else:
            self._client = httpx.Client(timeout=timeout)
            self._owns_client = True

        # Self-message filter (PR #2 bones).
        self._bot_user_id: str | None = bot_user_id
        self._bot_user_id_fetched_at: float | None = None

        # Reply-token cache (PR #2 bones).
        self._reply_tokens: dict[str, tuple[str, float]] = {}

    # ── Properties / helpers ──────────────────────────────────
    @property
    def channel_secret(self) -> str:
        return self._secret

    @property
    def bot_user_id(self) -> str | None:
        return self._bot_user_id

    def sign(self, body: bytes) -> str:
        from app.adapters.line.base import sign_line_webhook

        return sign_line_webhook(body, self._secret)

    def verify(self, body: bytes, signature: str) -> bool:
        from app.adapters.line.base import verify_line_webhook

        return verify_line_webhook(body, signature, self._secret)

    def set_reply_token(
        self, chat_id: str, token: str, *, ttl_seconds: int = REPLY_TOKEN_TTL_SECONDS
    ) -> None:
        self._reply_tokens[chat_id] = (token, time.time() + ttl_seconds)

    def consume_reply_token(self, chat_id: str) -> tuple[str | None, bool]:
        entry = self._reply_tokens.pop(chat_id, None)
        if not entry:
            return None, False
        token, expires_at = entry
        if not token or time.time() >= expires_at:
            return None, False
        return token, True

    # ── Bot-info fetch (cached) ───────────────────────────────
    def get_bot_user_id(self) -> str | None:
        """Return the channel's own LINE userId, fetched from /v2/bot/info.

        Cached after the first successful fetch. Returns the explicit
        init-time ``bot_user_id`` if provided (avoids the network call).
        """
        if self._bot_user_id is not None:
            return self._bot_user_id
        if self._bot_user_id_fetched_at is not None:
            return self._bot_user_id
        response = self._client.get(
            f"{self._api_base}/v2/bot/info",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if response.status_code == 401:
            raise LineAuthError("invalid access token for /v2/bot/info")
        if not response.is_success:
            raise LineAPIError(
                f"LINE /v2/bot/info failed ({response.status_code}): {response.text}"
            )
        data = response.json()
        self._bot_user_id = data.get("userId")
        self._bot_user_id_fetched_at = time.time()
        return self._bot_user_id

    # ── send_reply (the actual wiring) ────────────────────────
    def send_reply(self, line_user_id: str, text: str) -> dict[str, object]:
        """Send a reply to a LINE user, with self-message filter + transforms.

        Steps:
        1. Self-message filter: if line_user_id == bot_user_id → return
           ``{"skipped": "self-message"}`` without making any HTTP call.
        2. Apply outbound transforms: strip_markdown + split_for_line.
        3. Try Reply API first (free) if a cached reply token exists;
           fall back to Push API (metered) on miss/expire/error.
        """
        # 1) Self-message filter
        if self._bot_user_id is not None and line_user_id == self._bot_user_id:
            return {
                "id": f"reply-{uuid.uuid4().hex[:12]}",
                "line_user_id": line_user_id,
                "skipped": "self-message",
            }

        # 2) Outbound transforms
        clean = strip_markdown(text or "")
        bubbles = split_for_line(clean)
        messages = [{"type": "text", "text": b} for b in bubbles]

        # 3) Try Reply (free) if we have a cached token, else Push
        token, used_reply = self.consume_reply_token(line_user_id)
        if used_reply:
            response = self._client.post(
                f"{self._api_base}/v2/bot/message/reply",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                json={"replyToken": token, "messages": messages},
            )
        else:
            # Push API requires a target userId (LINE_TO = line_user_id)
            response = self._client.post(
                f"{self._api_base}/v2/bot/message/push",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                json={"to": line_user_id, "messages": messages},
            )

        if response.status_code == 401:
            raise LineAuthError("invalid access token for LINE Reply/Push")
        if response.status_code == 429:
            raise LineRateLimitError("LINE rate limit hit; retry with backoff")
        if not response.is_success:
            raise LineAPIError(
                f"LINE {('Reply' if used_reply else 'Push')} failed "
                f"({response.status_code}): {response.text}"
            )

        return {
            "id": f"reply-{uuid.uuid4().hex[:12]}",
            "line_user_id": line_user_id,
            "via": "reply" if used_reply else "push",
            "bubbles": len(messages),
        }

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
