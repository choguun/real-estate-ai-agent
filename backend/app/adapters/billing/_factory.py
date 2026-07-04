"""Billing adapter factory — USE_MOCKS-driven.

Wires the real Stripe adapter to `Settings.stripe_*` so the adapter
actually works in production. (Cycle 4 review finding C1: the previous
factory ignored Settings and hardcoded "real-key-placeholder".)
"""

from __future__ import annotations

from functools import lru_cache

from app.adapters.billing.base import BillingAdapter
from app.adapters.billing.mock import MockBillingAdapter
from app.adapters.billing.real import StripeBillingAdapter
from app.config import Settings, get_settings


# `_build` takes primitive args (not Settings) so lru_cache can hash
# them. Pydantic Settings is not hashable by default.
@lru_cache(maxsize=1)
def _build(
    use_mocks: bool,
    stripe_api_key: str,
    stripe_webhook_secret: str,
    stripe_price_growth: str = "",
    stripe_price_team: str = "",
) -> BillingAdapter:
    if use_mocks:
        return MockBillingAdapter()
    return StripeBillingAdapter(
        api_key=stripe_api_key,
        webhook_secret=stripe_webhook_secret,
        price_growth=stripe_price_growth or None,
        price_team=stripe_price_team or None,
    )


def build_billing_adapter(settings: Settings | None = None) -> BillingAdapter:
    s = settings or get_settings()
    return _build(
        use_mocks=s.use_mocks,
        stripe_api_key=s.stripe_api_key,
        stripe_webhook_secret=s.stripe_webhook_secret,
        stripe_price_growth=s.stripe_price_growth,
        stripe_price_team=s.stripe_price_team,
    )


def reset_cache() -> None:
    _build.cache_clear()
