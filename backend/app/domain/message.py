"""Message domain — Pydantic DTO for the messages table."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    """A row from the messages table — used as the inbound LINE inbox row."""

    model_config = ConfigDict(extra="ignore")

    id: str
    lead_id: str | None = None
    user_id: str
    direction: str | None = None  # 'inbound' | 'outbound'
    message_type: str | None = None
    content: str | None = None
    raw_data: dict[str, Any] | None = None
    is_ai_generated: bool | None = None
    created_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Message:
        return cls(**row)
