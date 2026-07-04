"""T-401 — billing_customers + billing_events schema tests.

Verifies:
- BILLING_CUSTOMERS table is in the mock schema
- billing_customers has the right columns + defaults
- team_id is the PK (UNIQUE on (team_id))
- stripe_customer_id is UNIQUE
- Insert + get + update works
- billing_events has stripe_event_id UNIQUE (replay protection)
"""

from __future__ import annotations

import pytest

from app.adapters.supabase._factory import get_db, reset_mock_singleton
from app.config import get_settings


@pytest.fixture
def db():
    reset_mock_singleton()
    yield get_db(get_settings())
    reset_mock_singleton()


def test_billing_customers_is_in_schema(db) -> None:
    """T-401: the new table is declared in _schema.py."""
    assert "billing_customers" in db.schema.table_names
    assert "billing_events" in db.schema.table_names


def test_billing_customers_columns_present(db) -> None:
    table = db.schema.get("billing_customers")
    expected = {
        "team_id",
        "stripe_customer_id",
        "stripe_subscription_id",
        "plan",
        "status",
        "current_period_start",
        "current_period_end",
        "cancel_at_period_end",
        "trial_ends_at",
        "created_at",
        "updated_at",
    }
    actual = {c.name for c in table.columns}
    assert expected.issubset(actual), f"missing columns: {expected - actual}"


def test_billing_customers_plan_defaults_to_starter(db) -> None:
    """T-401: new row's plan defaults to 'starter'."""
    row = db.insert("billing_customers", {"team_id": "00000000-0000-0000-0000-000000000001"})
    assert row["plan"] == "starter"
    assert row["status"] == "trialing"  # default in schema


def test_billing_customers_unique_on_stripe_customer_id(db) -> None:
    """T-401: stripe_customer_id is UNIQUE (enforced by mock + real)."""
    db.insert("billing_customers", {"stripe_customer_id": "cus_abc"})  # noqa: F841
    with pytest.raises(ValueError, match="UNIQUE"):
        db.insert("billing_customers", {"stripe_customer_id": "cus_abc"})


def test_billing_customers_team_id_unique(db) -> None:
    """T-401: one billing record per team (PK)."""
    db.insert("billing_customers", {"team_id": "team-1"})
    with pytest.raises(ValueError, match="UNIQUE"):
        db.insert("billing_customers", {"team_id": "team-1"})


def test_billing_events_unique_on_stripe_event_id(db) -> None:
    """T-401: webhook idempotency — replay of same Stripe event is a no-op."""
    db.insert(
        "billing_events",
        {"stripe_event_id": "evt_001", "event_type": "checkout.completed", "payload": {}},
    )
    with pytest.raises(ValueError, match="UNIQUE"):
        db.insert(
            "billing_events",
            {"stripe_event_id": "evt_001", "event_type": "checkout.completed", "payload": {}},
        )


def test_billing_customers_update(db) -> None:
    """T-401: webhook can update plan + status fields.

    Update by row["id"] (mock indexes by 'id' regardless of table PK).
    Real Postgres: UPDATE billing_customers SET ... WHERE team_id = ...
    """
    row = db.insert("billing_customers", {"team_id": "team-1"})
    updated = db.update(
        "billing_customers",
        row["id"],
        {"plan": "growth", "status": "active", "stripe_customer_id": "cus_xyz"},
    )
    assert updated is not None
    assert updated["plan"] == "growth"
    assert updated["status"] == "active"
    assert updated["stripe_customer_id"] == "cus_xyz"
    assert updated["updated_at"] != row["updated_at"]  # re-stamped


def test_teams_plan_limits_column_added() -> None:
    """T-401: teams.plan_limits JSONB column was added (for cheap plan-limit reads)."""
    from app.adapters.supabase._schema import TEAMS

    assert TEAMS.has("plan_limits")
