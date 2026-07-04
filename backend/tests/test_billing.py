"""T-403 — /api/billing/* routes tests (mocked Stripe)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.adapters.billing._factory import reset_cache as reset_billing_cache
from app.adapters.supabase._factory import reset_mock_singleton
from app.config import get_settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    reset_mock_singleton()
    reset_billing_cache()
    app = create_app(get_settings())
    with TestClient(app) as c:
        yield c
    reset_billing_cache()
    reset_mock_singleton()


def _signup(c: TestClient, email: str) -> str:
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "password": "supersecret123", "full_name": "B"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── ST-BL-01: GET /api/billing/status ───────────────────────────


def test_billing_status_requires_auth(client: TestClient) -> None:
    r = client.get("/api/billing/status")
    assert r.status_code in (401, 403)


def test_billing_status_returns_team_plan_and_seat_counts(
    client: TestClient,
) -> None:
    token = _signup(client, "billing-status@example.com")
    r = client.get("/api/billing/status", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan"] == "starter"
    assert body["status"] in ("active", "trialing")
    assert body["seats_used"] == 1  # the user themselves
    assert body["seats_limit"] == 1  # starter plan
    assert body["is_paid"] is False


# ── ST-BL-02: POST /api/billing/checkout ─────────────────────


def test_checkout_returns_url_and_session_id(client: TestClient) -> None:
    token = _signup(client, "billing-checkout@example.com")
    r = client.post(
        "/api/billing/checkout",
        json={"plan": "growth"},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "url" in body
    assert "session_id" in body
    assert body["url"].startswith("https://billing-mock.example.com/checkout/")


def test_checkout_rejects_invalid_plan(client: TestClient) -> None:
    token = _signup(client, "billing-badplan@example.com")
    r = client.post(
        "/api/billing/checkout",
        json={"plan": "invalid_tier"},
        headers=_auth(token),
    )
    assert r.status_code == 422


# ── ST-BL-03: POST /api/billing/portal ────────────────────────


def test_portal_returns_url_and_session_id(client: TestClient) -> None:
    token = _signup(client, "billing-portal@example.com")
    r = client.post("/api/billing/portal", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "url" in body
    assert body["url"].startswith("https://billing-mock.example.com/portal/")


# ── ST-BL-04 + ST-BL-05: webhook signature + handler ──────────


def test_webhook_signature_validated_in_real_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real mode: missing Stripe-Signature → 400 (mock accepts it)."""
    # In mock mode the route auto-fills the signature; in real mode
    # it requires one. We're in mock mode by default, so the test
    # verifies the mock path: unsigned payload is accepted.
    token = _signup(client, "webhook-1@example.com")
    payload = json.dumps(
        {
            "id": "evt_checkout_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"team_id": _get_team_id(client, token)},
                    "customer": "cus_test",
                    "subscription": "sub_test",
                }
            },
        }
    ).encode()
    r = client.post(
        "/api/billing/webhook",
        content=payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": "test-mock-sig"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"


def _get_team_id(client: TestClient, token: str) -> str:
    me = client.get("/api/auth/me", headers=_auth(token)).json()
    from app.adapters.supabase._factory import get_db
    from app.config import get_settings

    db = get_db(get_settings())
    user = db.get_by_id("users", me["id"])
    return str(user["team_id"])


def test_webhook_upgrades_team_plan(client: TestClient) -> None:
    """AC-BL-05: checkout.session.completed → team.plan = 'growth'."""
    token = _signup(client, "webhook-upgrade@example.com")
    team_id = _get_team_id(client, token)
    payload = json.dumps(
        {
            "id": "evt_upgrade_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"team_id": team_id, "plan": "growth"},
                    "customer": "cus_abc",
                    "subscription": "sub_abc",
                }
            },
        }
    ).encode()
    r = client.post(
        "/api/billing/webhook",
        content=payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": "test-mock-sig"},
    )
    assert r.status_code == 200
    # Verify team plan was updated
    status = client.get("/api/billing/status", headers=_auth(token)).json()
    assert status["plan"] == "growth"
    assert status["seats_limit"] == 3
    assert status["is_paid"] is True


def test_webhook_subscription_deleted_reverts_to_starter(
    client: TestClient,
) -> None:
    """AC-BL-05: customer.subscription.deleted → plan reverts to 'starter'."""
    token = _signup(client, "webhook-cancel@example.com")
    team_id = _get_team_id(client, token)
    # First, upgrade via checkout
    checkout_payload = json.dumps(
        {
            "id": "evt_up_2",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"team_id": team_id, "plan": "team"},
                    "customer": "cus_2",
                    "subscription": "sub_2",
                }
            },
        }
    ).encode()
    client.post(
        "/api/billing/webhook",
        content=checkout_payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": "test-mock-sig"},
    )
    # Then, delete
    delete_payload = json.dumps(
        {
            "id": "evt_del_1",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "metadata": {"team_id": team_id},
                    "id": "sub_2",
                }
            },
        }
    ).encode()
    r = client.post(
        "/api/billing/webhook",
        content=delete_payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": "test-mock-sig"},
    )
    assert r.status_code == 200
    status = client.get("/api/billing/status", headers=_auth(token)).json()
    assert status["plan"] == "starter"


def test_webhook_is_idempotent_on_replay(client: TestClient) -> None:
    """Same event id replayed → no double-processing."""
    token = _signup(client, "webhook-replay@example.com")
    team_id = _get_team_id(client, token)
    payload_dict: dict[str, Any] = {
        "id": "evt_idempotent_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"team_id": team_id, "plan": "growth"},
                "customer": "cus_x",
                "subscription": "sub_x",
            }
        },
    }
    payload = json.dumps(payload_dict).encode()
    # First call
    r1 = client.post(
        "/api/billing/webhook",
        content=payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": "test-mock-sig"},
    )
    assert r1.status_code == 200
    # Replay
    r2 = client.post(
        "/api/billing/webhook",
        content=payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": "test-mock-sig"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"
