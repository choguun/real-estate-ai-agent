"""Leads router — list / get / update scoped to the calling team.

T-304: scoped by `team_id`. Within a team, all members see all leads.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.deps import CurrentTeamIdDep, DBDep
from app.domain.lead import Lead, LeadUpdate

router = APIRouter(prefix="/api/leads", tags=["leads"])


def _scope(db: Any, lead_id: str, team_id: str) -> dict[str, Any]:
    row: dict[str, Any] | None = db.get_by_id("leads", lead_id)
    if row is None or row.get("team_id") != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return row


@router.get("", response_model=list[Lead])
def list_leads(
    db: DBDep,
    team_id: CurrentTeamIdDep,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """List the team's leads, newest first."""
    rows = db.query("leads", filters={"team_id": team_id})
    if status_filter:
        rows = [r for r in rows if r.get("status") == status_filter]
    rows.sort(
        key=lambda r: (
            r.get("updated_at") or "",
            r.get("created_at") or "",
        ),
        reverse=True,
    )
    return rows[:limit]


@router.get("/{lead_id}")
def get_lead(lead_id: str, db: DBDep, team_id: CurrentTeamIdDep) -> dict[str, Any]:
    """Lead + its messages, oldest first by created_at."""
    lead = _scope(db, lead_id, team_id)
    messages = db.query("messages", filters={"lead_id": lead_id})
    messages.sort(
        key=lambda r: (
            r.get("created_at") or "",
            r.get("id") or "",
        ),
    )
    return {**lead, "messages": messages}


@router.patch("/{lead_id}", response_model=Lead)
def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    db: DBDep,
    team_id: CurrentTeamIdDep,
) -> dict[str, Any]:
    """Update editable fields. Pydantic forbids extras; status is enum."""
    _scope(db, lead_id, team_id)
    data: dict[str, Any] = payload.model_dump(exclude_none=True)
    if "status" in data:
        data["status"] = data["status"].value
    updated = db.update("leads", lead_id, data)
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return updated
