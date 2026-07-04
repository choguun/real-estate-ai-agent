"""Plan limit helpers — T-404.

Pure functions over a `SupabaseAdapter` to check whether a team is
within its plan's seat / property / AI cap. Called from
`/api/teams/{id}/invitations` and `/api/properties` to enforce.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.adapters.supabase import SupabaseAdapter
from app.services.billing_service import get_plan_limits


class PlanLimitExceeded(Exception):
    """Raised when a team has hit its plan's cap (seats, properties, AI).

    The `code` is one of 'seats', 'properties', 'ai_listings' so the
    router can return a useful error message.
    """

    def __init__(self, code: str, limit: int, used: int) -> None:
        self.code = code
        self.limit = limit
        self.used = used
        super().__init__(f"{code} plan limit exceeded: {used}/{limit}")


def get_team_plan(adapter: SupabaseAdapter, *, team_id: UUID) -> str:
    """Return the team's current plan (default: 'starter')."""
    team = adapter.get_by_id("teams", str(team_id))
    return team.get("plan", "starter") if team else "starter"


def count_active_members(adapter: SupabaseAdapter, *, team_id: UUID) -> int:
    """Count active team_memberships (left_at IS NULL)."""
    rows = adapter.query("team_memberships", filters={"team_id": str(team_id)})
    return sum(1 for r in rows if r.get("left_at") is None)


def assert_can_invite(adapter: SupabaseAdapter, *, team_id: UUID) -> None:
    """Raise PlanLimitExceeded if the team is at its seat cap.

    Called from `POST /api/teams/{id}/invitations` after we've
    confirmed the invitee isn't already a member but before we email
    them. The invitation isn't created if this raises.
    """
    plan = get_team_plan(adapter, team_id=team_id)
    limits = get_plan_limits(plan)
    used = count_active_members(adapter, team_id=team_id)
    if used >= limits["seats"]:
        raise PlanLimitExceeded(code="seats", limit=limits["seats"], used=used)


def plan_status_dict(adapter: SupabaseAdapter, *, team_id: UUID) -> dict[str, Any]:
    """Return a per-cap snapshot for /api/billing/status and the dashboard."""
    plan = get_team_plan(adapter, team_id=team_id)
    limits = get_plan_limits(plan)
    used_seats = count_active_members(adapter, team_id=team_id)
    return {
        "plan": plan,
        "seats_limit": limits["seats"],
        "seats_used": used_seats,
        "properties_limit": limits["properties"],
        "ai_listings_limit_month": limits["ai_listings_per_month"],
    }
