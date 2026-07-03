"""T-307 — Invite accept flow + email mock."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _signup(client: TestClient, email: str) -> str:
    r = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "supersecret123", "full_name": "I"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_invite_email_is_sent_to_invitee() -> None:
    """ST-MT-08: invite creates a row + sends an email (mock logs)."""
    from app.adapters.email import build_email_adapter
    from app.config import get_settings

    client = _client()
    token = _signup(client, "owner-inv@example.com")
    client.post("/api/teams", json={"name": "Invite Test"}, headers=_auth(token))

    # Create a fresh email adapter (with empty sent list) to inspect
    email_svc = build_email_adapter(get_settings())
    email_svc.reset()  # in case the global state had any

    # Re-create the app with a dependency override so the test sees this email adapter
    from app.deps import get_email
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_email] = lambda: email_svc
    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/signup",
            json={
                "email": "owner-inv-2@example.com",
                "password": "supersecret123",
                "full_name": "I",
            },
        ).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        t = c.post(
            "/api/teams", json={"name": "Invite Test"}, headers={"Authorization": f"Bearer {tok}"}
        ).json()
        r = c.post(
            f"/api/teams/{t['id']}/invitations",
            json={"email": "alice@example.com", "role": "agent"},
        )
    assert r.status_code == 201, r.text
    # Check the mock recorded the email
    assert any(e["to"] == "alice@example.com" and "/invite/" in e["body"] for e in email_svc.sent)


def test_invite_token_is_high_entropy() -> None:
    """ST-MT-08: token must be ≥32 bytes entropy (URL-safe base64)."""
    import re

    client = _client()
    token = _signup(client, "owner-tok@example.com")
    team = client.post("/api/teams", json={"name": "TokTest"}, headers=_auth(token)).json()
    response = client.post(
        f"/api/teams/{team['id']}/invitations",
        json={"email": "x@x.com"},
        headers=_auth(token),
    )
    assert response.status_code == 201
    tok = response.json()["token"]
    assert len(tok) >= 32
    assert not re.match(r"^[a-z]+$", tok)  # not easily guessable


def test_accept_invite_creates_user_and_returns_jwt() -> None:
    """ST-MT-09: accept flow creates a new user + adds to team + returns JWT."""
    client = _client()
    owner_token = _signup(client, "owner-acc@example.com")
    team = client.post("/api/teams", json={"name": "AcceptTest"}, headers=_auth(owner_token)).json()

    # Owner invites
    invite = client.post(
        f"/api/teams/{team['id']}/invitations",
        json={"email": "newbie@example.com", "role": "agent"},
        headers=_auth(owner_token),
    ).json()
    token = invite["token"]

    # Newbie accepts (no existing account → password required)
    response = client.post(
        f"/api/teams/invitations/{token}/accept",
        json={"password": "supersecret123", "full_name": "Newbie"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["team_id"] == team["id"]
    assert body["user"]["email"] == "newbie@example.com"

    # Verify the new user is now a member
    members = client.get(f"/api/teams/{team['id']}/members", headers=_auth(owner_token)).json()
    emails = {m["email"] for m in members}
    assert "newbie@example.com" in emails
    newbie_member = next(m for m in members if m["email"] == "newbie@example.com")
    assert newbie_member["role"] == "agent"


def test_accept_invite_reuses_existing_user() -> None:
    """If the invitee already has an account, accept adds them to the team."""
    client = _client()
    owner_token = _signup(client, "owner-reuse@example.com")
    _signup(client, "existing@example.com")  # pre-create user
    team = client.post("/api/teams", json={"name": "Reuse"}, headers=_auth(owner_token)).json()

    invite = client.post(
        f"/api/teams/{team['id']}/invitations",
        json={"email": "existing@example.com", "role": "agent"},
        headers=_auth(owner_token),
    ).json()

    # Existing user accepts (no password — they already have one)
    response = client.post(f"/api/teams/invitations/{invite['token']}/accept", json={})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "existing@example.com"


def test_accept_invite_rejects_invalid_token() -> None:
    client = _client()
    response = client.post("/api/teams/invitations/no-such-token/accept", json={})
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


def test_accept_invite_rejects_double_use() -> None:
    """ST-MT-09: 410 Gone on second accept."""
    client = _client()
    owner_token = _signup(client, "owner-double@example.com")
    team = client.post("/api/teams", json={"name": "Double"}, headers=_auth(owner_token)).json()
    invite = client.post(
        f"/api/teams/{team['id']}/invitations",
        json={"email": "x2@x.com", "role": "agent"},
        headers=_auth(owner_token),
    ).json()

    # First accept succeeds
    r1 = client.post(
        f"/api/teams/invitations/{invite['token']}/accept",
        json={"password": "supersecret123", "full_name": "X"},
    )
    assert r1.status_code == 200
    # Second accept: 410 Gone
    r2 = client.post(f"/api/teams/invitations/{invite['token']}/accept", json={})
    assert r2.status_code == 410


def test_accept_invite_for_liff_user_sets_password() -> None:
    """LIFF users have no password yet; the accept form must supply one."""
    from app.adapters.supabase._factory import get_db
    from app.config import get_settings

    client = _client()
    owner_token = _signup(client, "owner-liff-acc@example.com")
    team = client.post("/api/teams", json={"name": "LiffAcc"}, headers=_auth(owner_token)).json()

    # Create a LIFF user (no password)
    db = get_db(get_settings())
    db.insert(
        "users",
        {
            "email": "liff-user@example.com",
            "full_name": "LIFF User",
            "password_hash": "",
            "line_user_id": "U-liff-test",
        },
    )

    invite = client.post(
        f"/api/teams/{team['id']}/invitations",
        json={"email": "liff-user@example.com", "role": "agent"},
        headers=_auth(owner_token),
    ).json()

    # Accept with a new password
    r = client.post(
        f"/api/teams/invitations/{invite['token']}/accept",
        json={"password": "new-password-1234"},
    )
    assert r.status_code == 200
    # And the user's password is now hashed (non-empty)
    user_rows = db.query("users", filters={"email": "liff-user@example.com"})
    assert user_rows[0]["password_hash"]  # non-empty
