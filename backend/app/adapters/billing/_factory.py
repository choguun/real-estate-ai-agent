"""Billing adapter factory — USE_MOCKS-driven."""

from __future__ import annotations

from functools import lru_cache

from app.adapters.billing.base import BillingAdapter
from app.adapters.billing.mock import MockBillingAdapter
from app.adapters.billing.real import StripeBillingAdapter
from app.config import Settings, get_settings


@lru_cache(maxsize=1)
def _build(use_mocks: bool) -> BillingAdapter:
    if use_mocks:
        return MockBillingAdapter()
    return StripeBillingAdapter(
        api_key="real-key-placeholder",
        webhook_secret="real-webhook-secret-placeholder",
    )


def build_billing_adapter(settings: Settings | None = None) -> BillingAdapter:
    s = settings or get_settings()
    return _build(s.use_mocks)


def reset_cache() -> None:
    _build.cache_clear()
