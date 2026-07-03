"""Real LINE Messaging API adapter — stub for MVP.

Real wiring (HTTP calls to `api.line.me/v2/bot/message/reply`) ships
in T-009/T-010. For T-008 the client only needs to verify webhook
signatures using the same shared helper, so the class can be swapped
in via env without any other code change.
"""

from __future__ import annotations

from app.adapters.line.base import sign_line_webhook, verify_line_webhook


class LineRealAdapter:
    def __init__(
        self,
        channel_secret: str,
        channel_access_token: str,
        *,
        api_base: str = "https://api.line.me",
    ) -> None:
        self._secret = channel_secret
        self._token = channel_access_token
        self._api_base = api_base

    @property
    def channel_secret(self) -> str:
        return self._secret

    def sign(self, body: bytes) -> str:
        return sign_line_webhook(body, self._secret)

    def verify(self, body: bytes, signature: str) -> bool:
        return verify_line_webhook(body, signature, self._secret)

    def send_reply(self, line_user_id: str, text: str) -> dict[str, object]:
        raise NotImplementedError(
            "LineRealAdapter.send_reply is not wired in MVP. "
            "Set use_real_line=false (default) to use mocks."
        )
