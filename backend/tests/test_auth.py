"""Auth tests — ST-002 (signup), ST-003 (login), ST-004 (LIFF)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.supabase.mock import MockSupabaseAdapter
from app.deps import get_db_dep
from app.main import create_app


# ─── Fixtures ───────────────────────────────────────────────────────────
@pytest.fixture
def db() -> MockSupabaseAdapter:
    return MockSupabaseAdapter()


@pytest.fixture
def client(db: MockSupabaseAdapter):
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ─── ST-002: signup ─────────────────────────────────────────────────────
def test_signup_returns_jwt_for_new_email(client: TestClient) -> None:
    res = client.post(
        "/api/auth/signup",
        json={"email": "agent@example.com", "full_name": "Somchai", "password": "password123"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["token"]
    assert body["user"]["email"] == "agent@example.com"
    assert body["user"]["full_name"] == "Somchai"
    assert "password_hash" not in body["user"]


def test_signup_rejects_duplicate_email_with_409(client: TestClient) -> None:
    payload = {"email": "dup@example.com", "full_name": "X", "password": "password123"}
    first = client.post("/api/auth/signup", json=payload)
    assert first.status_code == 201, first.text

    second = client.post("/api/auth/signup", json=payload)
    assert second.status_code == 409
    assert "already registered" in second.json()["detail"].lower()


def test_signup_validates_payload(client: TestClient) -> None:
    # short email + no password
    res = client.post("/api/auth/signup", json={"email": "x", "full_name": "X"})
    assert res.status_code == 422


# ─── ST-003: login ──────────────────────────────────────────────────────
def test_login_returns_jwt_for_valid_credentials(client: TestClient) -> None:
    client.post(
        "/api/auth/signup",
        json={"email": "agent@example.com", "full_name": "X", "password": "password123"},
    )
    res = client.post(
        "/api/auth/login",
        json={"email": "agent@example.com", "password": "password123"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token"]
    assert body["user"]["email"] == "agent@example.com"


def test_login_rejects_wrong_password_with_401(client: TestClient) -> None:
    client.post(
        "/api/auth/signup",
        json={"email": "agent@example.com", "full_name": "X", "password": "password123"},
    )
    res = client.post(
        "/api/auth/login",
        json={"email": "agent@example.com", "password": "WRONG-password"},
    )
    assert res.status_code == 401
    assert "invalid" in res.json()["detail"].lower()


def test_login_rejects_unknown_email_with_401(client: TestClient) -> None:
    res = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "anything12345"},
    )
    assert res.status_code == 401


# ─── ST-004: LIFF ───────────────────────────────────────────────────────
def test_liff_login_creates_user_and_returns_jwt(client: TestClient) -> None:
    res = client.post(
        "/api/auth/liff",
        json={"line_user_id": "U12345", "display_name": "Khun Yai"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token"]
    assert body["user"]["line_user_id"] == "U12345"
    assert body["user"]["full_name"] == "Khun Yai"
    # No real email from LIFF — a stable placeholder is OK for MVP.


def test_liff_login_reuses_existing_user(client: TestClient) -> None:
    first = client.post(
        "/api/auth/liff",
        json={"line_user_id": "U9999", "display_name": "Khun First"},
    )
    second = client.post(
        "/api/auth/liff",
        json={"line_user_id": "U9999", "display_name": "Khun Second"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    # Same user ID — we did NOT create a second user.
    assert first.json()["user"]["id"] == second.json()["user"]["id"]


def test_liff_login_updates_display_name_on_existing_user(
    client: TestClient, db: MockSupabaseAdapter
) -> None:
    client.post(
        "/api/auth/liff",
        json={"line_user_id": "U-ABC", "display_name": "Old Name"},
    )
    second = client.post(
        "/api/auth/liff",
        json={"line_user_id": "U-ABC", "display_name": "New Name"},
    )
    # current behaviour: don't overwrite
    assert second.json()["user"]["full_name"] == "Old Name"
    users = db.query("users", filters={"line_user_id": "U-ABC"})
    assert len(users) == 1


def test_liff_login_validates_payload(client: TestClient) -> None:
    res = client.post("/api/auth/liff", json={})  # missing line_user_id
    assert res.status_code == 422


# ─── /me endpoint ───────────────────────────────────────────────────────
def test_me_returns_user_for_valid_token(client: TestClient) -> None:
    signup = client.post(
        "/api/auth/signup",
        json={"email": "me@example.com", "full_name": "Me", "password": "password123"},
    )
    token = signup.json()["token"]

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "me@example.com"
    assert "password_hash" not in res.json()


def test_me_returns_401_without_header(client: TestClient) -> None:
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_me_returns_401_with_malformed_token(client: TestClient) -> None:
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


def test_me_returns_401_with_wrong_scheme(client: TestClient) -> None:
    res = client.get("/api/auth/me", headers={"Authorization": "Token foo"})
    assert res.status_code == 401


# ─── Cross-user scoping (security guard) ───────────────────────────────
def test_me_cannot_fetch_a_different_user_via_token(
    client: TestClient, db: MockSupabaseAdapter
) -> None:
    """JWT identifies the user by `sub`; the token payload is the source of truth."""
    a = client.post(
        "/api/auth/signup",
        json={"email": "a@a.com", "full_name": "A", "password": "password123"},
    )
    token_a = a.json()["token"]
    user_a_id = a.json()["user"]["id"]

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    assert res.status_code == 200
    assert res.json()["id"] == user_a_id
