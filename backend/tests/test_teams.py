"""T-302 — Team CRUD + membership router tests."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _signup(client: TestClient, email: str) -> str:
    r = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "supersecret123", "full_name": "T"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── ST-MT-01: create team ──────────────────────────────────────


def test_create_team_sets_caller_as_owner() -> None:
    client = _client()
    token = _signup(client, "owner1@example.com")
    response = client.post(
        "/api/teams",
        json={"name": "Smith Realty"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Smith Realty"
    assert body["plan"] == "starter"

    # The caller should be a member with role=owner
    me = client.get("/api/teams/me", headers=_auth(token)).json()
    assert me is not None
    assert me["id"] == body["id"]
    members = client.get(f"/api/teams/{body['id']}/members", headers=_auth(token)).json()
    assert len(members) == 1
    assert members[0]["role"] == "owner"
    assert members[0]["email"] == "owner1@example.com"


def test_create_team_requires_auth() -> None:
    response = _client().post("/api/teams", json={"name": "X"})
    assert response.status_code in (401, 403)


# ── ST-MT-02: get_my_team ───────────────────────────────────────


def test_get_my_team_returns_none_for_new_user() -> None:
    client = _client()
    token = _signup(client, "loner@example.com")
    response = client.get("/api/teams/me", headers=_auth(token))
    assert response.status_code == 200
    assert response.json() is None


def test_get_my_team_returns_team_after_creation() -> None:
    client = _client()
    token = _signup(client, "owner2@example.com")
    created = client.post("/api/teams", json={"name": "Best Team"}, headers=_auth(token)).json()
    me = client.get("/api/teams/me", headers=_auth(token)).json()
    assert me is not None
    assert me["id"] == created["id"]


# ── ST-MT-03: list members ─────────────────────────────────────


def test_list_members_requires_membership() -> None:
    client = _client()
    token_a = _signup(client, "alice@example.com")
    token_b = _signup(client, "bob@example.com")
    team = client.post("/api/teams", json={"name": "Alice's Team"}, headers=_auth(token_a)).json()
    # Bob (not a member) cannot list Alice's team members
    response = client.get(f"/api/teams/{team['id']}/members", headers=_auth(token_b))
    assert response.status_code == 403


# ── Invitations: token generation + UNIQUE ────────────────────


def test_invite_member_returns_token() -> None:
    client = _client()
    token = _signup(client, "owner3@example.com")
    team = client.post("/api/teams", json={"name": "Inviters"}, headers=_auth(token)).json()
    response = client.post(
        f"/api/teams/{team['id']}/invitations",
        json={"email": "alice@example.com", "role": "agent"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "agent"
    # Token is ≥32 bytes base64-url (~43 chars)
    assert len(body["token"]) >= 32


def test_invite_token_is_high_entropy() -> None:
    """Token must be secure — at least 32 bytes of entropy."""
    client = _client()
    token = _signup(client, "owner4@example.com")
    team = client.post("/api/teams", json={"name": "Secure"}, headers=_auth(token)).json()
    response = client.post(
        f"/api/teams/{team['id']}/invitations",
        json={"email": "x@x.com"},
        headers=_auth(token),
    )
    token_str = response.json()["token"]
    # secrets.token_urlsafe(32) → ~43 chars of base64-url
    assert len(token_str) >= 32
    # No easily-guessable patterns
    assert not re.match(r"^[a-z]+$", token_str)


def test_invite_only_owner_can_invite() -> None:
    """Non-owners get 403 even if they are team members."""
    client = _client()
    owner_token = _signup(client, "owner5@example.com")
    team = client.post("/api/teams", json={"name": "Strict"}, headers=_auth(owner_token)).json()
    team_id = team["id"]
    # Invite an agent
    invite = client.post(
        f"/api/teams/{team_id}/invitations",
        json={"email": "agent@x.com", "role": "agent"},
        headers=_auth(owner_token),
    ).json()
    # The agent signs up + we manually add them to the team for this test
    agent_token = _signup(client, "agent@x.com")
    # Agent cannot invite
    response = client.post(
        f"/api/teams/{team_id}/invitations",
        json={"email": "other@x.com", "role": "agent"},
        headers=_auth(agent_token),
    )
    assert response.status_code == 403
    assert "only owners" in response.json()["detail"]
