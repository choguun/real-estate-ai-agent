"""Agent → lead outbound messages + LINE delivery.

T-304: scoped by `team_id` (the caller's current team).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.supabase.base import SupabaseAdapter
from app.deps import CurrentTeamIdDep, CurrentUserIdDep, DBDep, LineDep

router = APIRouter(tags=["messages"])


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)


@router.post("/api/leads/{lead_id}/messages", status_code=status.HTTP_201_CREATED)
def send_reply(
    lead_id: str,
    payload: ReplyIn,
    db: DBDep,
    user_id: CurrentUserIdDep,
    team_id: CurrentTeamIdDep,
    line: LineDep,
) -> dict[str, object]:
    """Send an outbound text reply to a lead.

    The lead must belong to the caller's team. Inserted as
    `direction='outbound'`, `is_ai_generated=False`, then handed to the
    LINE adapter.
    """
    lead: dict[str, object] | None = db.get_by_id("leads", lead_id)
    if lead is None or lead.get("team_id") != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Lead not found")

    line_user_id = lead.get("line_user_id")
    if not isinstance(line_user_id, str) or not line_user_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Lead has no LINE user id; manual outbound not supported in MVP",
        )

    adapter_response = line.send_reply(line_user_id, payload.text)

    msg = _send_message(db, user_id=user_id, team_id=team_id, lead_id=lead_id, content=payload.text)

    db.update(
        "leads",
        lead_id,
        {"updated_at": datetime.now(timezone.utc).isoformat()},
    )

    return {
        "message": msg,
        "line_reply": adapter_response,
    }


def _send_message(
    db: SupabaseAdapter,
    *,
    user_id: str,
    team_id: str,
    lead_id: str,
    content: str,
) -> dict[str, object]:
    return db.insert(
        "messages",
        {
            "user_id": user_id,
            "team_id": team_id,
            "lead_id": lead_id,
            "direction": "outbound",
            "message_type": "text",
            "content": content,
            "is_ai_generated": False,
        },
    )
