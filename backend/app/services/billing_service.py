"""Billing service — orchestrates checkout, webhooks, plan state.

The service is the *single* place that knows how Stripe's state maps
to the team's `plan` field. Routes call into the service; the service
calls into the adapter.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.adapters.billing import BillingAdapter
from app.adapters.supabase import SupabaseAdapter

logger = logging.getLogger(__name__)


# Plan limits — T-401/T-404 reads these. Keep in sync with the pricing
# table in spec.md.
_PLAN_LIMITS: dict[str, dict[str, int]] = {
    "starter": {
        "seats": 1,
        "properties": 5,
        "ai_listings_per_month": 20,
    },
    "growth": {
        "seats": 3,
        "properties": 25,
        "ai_listings_per_month": 200,
    },
    "team": {
        "seats": 10,
        "properties": 100,
        "ai_listings_per_month": 1_000,
    },
    "enterprise": {
        "seats": 1_000,
        "properties": 100_000,
        "ai_listings_per_month": 100_000,
    },
}


def get_plan_limits(plan: str) -> dict[str, int]:
    """Return seat/property/AI caps for the plan.

    Falls back to `starter` for unknown plans (defensive default).
    """
    return _PLAN_LIMITS.get(plan, _PLAN_LIMITS["starter"])


def seats_used(adapter: SupabaseAdapter, *, team_id: UUID) -> int:
    """Count active (left_at IS NULL) members of the team."""
    rows = adapter.query("team_memberships", filters={"team_id": str(team_id)})
    return sum(1 for r in rows if r.get("left_at") is None)


def get_billing_status(adapter: SupabaseAdapter, *, team_id: UUID) -> dict[str, Any]:
    """Return the full billing status for the team.

    Used by `GET /api/billing/status` and as the data source for the
    frontend `/dashboard/billing` page.
    """
    # 1. Get the team's current plan (teams.plan)
    team = adapter.get_by_id("teams", str(team_id))
    if team is None:
        # Auto-create a starter record so the billing page renders
        adapter.insert("billing_customers", {"team_id": str(team_id), "plan": "starter"})
        team = {"plan": "starter"}
    plan = team.get("plan", "starter")

    # 2. Get the billing customer (may not exist for brand-new teams)
    billing_rows = adapter.query("billing_customers", filters={"team_id": str(team_id)})
    billing = billing_rows[0] if billing_rows else {}

    # 3. Compute usage
    used_seats = seats_used(adapter, team_id=team_id)
    limits = get_plan_limits(plan)

    # 4. Build the response
    return {
        "plan": plan,
        "status": billing.get("status", "active"),
        "seats_used": used_seats,
        "seats_limit": limits["seats"],
        "properties_used": 0,  # T-407 will wire this up
        "properties_limit": limits["properties"],
        "ai_listings_used_month": 0,
        "ai_listings_limit_month": limits["ai_listings_per_month"],
        "current_period_end": billing.get("current_period_end"),
        "cancel_at_period_end": billing.get("cancel_at_period_end", False),
        "trial_ends_at": billing.get("trial_ends_at"),
        "is_paid": plan != "starter",
        "is_within_plan_limits": used_seats <= limits["seats"],
    }


def ensure_billing_customer(adapter: SupabaseAdapter, *, team_id: UUID) -> dict[str, Any]:
    """Create a billing_customers row if one doesn't exist yet.

    Idempotent — UNIQUE on team_id enforces the constraint.
    """
    existing = adapter.query("billing_customers", filters={"team_id": str(team_id)})
    if existing:
        return existing[0]
    return adapter.insert("billing_customers", {"team_id": str(team_id), "plan": "starter"})


def start_checkout(
    *,
    adapter: SupabaseAdapter,
    billing: BillingAdapter,
    team_id: UUID,
    plan: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, str]:
    """Create a Stripe Checkout session for upgrading to `plan`."""
    ensure_billing_customer(adapter, team_id=team_id)
    return billing.create_checkout_session(
        team_id=str(team_id),
        plan=plan,
        success_url=success_url,
        cancel_url=cancel_url,
    )


def start_portal(
    *,
    adapter: SupabaseAdapter,
    billing: BillingAdapter,
    team_id: UUID,
    return_url: str,
) -> dict[str, str]:
    """Open the Stripe Customer Portal for the team's billing record."""
    ensure_billing_customer(adapter, team_id=team_id)
    return billing.create_portal_session(team_id=str(team_id), return_url=return_url)


def handle_webhook_event(
    *,
    adapter: SupabaseAdapter,
    billing: BillingAdapter,
    payload: bytes,
    signature_header: str,
) -> dict[str, Any]:
    """Process a Stripe webhook event. Updates billing_customers + team.plan.

    Returns a summary dict for the webhook ack response.
    """
    event = billing.verify_webhook_signature(payload=payload, signature_header=signature_header)
    event_id = event["id"]
    event_type = event["type"]

    # Idempotency: skip if we've already processed this event
    existing = adapter.query("billing_events", filters={"stripe_event_id": event_id})
    if existing and existing[0].get("processed_at") is not None:
        return {
            "status": "duplicate",
            "event_id": event_id,
            "event_type": event_type,
        }

    # Record the event (idempotency-safe via UNIQUE on stripe_event_id)
    data_obj = event.get("data", {}).get("object", {})
    team_id = _extract_team_id(data_obj)
    if existing:
        adapter.update("billing_events", existing[0]["id"], {"processed_at": _now_iso()})
    else:
        adapter.insert(
            "billing_events",
            {
                "team_id": team_id,
                "stripe_event_id": event_id,
                "event_type": event_type,
                "payload": event,
                "processed_at": _now_iso(),
            },
        )

    # Handle specific event types
    if event_type == "checkout.session.completed":
        _handle_checkout_completed(adapter, data_obj)
    elif event_type == "customer.subscription.created":
        _handle_subscription_created(adapter, data_obj)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(adapter, data_obj)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(adapter, data_obj)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(adapter, data_obj)

    return {
        "status": "ok",
        "event_id": event_id,
        "event_type": event_type,
    }


