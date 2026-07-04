"""Real Stripe billing adapter — wires the cycle 2 mock to Stripe.

Uses the official `stripe` Python SDK + httpx for the underlying
HTTP transport. In production, set:

    USE_MOCKS=false
    STRIPE_API_KEY=sk_live_...
    STRIPE_WEBHOOK_SECRET=whsec_...

In test mode (`sk_test_...`), no real money is moved. The live smoke
test (RUN_LIVE_BILLING=1) creates a real Checkout session against
Stripe's test infrastructure.

The adapter is intentionally thin: Stripe's SDK is already
well-tested, so we just need to:
1. Translate our domain parameters to Stripe's API
2. Handle errors (Stripe SDK raises its own typed exceptions;
   we wrap them in our domain PlanLimitExceeded where appropriate)
3. Verify webhook signatures using `stripe.Webhook.construct_event`
"""

from __future__ import annotations

import logging
from typing import Any

import stripe
from stripe import StripeError, Webhook

from app.adapters.billing.base import BillingAdapter

logger = logging.getLogger(__name__)


# Map our plan tiers to Stripe price IDs. Operators configure these
# in their Stripe dashboard + .env. Default: None (raises on use).
_PLAN_TO_PRICE: dict[str, str | None] = {
    "starter": None,  # free, no Stripe checkout
    "growth": None,  # set STRIPE_PRICE_GROWTH=price_xxx in .env
    "team": None,  # set STRIPE_PRICE_TEAM=price_xxx
    "enterprise": None,
}


class StripeBillingAdapter(BillingAdapter):
    """Production Stripe adapter using the official SDK."""

    def __init__(
        self,
        api_key: str,
        *,
        webhook_secret: str,
        price_growth: str | None = None,
        price_team: str | None = None,
        http_client: Any = None,
    ) -> None:
        """Initialize with Stripe credentials.

        The Stripe SDK uses its own httpx client internally. We override
        via `http_client` for tests (httpx.MockTransport).
        """
        if not api_key:
            raise ValueError("STRIPE_API_KEY is required for the real billing adapter")
        stripe.api_key = api_key
        if http_client is not None:
            stripe.default_http_client = http_client
        self._api_key = api_key
        self._webhook_secret = webhook_secret
        if price_growth:
            _PLAN_TO_PRICE["growth"] = price_growth
        if price_team:
            _PLAN_TO_PRICE["team"] = price_team

    # ── Checkout ──────────────────────────────────────────────────
    def create_checkout_session(
        self,
        *,
        team_id: str,
        plan: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, str]:
        price_id = _PLAN_TO_PRICE.get(plan)
        if not price_id:
            raise ValueError(
                f"No Stripe price configured for plan {plan!r}. "
                f"Set STRIPE_PRICE_{plan.upper()} in .env."
            )
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"team_id": team_id, "plan": plan},
            )
        except StripeError as exc:
            logger.error("Stripe checkout session failed: %s", exc)
            raise
        return {"url": session.url or "", "session_id": session.id}

    # ── Portal ────────────────────────────────────────────────────
    def create_portal_session(self, *, team_id: str, return_url: str) -> dict[str, str]:
        # 1. Find or create the Stripe customer for this team
        customer_id = self._get_or_create_customer(team_id=team_id)
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
        except StripeError as exc:
            logger.error("Stripe portal session failed: %s", exc)
            raise
        return {"url": session.url, "session_id": session.id}

    # ── Subscription ─────────────────────────────────────────────
    def get_subscription(self, *, subscription_id: str) -> dict[str, Any] | None:
        try:
            sub = stripe.Subscription.retrieve(subscription_id)
        except StripeError as exc:
            logger.error("Stripe subscription retrieve failed: %s", exc)
            raise
        return sub.to_dict() if hasattr(sub, "to_dict") else dict(sub)  # type: ignore[call-overload, unused-ignore]

    # ── Webhook ──────────────────────────────────────────────────
    def verify_webhook_signature(self, *, payload: bytes, signature_header: str) -> dict[str, Any]:
        """Verify the Stripe-Signature header + parse the event.

        Raises ValueError on bad signature. Real-mode: HMAC-SHA256 via
        stripe.Webhook.construct_event.
        """
        try:
            event: Any = Webhook.construct_event(  # type: ignore[no-untyped-call]
                payload, signature_header, self._webhook_secret
            )
        except ValueError as exc:
            raise ValueError(f"invalid Stripe signature: {exc}") from exc
        except StripeError as exc:
            raise ValueError(f"Stripe webhook error: {exc}") from exc
        return event.to_dict() if hasattr(event, "to_dict") else dict(event)

    # ── Helpers ──────────────────────────────────────────────────
    def _get_or_create_customer(self, *, team_id: str) -> str:
        """Find the Stripe customer for this team, or create one.

        In production this is a lookup against the `billing_customers`
        table for `stripe_customer_id`. We keep it simple here by
        searching Stripe directly via the metadata field we set on
        the original checkout session.
        """
        from app.adapters.supabase._factory import get_db
        from app.config import get_settings

        db = get_db(get_settings())
        rows = db.query("billing_customers", filters={"team_id": team_id})
        if rows and rows[0].get("stripe_customer_id"):
            return str(rows[0]["stripe_customer_id"])
        # Create a new customer
        customer = stripe.Customer.create(metadata={"team_id": team_id})
        if rows:
            db.update(
                "billing_customers",
                rows[0]["team_id"],
                {"stripe_customer_id": customer.id},
            )
        else:
            db.insert(
                "billing_customers",
                {
                    "team_id": team_id,
                    "stripe_customer_id": customer.id,
                    "plan": "starter",
                },
            )
        return str(customer.id)
