"""T-303 — Member management (role change + remove + leave)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _signup(client: TestClient, email: str) -> str:
    r = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "supersecret123", "full_name": "M"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_team(client: TestClient, token: str) -> str:
    r = client.post("/api/teams", json={"name": "Test Team"}, headers=_auth(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _add_member_via_invite(client: TestClient, owner_token: str, team_id: str, email: str) -> str:
    """Owner invites, accept flow is T-307; for now manually add via insert."""
    r = client.post(
        f"/api/teams/{team_id}/invitations",
        json={"email": email, "role": "agent"},
        headers=_auth(owner_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


# ── ST-MT-06: change role (owner only) ─────────────────────────


def test_owner_can_change_member_role() -> None:
    client = _client()
    owner_token = _signup(client, "owner-mr@example.com")
    _signup(client, "agent-mr@example.com")
    team_id = _create_team(client, owner_token)

    # Manually add agent to team (simulating accepted invite)
    from app.adapters.supabase._factory import get_db
    from app.config import get_settings

    db = get_db(get_settings())
    user_rows = db.query("users", filters={"email": "agent-mr@example.com"})
    assert user_rows
    db.insert(
        "team_memberships",
        {
            "team_id": team_id,
            "user_id": str(user_rows[0]["id"]),
            "role": "agent",
        },
    )

    # Owner changes agent to admin
    r = client.patch(
        f"/api/teams/{team_id}/members/{user_rows[0]['id']}",
        json={"role": "admin"},
        headers=_auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"


def test_non_owner_cannot_change_role() -> None:
    client = _client()
    owner_token = _signup(client, "owner-mr2@example.com")
    agent_token = _signup(client, "agent-mr2@example.com")
    team_id = _create_team(client, owner_token)
    from app.adapters.supabase._factory import get_db
    from app.config import get_settings

    db = get_db(get_settings())
    user_rows = db.query("users", filters={"email": "agent-mr2@example.com"})
    assert user_rows
    db.insert(
        "team_memberships",
        {
            "team_id": team_id,
            "user_id": str(user_rows[0]["id"]),
            "role": "agent",
        },
    )

    # Agent tries to change another member's role
    r = client.patch(
        f"/api/teams/{team_id}/members/{user_rows[0]['id']}",
        json={"role": "admin"},
        headers=_auth(agent_token),
    )
    assert r.status_code == 403


# ── ST-MT-07: owner cannot demote themselves ──────────────────


def test_owner_cannot_demote_themselves() -> None:
    client = _client()
    owner_token = _signup(client, "self-demote@example.com")
    team_id = _create_team(client, owner_token)

    # Get owner's user id
    from app.adapters.supabase._factory import get_db
    from app.config import get_settings

    db = get_db(get_settings())
    user_rows = db.query("users", filters={"email": "self-demote@example.com"})
    owner_id = str(user_rows[0]["id"])

    # Owner tries to demote themselves to agent
    r = client.patch(
        f"/api/teams/{team_id}/members/{owner_id}",
        json={"role": "agent"},
        headers=_auth(owner_token),
    )
    assert r.status_code == 409
    assert "cannot demote" in r.json()["detail"]


# ── ST-MT-08: owner cannot leave ─────────────────────────────


def test_owner_cannot_leave_team() -> None:
    client = _client()
    owner_token = _signup(client, "owner-leave@example.com")
    team_id = _create_team(client, owner_token)

    r = client.post(f"/api/teams/{team_id}/leave", headers=_auth(owner_token))
    assert r.status_code == 409
    assert "owner cannot leave" in r.json()["detail"]


def test_agent_can_leave_team() -> None:
    client = _client()
    owner_token = _signup(client, "owner-al@example.com")
    agent_token = _signup(client, "agent-al@example.com")
    team_id = _create_team(client, owner_token)

    from app.adapters.supabase._factory import get_db
    from app.config import get_settings

    db = get_db(get_settings())
    user_rows = db.query("users", filters={"email": "agent-al@example.com"})
    assert user_rows
    db.insert(
        "team_memberships",
        {
            "team_id": team_id,
            "user_id": str(user_rows[0]["id"]),
            "role": "agent",
        },
    )

    # Agent leaves
    r = client.post(f"/api/teams/{team_id}/leave", headers=_auth(agent_token))
    assert r.status_code == 204

    # Verify they no longer appear in members
    members = client.get(f"/api/teams/{team_id}/members", headers=_auth(owner_token)).json()
    assert all(m["user_id"] != str(user_rows[0]["id"]) for m in members)


# ── Remove member (owner only) ─────────────────────────────


def test_owner_can_remove_member() -> None:
    client = _client()
    owner_token = _signup(client, "owner-rm@example.com")
    team_id = _create_team(client, owner_token)

    from app.adapters.supabase._factory import get_db
    from app.config import get_settings

    db = get_db(get_settings())
    _signup(client, "agent-rm@example.com")  # agent user
    user_rows = db.query("users", filters={"email": "agent-rm@example.com"})
    assert user_rows
    agent_id = str(user_rows[0]["id"])
    db.insert(
        "team_memberships",
        {
            "team_id": team_id,
            "user_id": agent_id,
            "role": "agent",
        },
    )

    # Owner removes agent
    r = client.delete(f"/api/teams/{team_id}/members/{agent_id}", headers=_auth(owner_token))
    assert r.status_code == 204

    # Verify they're gone
    members = client.get(f"/api/teams/{team_id}/members", headers=_auth(owner_token)).json()
    assert all(m["user_id"] != agent_id for m in members)


def test_owner_cannot_remove_themselves() -> None:
    client = _client()
    owner_token = _signup(client, "owner-rmself@example.com")
    team_id = _create_team(client, owner_token)

    from app.adapters.supabase._factory import get_db
    from app.config import get_settings

    db = get_db(get_settings())
    user_rows = db.query("users", filters={"email": "owner-rmself@example.com"})
    owner_id = str(user_rows[0]["id"])

    r = client.delete(f"/api/teams/{team_id}/members/{owner_id}", headers=_auth(owner_token))
    assert r.status_code == 409
    assert "cannot remove themselves" in r.json()["detail"]
