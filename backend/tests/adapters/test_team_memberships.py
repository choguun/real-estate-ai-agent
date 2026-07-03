"""T-301 — Team memberships + invitations mock + scoped queries.

Tests the mock's behavior on the new team_memberships and
team_invitations tables added by 002_teams.sql, plus the new
team_id-based scoping on properties/leads/messages.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.adapters.supabase._factory import get_db, reset_mock_singleton
from app.config import get_settings


@pytest.fixture
def adapter():
    """A fresh mock adapter for each test."""
    reset_mock_singleton()
    yield get_db(get_settings())
    reset_mock_singleton()


def _new_user_row(adapter, email: str = "u@x.com") -> dict[str, Any]:
    return adapter.insert(
        "users",
        {
            "email": email,
            "full_name": "User",
            "password_hash": "hash",
            "role": "agent",
        },
    )


def _new_team_row(adapter, name: str = "Team A", owner_id: str | None = None) -> dict[str, Any]:
    if owner_id is None:
        owner = _new_user_row(adapter, "owner@x.com")
        owner_id = str(owner["id"])
    return adapter.insert(
        "teams",
        {"name": name, "owner_id": owner_id, "plan": "starter"},
    )


# ── team_memberships CRUD ────────────────────────────────────────


def test_insert_and_get_team_membership(adapter) -> None:
    user = _new_user_row(adapter, f"{uuid4().hex[:8]}@x.com")
    team = _new_team_row(adapter)
    membership = adapter.insert(
        "team_memberships",
        {
            "team_id": str(team["id"]),
            "user_id": str(user["id"]),
            "role": "agent",
        },
    )
    assert membership["role"] == "agent"
    fetched = adapter.get_by_id("team_memberships", str(membership["id"]))
    assert fetched is not None
    assert fetched["team_id"] == str(team["id"])


def test_team_membership_role_defaults_to_agent(adapter) -> None:
    user = _new_user_row(adapter)
    team = _new_team_row(adapter)
    membership = adapter.insert(
        "team_memberships",
        {"team_id": str(team["id"]), "user_id": str(user["id"])},
    )
    assert membership["role"] == "agent"


def test_query_team_memberships_by_team(adapter) -> None:
    owner = _new_user_row(adapter, "owner@x.com")
    team = _new_team_row(adapter, owner_id=str(owner["id"]))
    agent = _new_user_row(adapter, "agent@x.com")
    adapter.insert(
        "team_memberships",
        {"team_id": str(team["id"]), "user_id": str(owner["id"]), "role": "owner"},
    )
    adapter.insert(
        "team_memberships",
        {"team_id": str(team["id"]), "user_id": str(agent["id"]), "role": "agent"},
    )
    rows = adapter.query("team_memberships", filters={"team_id": str(team["id"])})
    assert len(rows) == 2


def test_query_team_memberships_by_user(adapter) -> None:
    user = _new_user_row(adapter)
    team_a = _new_team_row(adapter, "Team A")
    team_b = _new_team_row(adapter, "Team B")
    adapter.insert(
        "team_memberships",
        {"team_id": str(team_a["id"]), "user_id": str(user["id"]), "role": "agent"},
    )
    adapter.insert(
        "team_memberships",
        {"team_id": str(team_b["id"]), "user_id": str(user["id"]), "role": "agent"},
    )
    rows = adapter.query("team_memberships", filters={"user_id": str(user["id"])})
    assert len(rows) == 2


# ── team_invitations CRUD ───────────────────────────────────────


def test_insert_team_invitation(adapter) -> None:
    inviter = _new_user_row(adapter, "inviter@x.com")
    team = _new_team_row(adapter, owner_id=str(inviter["id"]))
    invitation = adapter.insert(
        "team_invitations",
        {
            "team_id": str(team["id"]),
            "email": "alice@example.com",
            "role": "agent",
            "token": "abc123",
            "invited_by": str(inviter["id"]),
            "expires_at": "2026-12-31T00:00:00+00:00",
        },
    )
    assert invitation["email"] == "alice@example.com"
    assert invitation["role"] == "agent"


def test_team_invitation_token_is_unique(adapter) -> None:
    inviter = _new_user_row(adapter, "inviter@x.com")
    team = _new_team_row(adapter, owner_id=str(inviter["id"]))
    adapter.insert(
        "team_invitations",
        {
            "team_id": str(team["id"]),
            "email": "a@x.com",
            "role": "agent",
            "token": "duplicate-token",
            "invited_by": str(inviter["id"]),
            "expires_at": "2026-12-31T00:00:00+00:00",
        },
    )
    with pytest.raises(ValueError, match="UNIQUE constraint violation"):
        adapter.insert(
            "team_invitations",
            {
                "team_id": str(team["id"]),
                "email": "b@x.com",
                "role": "agent",
                "token": "duplicate-token",
                "invited_by": str(inviter["id"]),
                "expires_at": "2026-12-31T00:00:00+00:00",
            },
        )


# ── team-scoped queries on properties/leads/messages ─────────────


def test_query_properties_by_team(adapter) -> None:
    """Properties are scoped by team_id (set by the team-scoping routers)."""
    owner = _new_user_row(adapter, "owner@x.com")
    team = _new_team_row(adapter, owner_id=str(owner["id"]))
    prop = adapter.insert(
        "properties",
        {
            "user_id": str(owner["id"]),
            "team_id": str(team["id"]),
            "title": "Team property",
        },
    )
    rows = adapter.query("properties", filters={"team_id": str(team["id"])})
    assert len(rows) == 1
    assert rows[0]["id"] == prop["id"]


def test_cross_team_isolation_on_properties(adapter) -> None:
    """A property in team A must not appear in team B's query."""
    owner_a = _new_user_row(adapter, "a@x.com")
    owner_b = _new_user_row(adapter, "b@x.com")
    team_a = _new_team_row(adapter, "Team A", owner_id=str(owner_a["id"]))
    team_b = _new_team_row(adapter, "Team B", owner_id=str(owner_b["id"]))
    adapter.insert(
        "properties",
        {"user_id": str(owner_a["id"]), "team_id": str(team_a["id"]), "title": "A's"},
    )
    adapter.insert(
        "properties",
        {"user_id": str(owner_b["id"]), "team_id": str(team_b["id"]), "title": "B's"},
    )
    rows_a = adapter.query("properties", filters={"team_id": str(team_a["id"])})
    rows_b = adapter.query("properties", filters={"team_id": str(team_b["id"])})
    assert len(rows_a) == 1
    assert rows_a[0]["title"] == "A's"
    assert len(rows_b) == 1
    assert rows_b[0]["title"] == "B's"


def test_within_team_any_member_sees_properties(adapter) -> None:
    """Within a team, any member can list any other member's properties."""
    owner = _new_user_row(adapter, "owner@x.com")
    agent = _new_user_row(adapter, "agent@x.com")
    team = _new_team_row(adapter, owner_id=str(owner["id"]))
    adapter.insert(
        "team_memberships",
        {"team_id": str(team["id"]), "user_id": str(agent["id"]), "role": "agent"},
    )
    adapter.insert(
        "properties",
        {"user_id": str(owner["id"]), "team_id": str(team["id"]), "title": "Owner's prop"},
    )
    # Agent queries by team_id (not user_id) → sees owner's property
    rows = adapter.query("properties", filters={"team_id": str(team["id"])})
    assert len(rows) == 1
    assert rows[0]["title"] == "Owner's prop"
