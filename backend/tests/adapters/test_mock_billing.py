"""T-402 — BillingAdapter mock tests.

Covers:
- Protocol compliance (mock + future real satisfy the shape)
- create_checkout_session returns stub URL + session_id
- create_portal_session returns stub URL + session_id
- get_subscription returns None for unknown
- verify_webhook_signature parses JSON + dedupes by event id
- Idempotency: replay → no-op
- seed_subscription helper works for downstream tests
"""

from __future__ import annotations

import json

import pytest

from app.adapters.billing import (
    BillingAdapter,
    MockBillingAdapter,
    build_billing_adapter,
)
from app.adapters.billing import reset_cache as reset_billing_cache
from app.adapters.supabase._factory import reset_mock_singleton
from app.config import get_settings


@pytest.fixture
def billing() -> MockBillingAdapter:
    reset_mock_singleton()
    reset_billing_cache()
    yield build_billing_adapter(get_settings())  # type: ignore[misc]
    reset_billing_cache()
    reset_mock_singleton()


# ── Protocol compliance ──────────────────────────────────────


def test_mock_satisfies_protocol(billing: MockBillingAdapter) -> None:
    assert isinstance(billing, BillingAdapter)


def test_build_billing_adapter_returns_mock_by_default(billing: MockBillingAdapter) -> None:
    """USE_MOCKS=true (default) → MockBillingAdapter."""
    assert isinstance(billing, MockBillingAdapter)


# ── Checkout ──────────────────────────────────────────────


def test_create_checkout_session_returns_url_and_session_id(billing: MockBillingAdapter) -> None:
    result = billing.create_checkout_session(
        team_id="team-1",
        plan="growth",
        success_url="https://app.example.com/dashboard/billing?upgrade=success",
        cancel_url="https://app.example.com/dashboard/billing",
    )
    assert "url" in result
    assert "session_id" in result
    assert result["url"].startswith("https://billing-mock.example.com/checkout/")
    assert result["session_id"].startswith("mock_cs_")
    # Session is recorded
    assert result["session_id"] in billing.sessions
    session = billing.sessions[result["session_id"]]
    assert session["team_id"] == "team-1"
    assert session["plan"] == "growth"


def test_create_checkout_session_idempotency(billing: MockBillingAdapter) -> None:
    """Each checkout call gets a unique session_id."""
    r1 = billing.create_checkout_session(
        team_id="t", plan="starter", success_url="x", cancel_url="y"
    )
    r2 = billing.create_checkout_session(
        team_id="t", plan="starter", success_url="x", cancel_url="y"
    )
    assert r1["session_id"] != r2["session_id"]
    assert len(billing.sessions) == 2


# ── Portal ───────────────────────────────────────────────


def test_create_portal_session(billing: MockBillingAdapter) -> None:
    result = billing.create_portal_session(
        team_id="team-1", return_url="https://app.example.com/dashboard/billing"
    )
    assert "url" in result
    assert "session_id" in result
    assert result["url"].startswith("https://billing-mock.example.com/portal/")
    assert result["session_id"].startswith("mock_ps_")


# ── Subscription ────────────────────────────────────────


def test_get_subscription_returns_none_for_unknown(billing: MockBillingAdapter) -> None:
    assert billing.get_subscription(subscription_id="sub_does_not_exist") is None


def test_get_subscription_returns_seeded_state(billing: MockBillingAdapter) -> None:
    billing.seed_subscription(subscription_id="sub_test", team_id="team-1", plan="growth")
    sub = billing.get_subscription(subscription_id="sub_test")
    assert sub is not None
    assert sub["id"] == "sub_test"
    assert sub["plan"] == "growth"
    assert sub["status"] == "active"


# ── Webhook ─────────────────────────────────────────────


def test_verify_webhook_signature_parses_json(billing: MockBillingAdapter) -> None:
    payload = json.dumps(
        {
            "id": "evt_test_1",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_abc", "customer": "cus_xyz"}},
        }
    ).encode("utf-8")
    event = billing.verify_webhook_signature(payload=payload, signature_header="mock-sig")
    assert event["id"] == "evt_test_1"
    assert event["type"] == "checkout.session.completed"


def test_verify_webhook_signature_idempotent(billing: MockBillingAdapter) -> None:
    """Replay of the same event returns the cached event (no double-processing)."""
    payload = json.dumps({"id": "evt_dup", "type": "invoice.payment_succeeded", "data": {}}).encode(
        "utf-8"
    )
    e1 = billing.verify_webhook_signature(payload=payload, signature_header="x")
    e2 = billing.verify_webhook_signature(payload=payload, signature_header="x")
    assert e1 == e2
    assert len(billing.events) == 1


def test_verify_webhook_signature_rejects_invalid_json(billing: MockBillingAdapter) -> None:
    with pytest.raises(ValueError, match="invalid JSON"):
        billing.verify_webhook_signature(payload=b"not json at all", signature_header="x")


def test_verify_webhook_signature_rejects_missing_id(billing: MockBillingAdapter) -> None:
    bad = json.dumps({"type": "noop", "data": {}}).encode("utf-8")
    with pytest.raises(ValueError, match="missing 'id'"):
        billing.verify_webhook_signature(payload=bad, signature_header="x")
