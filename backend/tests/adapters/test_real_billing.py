"""T-405 + Cycle 4 review fix — test the REAL billing factory wiring.

C1 review finding: the previous factory ignored Settings and hardcoded
"real-key-placeholder" placeholders. These tests verify:

1. `use_mocks=True` → MockBillingAdapter (existing behavior)
2. `use_mocks=False` + valid Settings → real StripeBillingAdapter with
   the Settings' stripe_api_key, webhook_secret, and price IDs
3. Two adapter instances with different Settings do NOT leak config via
   the previous module-global `_PLAN_TO_PRICE` (now instance state)
"""

from __future__ import annotations

import pytest

from app.adapters.billing import BillingAdapter
from app.adapters.billing._factory import build_billing_adapter, reset_cache
from app.adapters.billing.mock import MockBillingAdapter
from app.adapters.billing.real import StripeBillingAdapter
from app.config import Settings


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_cache()
    yield
    reset_cache()


def test_factory_returns_mock_by_default() -> None:
    s = Settings(use_mocks=True)
    adapter = build_billing_adapter(s)
    assert isinstance(adapter, MockBillingAdapter)
    assert not isinstance(adapter, StripeBillingAdapter)


def test_factory_wires_settings_to_real_adapter() -> None:
    """C1 fix: real adapter is constructed from Settings, not placeholders."""
    s = Settings(
        use_mocks=False,
        stripe_api_key="sk_test_settings_key_abc",
        stripe_webhook_secret="whsec_settings_secret_xyz",
        stripe_price_growth="price_growth_123",
        stripe_price_team="price_team_456",
    )
    adapter = build_billing_adapter(s)

    assert isinstance(adapter, StripeBillingAdapter)
    # State pulled from Settings, not the previous hardcoded placeholder
    assert adapter._api_key == "sk_test_settings_key_abc"  # noqa: SLF001
    assert adapter._webhook_secret == "whsec_settings_secret_xyz"  # noqa: SLF001
    assert adapter._plan_to_price["growth"] == "price_growth_123"  # noqa: SLF001
    assert adapter._plan_to_price["team"] == "price_team_456"  # noqa: SLF001
    assert adapter._plan_to_price["starter"] is None  # noqa: SLF001


def test_factory_raises_without_stripe_key() -> None:
    """A real adapter with no API key should fail loud, not silent."""
    s = Settings(
        use_mocks=False,
        stripe_api_key="",  # empty — invalid
        stripe_webhook_secret="whsec_x",
    )
    with pytest.raises(ValueError, match="STRIPE_API_KEY is required"):
        build_billing_adapter(s)


def test_factory_cache_isolates_settings() -> None:
    """Two different Settings should yield two distinct adapter instances
    with the right config (C1 follow-up: per-instance state, not global).
    """
    s1 = Settings(
        use_mocks=False,
        stripe_api_key="sk_test_aaa",
        stripe_webhook_secret="whsec_aaa",
        stripe_price_growth="price_growth_aaa",
    )
    s2 = Settings(
        use_mocks=False,
        stripe_api_key="sk_test_bbb",
        stripe_webhook_secret="whsec_bbb",
        stripe_price_growth="price_growth_bbb",
    )
    a1 = build_billing_adapter(s1)
    a2 = build_billing_adapter(s2)

    # Same Settings → same adapter (cached). Different Settings → different.
    # In practice, the lru_cache keys on the Settings-derived primitive
    # tuple, so two distinct Settings produce two distinct cache entries.
    assert a1 is not a2
    assert a1._api_key != a2._api_key  # noqa: SLF001
    assert a1._plan_to_price["growth"] != a2._plan_to_price["growth"]  # noqa: SLF001


def test_factory_protocol_compliance() -> None:
    """Both paths satisfy the BillingAdapter Protocol."""
    mock_adapter = build_billing_adapter(Settings(use_mocks=True))
    real_adapter = build_billing_adapter(
        Settings(
            use_mocks=False,
            stripe_api_key="sk_test_xyz",
            stripe_webhook_secret="whsec_xyz",
        )
    )
    assert isinstance(mock_adapter, BillingAdapter)
    assert isinstance(real_adapter, BillingAdapter)
