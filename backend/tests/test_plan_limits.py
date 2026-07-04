"""T-404 — Plan-limit guard on invitations."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.supabase._factory import get_db, reset_mock_singleton
from app.config import get_settings
from app.main import create_app
from app.services.plan_limits import (
    PlanLimitExceeded,
    assert_can_invite,
    count_active_members,
    get_team_plan,
)


@pytest.fixture
def db():
    reset_mock_singleton()
    yield get_db(get_settings())
    reset_mock_singleton()


def test_get_team_plan_defaults_to_starter(db) -> None:
    team = db.insert("teams", {"name": "Test", "owner_id": "u1"})
    assert get_team_plan(db, team_id=team["id"]) == "starter"


def test_get_team_plan_returns_team_value(db) -> None:
    team = db.insert("teams", {"name": "Test", "owner_id": "u1", "plan": "growth"})
    assert get_team_plan(db, team_id=team["id"]) == "growth"


def test_count_active_members_excludes_soft_deleted(db) -> None:
    team = db.insert("teams", {"name": "T", "owner_id": "u1"})
    u1 = db.insert("users", {"email": "a@x.com", "full_name": "A"})
    u2 = db.insert("users", {"email": "b@x.com", "full_name": "B"})
    db.insert("team_memberships", {"team_id": team["id"], "user_id": u1["id"], "role": "owner"})
    db.insert("team_memberships", {"team_id": team["id"], "user_id": u2["id"], "role": "agent"})
    assert count_active_members(db, team_id=team["id"]) == 2
    # Soft-delete one
    memberships = db.query("team_memberships", filters={"team_id": team["id"], "user_id": u2["id"]})
    db.update("team_memberships", memberships[0]["id"], {"left_at": "2026-07-01T00:00:00Z"})
    assert count_active_members(db, team_id=team["id"]) == 1


# ── assert_can_invite (the seat guard) ─────────────────────


def test_assert_can_invite_passes_under_limit(db) -> None:
    """starter plan (1 seat), 1 member used → inviting 2nd raises."""
    team = db.insert("teams", {"name": "T", "owner_id": "u1"})
    u1 = db.insert("users", {"email": "a@x.com", "full_name": "A"})
    db.insert("team_memberships", {"team_id": team["id"], "user_id": u1["id"], "role": "owner"})
    with pytest.raises(PlanLimitExceeded) as exc:
        assert_can_invite(db, team_id=team["id"])
    assert exc.value.code == "seats"
    assert exc.value.limit == 1
    assert exc.value.used == 1


def test_assert_can_invite_passes_for_growth_plan(db) -> None:
    """growth (3 seats): 1 member ok; 4th would fail."""
    team = db.insert("teams", {"name": "T", "owner_id": "u1", "plan": "growth"})
    u1 = db.insert("users", {"email": "a@x.com", "full_name": "A"})
    db.insert("team_memberships", {"team_id": team["id"], "user_id": u1["id"], "role": "owner"})
    assert_can_invite(db, team_id=team["id"])
    # Add 2 more (total 3)
    for i in range(2):
        u = db.insert("users", {"email": f"u{i}@x.com", "full_name": f"U{i}"})
        db.insert("team_memberships", {"team_id": team["id"], "user_id": u["id"], "role": "agent"})
    # 3 active, growth = 3 → 4th would exceed
    with pytest.raises(PlanLimitExceeded) as exc:
        assert_can_invite(db, team_id=team["id"])
    assert exc.value.limit == 3
    assert exc.value.used == 3


def test_assert_can_invite_for_team_plan_allows_9(db) -> None:
    """team (10 seats): 9 members fit, 10th raises."""
    team = db.insert("teams", {"name": "T", "owner_id": "u1", "plan": "team"})
    u1 = db.insert("users", {"email": "a@x.com", "full_name": "A"})
    db.insert("team_memberships", {"team_id": team["id"], "user_id": u1["id"], "role": "owner"})
    for i in range(8):
        u = db.insert("users", {"email": f"u{i}@x.com", "full_name": f"U{i}"})
        db.insert(
            "team_memberships",
            {"team_id": team["id"], "user_id": u["id"], "role": "agent"},
        )
    # 9 active, team plan = 10 seats → 9 < 10 → fits
    assert_can_invite(db, team_id=team["id"])


# ── end-to-end via the router ────────────────────────────


def _client() -> TestClient:
    reset_mock_singleton()
    app = create_app(get_settings())
    return TestClient(app)


def test_invite_403_plan_limit_exceeded_free_plan() -> None:
    """ST-BL-06: starter plan refuses 2nd member invitation (403)."""
    client = _client()
    r1 = client.post(
        "/api/auth/signup",
        json={"email": "owner-pl@example.com", "password": "supersecret123", "full_name": "P"},
    )
    assert r1.status_code in (200, 201)
    owner_token = r1.json()["token"]
    r = client.post(
        "/api/teams",
        json={"name": "My Team"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    team_id = r.json()["id"]
    invite = client.post(
        f"/api/teams/{team_id}/invitations",
        json={"email": "alice-pl@example.com", "role": "agent"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    # Starter plan = 1 seat. The owner is already a member. So inviting
    # the 2nd would exceed → 403.
    assert invite.status_code == 403
    assert "limit" in invite.json()["detail"].lower()


def test_invite_succeeds_after_upgrade() -> None:
    """AC-BL-07: plan upgrade via webhook immediately raises the limit."""
    import json

    client = _client()
    r1 = client.post(
        "/api/auth/signup",
        json={"email": "owner-up@example.com", "password": "supersecret123", "full_name": "U"},
    )
    assert r1.status_code in (200, 201)
    owner_token = r1.json()["token"]
    team = client.post(
        "/api/teams",
        json={"name": "Up"},
        headers={"Authorization": f"Bearer {owner_token}"},
    ).json()
    team_id = team["id"]
    # First invite is rejected (starter = 1 seat, owner is already in)
    r = client.post(
        f"/api/teams/{team_id}/invitations",
        json={"email": "a-up@example.com", "role": "agent"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 403
    # Webhook upgrade to growth
    payload = json.dumps(
        {
            "id": "evt_up_st",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"team_id": team_id, "plan": "growth"},
                    "customer": "cus_x",
                    "subscription": "sub_x",
                }
            },
        }
    ).encode()
    client.post(
        "/api/billing/webhook",
        content=payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": "test-mock-sig"},
    )
    # Now invite should succeed (growth = 3 seats, 1 used → fits)
    r = client.post(
        f"/api/teams/{team_id}/invitations",
        json={"email": "a-up@example.com", "role": "agent"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201, r.text
