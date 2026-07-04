"""T-604 — JWT secret rotation helper (cycle 6 AC-SR-01..05).

4 unit tests covering the rotation contract:

- Token signed with current secret → verify OK
- Token signed with previous secret → verify OK (rollover window)
- Token signed with neither → InvalidTokenError
- Malformed token → InvalidTokenError

Plus integration via `Settings.jwt_secret_previous` wiring + the
validator enforcing ≥32 bytes on it (folded into
test_security_validation.py as a 5th test).
"""

from __future__ import annotations

import time

import jwt
import pytest

from app.config import Settings
from app.secret_rotation import decode_token_rotating
from app.services.auth import create_access_token


def _settings(*, current: str, previous: str = "") -> Settings:
    """Build a Settings with both current + previous JWT secrets."""
    return Settings(
        env="dev",
        jwt_secret=current,
        jwt_secret_previous=previous,
        jwt_ttl_seconds=3600,
    )


# ── AC-SR-01: current secret verifies ──────────────────────────────


def test_decode_token_rotating_accepts_current_secret() -> None:
    """A token signed with the current secret verifies."""
    secret = "x" * 32
    settings = _settings(current=secret)
    token = create_access_token("user-1", "alice@example.com", settings=settings)
    payload = decode_token_rotating(token, settings)
    assert payload["sub"] == "user-1"
    assert payload["email"] == "alice@example.com"


# ── AC-SR-01: previous secret verifies during rollover window ─────


def test_decode_token_rotating_accepts_previous_secret() -> None:
    """During the rollover window, tokens signed with the previous
    secret still verify. This is the whole point of the helper:
    operators rotate `jwt_secret` without logging every user out.
    """
    previous = "p" * 32
    current = "c" * 32
    settings = _settings(current=current, previous=previous)
    # Issue a token with the previous secret (simulating "before rotation")
    payload_dict = {
        "sub": "user-2",
        "email": "bob@example.com",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "jti": "test-jti",
        "iss": "test",
    }
    token = jwt.encode(payload_dict, previous, algorithm="HS256")
    # Verify with the rotation helper — must succeed even though
    # settings.jwt_secret is now `current`
    decoded = decode_token_rotating(token, settings)
    assert decoded["sub"] == "user-2"


# ── AC-SR-02: token signed with neither secret is rejected ─────────


def test_decode_token_rotating_rejects_unknown_secret() -> None:
    """Tokens signed with a secret not in {current, previous} raise."""
    unknown = "u" * 32
    current = "c" * 32
    previous = "p" * 32
    settings = _settings(current=current, previous=previous)
    payload_dict = {
        "sub": "user-3",
        "email": "eve@example.com",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload_dict, unknown, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token_rotating(token, settings)


# ── AC-SR-02: malformed token is rejected ───────────────────────────


def test_decode_token_rotating_rejects_malformed_token() -> None:
    """A garbage token raises InvalidTokenError (or a subclass)."""
    settings = _settings(current="x" * 32)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token_rotating("not-a-real-jwt", settings)


# ── AC-SR-05: validator enforces ≥32 bytes on jwt_secret_previous ──


def test_validator_rejects_short_jwt_secret_previous_in_production() -> None:
    """The cycle-5 validator is extended: if jwt_secret_previous
    is set in non-dev environments, it must be ≥32 bytes.
    """
    base = {
        "env": "production",
        "jwt_secret": "x" * 32,
        "line_channel_secret": "real-line-secret-32-bytes-long-1234",
        "cors_origins": ["https://app.example.com"],
    }
    s = Settings(**base, jwt_secret_previous="short")
    with pytest.raises(ValueError, match="JWT_SECRET_PREVIOUS"):
        s.validate_security()


def test_validator_accepts_long_jwt_secret_previous_in_production() -> None:
    """A 32+ byte previous secret passes the validator."""
    base = {
        "env": "production",
        "jwt_secret": "x" * 32,
        "line_channel_secret": "real-line-secret-32-bytes-long-1234",
        "cors_origins": ["https://app.example.com"],
    }
    s = Settings(**base, jwt_secret_previous="p" * 32)
    s.validate_security()  # should not raise


def test_validator_allows_empty_jwt_secret_previous() -> None:
    """Empty previous secret means 'no rotation in progress' — OK."""
    base = {
        "env": "production",
        "jwt_secret": "x" * 32,
        "line_channel_secret": "real-line-secret-32-bytes-long-1234",
        "cors_origins": ["https://app.example.com"],
    }
    s = Settings(**base, jwt_secret_previous="")
    s.validate_security()  # should not raise
