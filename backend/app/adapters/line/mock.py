"""In-memory LINE adapter.

Sign + verify work identically to a real client; the mock also keeps a
sent-replies log so tests can inspect what the agent has sent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.adapters.line.base import (
    sign_line_webhook,
    verify_line_webhook,
)


@dataclass
class _SentReply:
    line_user_id: str
    text: str
    sent_at: str


class LineMockAdapter:
    def __init__(self, channel_secret: str) -> None:
        self._secret = channel_secret
        self.received_events: list[dict[str, object]] = []
        self.sent_replies: list[_SentReply] = []

    @property
    def channel_secret(self) -> str:
        return self._secret

    def sign(self, body: bytes) -> str:
        return sign_line_webhook(body, self._secret)

    def verify(self, body: bytes, signature: str) -> bool:
        return verify_line_webhook(body, signature, self._secret)

    def send_reply(self, line_user_id: str, text: str) -> dict[str, object]:
        reply_id = uuid.uuid4().hex[:12]
        sent = _SentReply(
            line_user_id=line_user_id,
            text=text,
            sent_at=datetime.now(timezone.utc).isoformat(),
        )
        self.sent_replies.append(sent)
        return {
            "id": f"reply-{reply_id}",
            "line_user_id": line_user_id,
            "sent_at": sent.sent_at,
        }
