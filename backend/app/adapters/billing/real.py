"""Real Stripe billing adapter stub. Wired in T-405 (httpx + stripe SDK)."""

from __future__ import annotations

from typing import Any


class StripeBillingAdapter:
    """Stub — full Stripe wiring lands in T-405."""

    def __init__(self, api_key: str, *, webhook_secret: str) -> None:
        self._api_key = api_key
        self._webhook_secret = webhook_secret

    def create_checkout_session(self, **kw: Any) -> Any:
        raise NotImplementedError(
            "StripeBillingAdapter wired in T-405. " "Set use_mocks=true (default) for local dev."
        )

    def create_portal_session(self, **kw: Any) -> Any:
        raise NotImplementedError(
            "StripeBillingAdapter wired in T-405. " "Set use_mocks=true (default) for local dev."
        )

    def get_subscription(self, **kw: Any) -> Any:
        raise NotImplementedError(
            "StripeBillingAdapter wired in T-405. " "Set use_mocks=true (default) for local dev."
        )

    def verify_webhook_signature(self, **kw: Any) -> Any:
        raise NotImplementedError(
            "StripeBillingAdapter wired in T-405. " "Set use_mocks=true (default) for local dev."
        )
