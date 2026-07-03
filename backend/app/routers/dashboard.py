"""Dashboard router — the agent's home screen payload.

T-304: scoped by `team_id` (the caller's current team) — every agent
in a team sees the same dashboard (team-wide new leads, recent
messages, recent properties).

Three blocks for /api/dashboard:
1. `new_leads_count` — number of leads with status='new' for the team
2. `recent_inbound` — last 20 inbound messages, each enriched with lead meta
3. `recent_properties` — last 5 properties (newest by updated_at, archived hidden)

This endpoint is polled by the dashboard page every 5 s in MVP
(no WebSockets). The contract is small and stable so we can cache it
later without changing the frontend.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.deps import CurrentTeamIdDep, DBDep

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def get_dashboard(db: DBDep, team_id: CurrentTeamIdDep) -> dict[str, Any]:
    # 1. New leads count — status='new' scoped to the calling team.
    all_leads = db.query("leads", filters={"team_id": team_id})
    new_leads_count = sum(1 for ld in all_leads if ld.get("status") == "new")

    # 2. Recent inbound messages (last 20), enriched with lead preview.
    # Build a {lead_id -> lead} dict in one query to avoid N+1 on real DB.
    leads_by_id: dict[str, dict[str, Any]] = {
        ld["id"]: ld for ld in all_leads if isinstance(ld.get("id"), str)
    }

    # T-304: messages are team-scoped; cross-team defense (the mock
    # doesn't have RLS, so we filter explicitly).
    all_team_messages = db.query("messages", filters={"team_id": team_id})
    inbound = [m for m in all_team_messages if m.get("direction") == "inbound"]
    inbound.sort(
        key=lambda m: (m.get("created_at") or "", m.get("id") or ""),
        reverse=True,
    )
    recent_inbound: list[dict[str, Any]] = []
    for m in inbound[:20]:
        lead_id = m.get("lead_id")
        lead_preview: dict[str, Any] | None = None
        if lead_id:
            row = leads_by_id.get(lead_id)
            # Cross-team defense: even though all_leads is team-scoped,
            # a stale row whose lead_id is no longer in this team's
            # leads dict should not leak. (Belt + suspenders.)
            if row is not None and row.get("team_id") == team_id:
                lead_preview = {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "line_user_id": row.get("line_user_id"),
                }
        recent_inbound.append({**m, "lead": lead_preview})

    # 3. Recent properties (last 5, newest first by updated_at, archived hidden).
    properties = db.query("properties", filters={"team_id": team_id})
    properties = [p for p in properties if p.get("status") != "archived"]
    properties.sort(
        key=lambda p: (p.get("updated_at") or "", p.get("created_at") or ""),
        reverse=True,
    )
    recent_properties = properties[:5]

    return {
        "new_leads_count": new_leads_count,
        "recent_inbound": recent_inbound,
        "recent_properties": recent_properties,
    }
