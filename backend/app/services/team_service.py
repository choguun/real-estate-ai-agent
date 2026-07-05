"""TeamService — team lifecycle + membership queries.

The service is intentionally thin: it composes DB rows (from the
generic mock/real adapters) into team-scoped views. All tenant
isolation happens at the DB level (RLS, real path) or via the
team_id filter (mock path) — the service does NOT enforce isolation
itself; the routers must pass the right `team_id`.
"""

from __future__ import annotations

import secrets
from typing import Any
from uuid import UUID

from app.adapters.supabase import SupabaseAdapter


def create_team(
    adapter: SupabaseAdapter, *, name: str, owner_id: UUID, plan: str = "starter"
) -> dict[str, Any]:
    """Create a team + add the owner as the first member.

    Inserts the team row, then inserts a `team_memberships` row with
    `role='owner'`. Both are part of the same logical operation; if
    the second insert fails, the team row is left orphaned (acceptable
    in dev; Cycle 4+ will use a transaction).
    """
    team = adapter.insert("teams", {"name": name, "owner_id": str(owner_id), "plan": plan})
    adapter.insert(
        "team_memberships",
        {"team_id": str(team["id"]), "user_id": str(owner_id), "role": "owner"},
    )
    return team


def get_user_team(adapter: SupabaseAdapter, *, user_id: UUID) -> dict[str, Any] | None:
    """Return the first (and only) team the user belongs to.

    MVP: a user is in at most one team. Returns None if no membership.
    """
    memberships = adapter.query("team_memberships", filters={"user_id": str(user_id)})
    if not memberships:
        return None
    team_id = memberships[0]["team_id"]
    team = adapter.get_by_id("teams", team_id)
    if team is None or team.get("deleted_at") is not None:
        return None
    return team


def list_members(adapter: SupabaseAdapter, *, team_id: UUID) -> list[dict[str, Any]]:
    """Return active members of a team (joined with users) for display.

    Excludes soft-deleted members (`left_at IS NOT NULL`).
    """
    memberships = adapter.query("team_memberships", filters={"team_id": str(team_id)})
    out: list[dict[str, Any]] = []
    for m in memberships:
        if m.get("left_at") is not None:
            continue
        user = adapter.get_by_id("users", m["user_id"])
        if user is None:
            continue
        out.append(
            {
                "id": m["id"],
                "team_id": m["team_id"],
                "user_id": m["user_id"],
                "email": user["email"],
                "full_name": user["full_name"],
                "role": m["role"],
                "joined_at": m["joined_at"],
                "left_at": m.get("left_at"),
            }
        )
    return out


def user_is_member(adapter: SupabaseAdapter, *, user_id: UUID, team_id: UUID) -> bool:
    """True iff `user_id` is an active member of `team_id`."""
    rows = adapter.query(
        "team_memberships",
        filters={"team_id": str(team_id), "user_id": str(user_id)},
    )
    if not rows:
        return False
    return rows[0].get("left_at") is None


def user_role_in_team(adapter: SupabaseAdapter, *, user_id: UUID, team_id: UUID) -> str | None:
    """Return the user's role in the team, or None if not a member."""
    rows = adapter.query(
        "team_memberships",
        filters={"team_id": str(team_id), "user_id": str(user_id)},
    )
    if not rows:
        return None
    if rows[0].get("left_at") is not None:
        return None
    role_raw: object = rows[0]["role"]
    return str(role_raw)


def generate_invite_token() -> str:
    """Generate a secure URL-safe token (≥32 bytes entropy)."""
    return secrets.token_urlsafe(32)


def get_effective_rate_limits(adapter: SupabaseAdapter, *, team_id: str) -> dict[str, int]:
    """Return the team's effective rate-limit policy.

    Reads the `team_rate_limits` row if one exists; falls back to
    the system defaults otherwise. The shape is
    `{login_per_15min, signup_per_hour, invite_per_hour}` (cycle-6
    fields, keyed by their public names rather than the internal
    `auth.login` / `auth.signup` / `team.invite` action names).

    A future cycle can add an in-memory cache here (lru_cache +
    TTL); for now, every rate-limit check on a team-scoped endpoint
    does one extra DB query. Acceptable at current scale.
    """
    rows = adapter.query("team_rate_limits", filters={"team_id": str(team_id)})
    defaults = {
        "login_per_15min": 5,
        "signup_per_hour": 5,
        "invite_per_hour": 20,
    }
    if not rows:
        return defaults
    row = rows[0]
    return {
        "login_per_15min": row.get("login_per_15min", defaults["login_per_15min"]),
        "signup_per_hour": row.get("signup_per_hour", defaults["signup_per_hour"]),
        "invite_per_hour": row.get("invite_per_hour", defaults["invite_per_hour"]),
    }


def set_team_rate_limits(
    adapter: SupabaseAdapter,
    *,
    team_id: str,
    login_per_15min: int | None = None,
    signup_per_hour: int | None = None,
    invite_per_hour: int | None = None,
) -> dict[str, int]:
    """Upsert per-team rate-limit overrides.

    None values mean "don't change this field." The router layer
    enforces at-least-one-field-present and ≥ 1 per field; this
    service trusts its callers (router validates).
    """
    # Build the patch from existing row + new values
    existing = adapter.query("team_rate_limits", filters={"team_id": str(team_id)})
    row = existing[0] if existing else {"team_id": str(team_id)}

    if login_per_15min is not None:
        row["login_per_15min"] = login_per_15min
    if signup_per_hour is not None:
        row["signup_per_hour"] = signup_per_hour
    if invite_per_hour is not None:
        row["invite_per_hour"] = invite_per_hour
    row["updated_at"] = (
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    )

    if existing:
        adapter.update("team_rate_limits", row["team_id"], row)
    else:
        adapter.insert("team_rate_limits", row)

    return get_effective_rate_limits(adapter, team_id=team_id)
