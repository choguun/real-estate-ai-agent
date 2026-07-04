"""Billing adapter Protocol — Stripe abstraction for the rest of the app.

Two implementations:
- MockBillingAdapter (dev/test): records every call in-memory, returns
  stub URLs, signs no-op webhooks. CI never hits Stripe.
- StripeBillingAdapter (prod): wraps the stripe SDK + httpx. Implemented
  in T-405.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BillingAdapter(Protocol):
    """The single interface the rest of the app uses to bill customers."""

    def create_checkout_session(
        self,
        *,
        team_id: str,
        plan: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, str]:
        """Create a Stripe Checkout session for upgrading to `plan`.

        Returns:
            {"url": str, "session_id": str}. The URL is a hosted checkout
            where the user enters card details. The session_id is stored
            for later correlation with webhooks.

        Mock returns a stub URL like ``https://billing-mock.example.com
        /checkout/{token}``.
        """
        ...

    def create_portal_session(self, *, team_id: str, return_url: str) -> dict[str, str]:
        """Create a Stripe Billing Portal session for self-service.

        Lets the user update payment methods, view invoices, cancel
        their subscription. Returns ``{"url": str, "session_id": str}``.
        """
        ...

    def get_subscription(self, *, subscription_id: str) -> dict[str, Any] | None:
        """Return the current subscription state, or None if canceled/deleted.

        Shape (Stripe API):
            {"id", "status", "current_period_start", "current_period_end",
             "cancel_at_period_end", "items": [{"price": {"id": "..."}}]}

        Mock returns a deterministic state.
        """
        ...

    def verify_webhook_signature(self, *, payload: bytes, signature_header: str) -> dict[str, Any]:
        """Verify a Stripe webhook signature + parse the event.

        Args:
            payload: Raw request bytes (BEFORE any JSON parsing).
            signature_header: Value of the ``Stripe-Signature`` header.

        Returns:
            Parsed event dict (Stripe Event shape: ``{"id", "type", "data": {...}}``).

        Raises:
            ValueError: If the signature is invalid.
        """
        ...
