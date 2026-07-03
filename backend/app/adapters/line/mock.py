"""In-memory LINE adapter.

Sign + verify work identically to a real client; the mock also keeps a
recent-events log so tests can inspect what the webhook received after
verification passed.
"""

from __future__ import annotations

from app.adapters.line.base import (
    sign_line_webhook,
    verify_line_webhook,
)


class LineMockAdapter:
    def __init__(self, channel_secret: str) -> None:
        self._secret = channel_secret
        self.received_events: list[dict[str, object]] = []

    @property
    def channel_secret(self) -> str:
        return self._secret

    def sign(self, body: bytes) -> str:
        return sign_line_webhook(body, self._secret)

    def verify(self, body: bytes, signature: str) -> bool:
        return verify_line_webhook(body, signature, self._secret)
