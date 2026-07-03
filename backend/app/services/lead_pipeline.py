"""Lead pipeline — turn verified LINE events into leads + messages.

Idempotency contract: a given event_id is processed at most once.
We detect replays by scanning `messages.raw_data['event_id']` — fine
for MVP (mock) volume; production would add an index on a column.

Failure modes (logged, never crash the webhook handler):
- Missing event_id             → ignored, processed=False
- Non-message events (follow,  → ignored, processed=False
  unfollow, join, leave)
- Missing source               → ignored, processed=False
- Malformed payload            → ignored, processed=False
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.adapters.supabase.base import SupabaseAdapter

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """Outcome of processing a single event."""

    event_id: str
    processed: bool
    new_lead: bool
    new_message: bool
    lead_id: str | None
    message_id: str | None
    reason: str  # "ok" | "replay" | "no_event_id" | "no_source" | "non_message"


class LeadPipeline:
    """Stateless service — owned DB injected via the constructor."""

    def __init__(self, db: SupabaseAdapter) -> None:
        self._db = db

    # ─── Idempotency ─────────────────────────────────────────────
    def is_event_processed(self, event_id: str) -> bool:
        if not event_id:
            return False
        for m in self._db.query("messages"):
            raw = m.get("raw_data")
            if isinstance(raw, dict) and raw.get("event_id") == event_id:
                return True
        return False

    # ─── Entry point ──────────────────────────────────────────────
    def process_event(self, event: dict[str, Any], agent_id: str) -> ProcessResult:
        event_id = _extract_event_id(event)
        if not event_id:
            logger.info("LINE event missing event_id; ignoring")
            return ProcessResult(
                event_id="",
                processed=False,
                new_lead=False,
                new_message=False,
                lead_id=None,
                message_id=None,
                reason="no_event_id",
            )

        if self.is_event_processed(event_id):
            logger.info("LINE event %s already processed; ignoring as replay", event_id)
            return ProcessResult(
                event_id=event_id,
                processed=False,
                new_lead=False,
                new_message=False,
                lead_id=None,
                message_id=None,
                reason="replay",
            )

        if event.get("type") != "message":
            logger.info("LINE event %s is type=%s; ignoring", event_id, event.get("type"))
            return ProcessResult(
                event_id=event_id,
                processed=False,
                new_lead=False,
                new_message=False,
                lead_id=None,
                message_id=None,
                reason="non_message",
            )

        source = event.get("source") or {}
        line_user_id = source.get("userId")
        if not line_user_id:
            logger.info("LINE event %s has no source.userId; ignoring", event_id)
            return ProcessResult(
                event_id=event_id,
                processed=False,
                new_lead=False,
                new_message=False,
                lead_id=None,
                message_id=None,
                reason="no_source",
            )

        # Find or create lead.
        existing = self._db.query("leads", filters={"line_user_id": line_user_id})
        if existing:
            lead = existing[0]
            new_lead = False
        else:
            lead = self._db.insert(
                "leads",
                {
                    "user_id": agent_id,
                    "line_user_id": line_user_id,
                    "source": "line",
                },
            )
            new_lead = True

        # Resolve message content.
        msg = event.get("message") or {}
        msg_type = msg.get("type") or "text"
        content = msg.get("text") or msg.get("altText") or ""

        message = self._db.insert(
            "messages",
            {
                "user_id": agent_id,
                "lead_id": lead["id"],
                "direction": "inbound",
                "message_type": msg_type,
                "content": content,
                "raw_data": event,  # store full event for re-processing / audit
                "is_ai_generated": False,
            },
        )

        # Bump last_contacted_at on the lead (proxy-via updated_at keeps
        # the schema simple — production would add last_contacted_at as a
        # column and trigger.)
        from datetime import datetime, timezone

        self._db.update(
            "leads",
            lead["id"],
            {"updated_at": datetime.now(timezone.utc).isoformat()},
        )

        return ProcessResult(
            event_id=event_id,
            processed=True,
            new_lead=new_lead,
            new_message=True,
            lead_id=lead["id"],
            message_id=message["id"],
            reason="ok",
        )


def _extract_event_id(event: dict[str, Any]) -> str:
    """LINE sends `event_id` for message/follow/etc., or `webhookEventId`
    in some payloads. Accept either; default to empty string if missing.
    """
    return (
        (event.get("event_id") if isinstance(event.get("event_id"), str) else None)
        or (event.get("webhookEventId") if isinstance(event.get("webhookEventId"), str) else None)
        or ""
    )
