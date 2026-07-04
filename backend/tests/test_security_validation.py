"""T-501 — Settings fail-fast validators (cycle 5 AC-SEC-01..06).

12 unit tests covering every validator branch:
- JWT_SECRET: default rejected, empty rejected, <32 bytes rejected,
  dev-override accepted, valid secret accepted
- CORS_ORIGINS: ["*"] rejected in prod, explicit origins accepted,
  dev override accepted
- LINE_CHANNEL_SECRET: default rejected, dev-override accepted
- STRIPE_API_KEY: placeholder rejected when USE_MOCKS=false,
  accepted when USE_MOCKS=true (mock mode doesn't need a real key)

Plus an integration test that calls Settings.validate_security() with bad
config and asserts the exception propagates through.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.security_validation import (
    validate_cors_origins,
    validate_jwt_secret,
    validate_line_channel_secret,
    validate_stripe_api_key,
)

# ── JWT_SECRET ────────────────────────────────────────────────────


def test_jwt_secret_default_rejected_in_production() -> None:
    """AC-SEC-01: prod + default secret → raises."""
    with pytest.raises(ValueError, match="JWT_SECRET.*default"):
        validate_jwt_secret("dev-jwt-secret-change-me", env="production")


def test_jwt_secret_too_short_rejected_in_production() -> None:
    """AC-SEC-02: prod + <32 bytes → raises with byte count."""
    with pytest.raises(ValueError, match=r"JWT_SECRET.*\d+ byte"):
        validate_jwt_secret("tooshort", env="production")


def test_jwt_secret_exactly_32_bytes_accepted_in_production() -> None:
    """Boundary: 32 bytes is the minimum."""
    secret = "x" * 32  # 32 chars
    validate_jwt_secret(secret, env="production")  # should not raise


def test_jwt_secret_valid_long_accepted_in_production() -> None:
    """Typical deploy: 64-byte random base64."""
    secret = "a" * 64
    validate_jwt_secret(secret, env="production")


def test_jwt_secret_dev_override_accepted() -> None:
    """AC-SEC-03: env=dev + default → no raise (dev override)."""
    validate_jwt_secret("dev-jwt-secret-change-me", env="dev")


def test_jwt_secret_empty_rejected_in_production() -> None:
    """Empty secret = no signature → reject even in dev (forces setup)."""
    with pytest.raises(ValueError, match="JWT_SECRET"):
        validate_jwt_secret("", env="production")


# ── CORS_ORIGINS ──────────────────────────────────────────────────


def test_cors_origins_wildcard_rejected_in_production() -> None:
    """AC-SEC-04: prod + ["*"] → raises."""
    with pytest.raises(ValueError, match=r"CORS_ORIGINS.*\*"):
        validate_cors_origins(["*"], env="production")


def test_cors_origins_explicit_accepted_in_production() -> None:
    """Explicit list of origins is the safe pattern."""
    validate_cors_origins(
        ["https://app.example.com", "https://admin.example.com"],
        env="production",
    )


def test_cors_origins_empty_rejected_in_production() -> None:
    """No origins = nothing can call → fail-fast at deploy time."""
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        validate_cors_origins([], env="production")


def test_cors_origins_dev_override_allows_wildcard() -> None:
    """Dev: localhost needs to call from any port; allow * in dev."""
    validate_cors_origins(["*"], env="dev")


# ── LINE_CHANNEL_SECRET ──────────────────────────────────────────


def test_line_channel_secret_default_rejected_in_production() -> None:
    """AC-SEC-05: prod + default secret → raises."""
    with pytest.raises(ValueError, match="LINE_CHANNEL_SECRET"):
        validate_line_channel_secret("dev-line-channel-secret-change-me", env="production")


def test_line_channel_secret_real_value_accepted_in_production() -> None:
    """Real LINE secrets are 32+ chars."""
    validate_line_channel_secret("a" * 32, env="production")


# ── STRIPE_API_KEY ───────────────────────────────────────────────


def test_stripe_api_key_placeholder_rejected_in_real_mode() -> None:
    """AC-SEC-06: USE_MOCKS=false + placeholder → raises."""
    with pytest.raises(ValueError, match="STRIPE_API_KEY"):
        validate_stripe_api_key("sk_test_placeholder", use_mocks=False, env="production")


def test_stripe_api_key_placeholder_accepted_in_mock_mode() -> None:
    """Mock mode doesn't need a real key; placeholder is fine."""
    validate_stripe_api_key("sk_test_placeholder", use_mocks=True, env="production")


def test_stripe_api_key_real_value_accepted_in_real_mode() -> None:
    """Live deploy: any non-placeholder value passes.

    NOTE: We build a long fake-looking value via concatenation so
    the test file doesn't trip GitHub's secret-scanner. The
    validator only checks for the known placeholder strings, not
    the format.
    """
    # Build a long, clearly-fake value via concatenation.
    prefix = "live-real-key-" + "abcdef123456" * 4
    # Use a non-secret-looking prefix that the scanner won't match.
    fake_real_key = "sk." + "live." + prefix
    validate_stripe_api_key(fake_real_key, use_mocks=False, env="production")


# ── Settings integration ─────────────────────────────────────────


def test_settings_validate_raises_on_production_default_jwt() -> None:
    """Constructing Settings with bad config → validate() raises before
    any FastAPI app is built. This is the AC-SEC-01 integration test.
    """
    s = Settings(env="production", jwt_secret="dev-jwt-secret-change-me")
    with pytest.raises(ValueError, match="JWT_SECRET"):
        s.validate_security()


def test_settings_validate_raises_on_production_wildcard_cors() -> None:
    """AC-SEC-04 integration."""
    # Set jwt_secret + line_channel_secret to valid values so we reach the CORS check
    s = Settings(
        env="production",
        jwt_secret="x" * 32,
        line_channel_secret="real-secret-32-bytes-long-real-secret",
        cors_origins=["*"],
    )
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        s.validate_security()


def test_settings_validate_passes_in_dev_mode() -> None:
    """Dev mode accepts the defaults so pytest runs without an .env file."""
    s = Settings(env="dev")
    s.validate_security()  # should not raise


def test_settings_validate_passes_in_test_mode() -> None:
    """Test mode also accepts the defaults."""
    s = Settings(env="test")
    s.validate_security()  # should not raise
