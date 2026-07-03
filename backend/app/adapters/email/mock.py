"""Mock email adapter — logs to console + records in-memory sent list."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from app.adapters.email.base import EmailAdapter

logger = logging.getLogger(__name__)


class MockEmailAdapter(EmailAdapter):
    """Records every sent email in a thread-safe in-memory list."""

    def __init__(self) -> None:
        self._sent: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
    ) -> dict[str, str]:
        record = {
            "id": f"mock-email-{uuid.uuid4().hex[:12]}",
            "to": to,
            "subject": subject,
            "body": body,
            "html": html or "",
        }
        with self._lock:
            self._sent.append(record)
        # Visible in the dev console — operators can copy the invite
        # URL from here during local testing.
        logger.info("[mock-email] to=%s subject=%s\n%s", to, subject, body)
        return {"id": record["id"]}

    @property
    def sent(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._sent)

    def reset(self) -> None:
        with self._lock:
            self._sent.clear()