# ── Event handlers ──────────────────────────────────────────


def _extract_team_id(data_obj: dict[str, Any]) -> str | None:
    """Get the team_id from the webhook payload's metadata.

    The Stripe Checkout session + Subscription both have a `metadata`
    dict we set when creating the checkout session. The mock +
    real adapters both support this.
    """
    metadata = data_obj.get("metadata", {}) or {}
    return metadata.get("team_id")


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _plan_from_subscription(sub: dict[str, Any]) -> str:
    """Extract the plan tier from a Stripe subscription object.

    Maps the Stripe price ID → plan tier. In mock mode, the test
    fixture injects the plan directly via the `metadata.plan` field.
    """
    metadata = sub.get("metadata", {}) or {}
    if "plan" in metadata:
        return str(metadata["plan"])
    items = sub.get("items", {}).get("data", []) or sub.get("items", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        # Real adapter will set this via price_id → plan map
        if "starter" in price_id:
            return "starter"
        if "growth" in price_id:
            return "growth"
        if "team" in price_id:
            return "team"
    return "starter"


def _ensure_team_billing(adapter: SupabaseAdapter, team_id: str) -> dict[str, Any]:
    rows = adapter.query("billing_customers", filters={"team_id": team_id})
    if rows:
        return rows[0]
    return adapter.insert("billing_customers", {"team_id": team_id, "plan": "starter"})


def _update_team_plan(adapter: SupabaseAdapter, team_id: str, plan: str) -> None:
    """Sync the team's plan field with the billing record."""
    adapter.update("teams", team_id, {"plan": plan})


def _handle_checkout_completed(adapter: SupabaseAdapter, data_obj: dict[str, Any]) -> None:
    """`checkout.session.completed` — customer has paid; upgrade their plan."""
    team_id = data_obj.get("metadata", {}).get("team_id")
    if not team_id:
        return
    plan = data_obj.get("metadata", {}).get("plan", "starter")
    customer_id = data_obj.get("customer")
    subscription_id = data_obj.get("subscription")
    record = _ensure_team_billing(adapter, team_id)
    adapter.update(
        "billing_customers",
        record["team_id"],
        {
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": subscription_id,
            "plan": plan,
            "status": "active",
        },
    )
    _update_team_plan(adapter, team_id, plan)
    logger.info("billing: team %s upgraded to %s (customer %s)", team_id, plan, customer_id)


def _handle_subscription_created(adapter: SupabaseAdapter, data_obj: dict[str, Any]) -> None:
    team_id = data_obj.get("metadata", {}).get("team_id")
    if not team_id:
        return
    plan = _plan_from_subscription(data_obj)
    record = _ensure_team_billing(adapter, team_id)
    adapter.update(
        "billing_customers",
        record["team_id"],
        {
            "stripe_subscription_id": data_obj.get("id"),
            "plan": plan,
            "status": data_obj.get("status", "active"),
            "current_period_start": _to_iso(data_obj.get("current_period_start")),
            "current_period_end": _to_iso(data_obj.get("current_period_end")),
        },
    )
    _update_team_plan(adapter, team_id, plan)


def _handle_subscription_updated(adapter: SupabaseAdapter, data_obj: dict[str, Any]) -> None:
    team_id = data_obj.get("metadata", {}).get("team_id")
    if not team_id:
        return
    plan = _plan_from_subscription(data_obj)
    record = _ensure_team_billing(adapter, team_id)
    cancel_at_pe = bool(data_obj.get("cancel_at_period_end", False))
    adapter.update(
        "billing_customers",
        record["team_id"],
        {
            "plan": plan,
            "status": data_obj.get("status", record["status"]),
            "current_period_start": _to_iso(data_obj.get("current_period_start")),
            "current_period_end": _to_iso(data_obj.get("current_period_end")),
            "cancel_at_period_end": cancel_at_pe,
        },
    )
    _update_team_plan(adapter, team_id, plan)


def _handle_subscription_deleted(adapter: SupabaseAdapter, data_obj: dict[str, Any]) -> None:
    team_id = data_obj.get("metadata", {}).get("team_id")
    if not team_id:
        return
    record = _ensure_team_billing(adapter, team_id)
    # Downgrade: keep the customer record but flip to starter
    adapter.update(
        "billing_customers",
        record["team_id"],
        {
            "plan": "starter",
            "status": "canceled",
            "cancel_at_period_end": True,
        },
    )
    _update_team_plan(adapter, team_id, "starter")


def _handle_payment_failed(adapter: SupabaseAdapter, data_obj: dict[str, Any]) -> None:
    team_id = data_obj.get("metadata", {}).get("team_id")
    if not team_id:
        return
    record = _ensure_team_billing(adapter, team_id)
    adapter.update(
        "billing_customers",
        record["team_id"],
        {"status": "past_due"},
    )


def _to_iso(epoch: int | None) -> str | None:
    if epoch is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
