"""Settings validators — cycle 5 T-501 (AC-SEC-01..06).

Pure validator functions that fail-fast when insecure defaults
are present in non-dev environments. Each validator:
1. Takes the value + the relevant context (env, use_mocks flag).
2. Returns None on success.
3. Raises `ValueError` with a remediation message on failure.

These are called from `Settings.validate()` in `app/config.py`,
which is in turn called from `create_app()` in `app/main.py`
before FastAPI is constructed — so a misconfigured prod deploy
exits before binding to a port.

Cycle 4 review critical C3 (deferred to cycle 5):
- JWT_SECRET default ships silently
- CORS_ORIGINS=["*"] ships silently
- LINE_CHANNEL_SECRET default ships silently
- STRIPE_API_KEY placeholder accepted when USE_MOCKS=false

The dev/test override accepts the defaults so:
- `pytest` runs without an .env file
- `uvicorn app.main:app` in dev mode works locally
- CI builds don't fail on missing env vars
"""

from __future__ import annotations

# Minimum JWT secret length (RFC 7518 §3.2: "A key of the same size as
# the hash output (for instance, 256 bits for "HS256") or larger MUST
# be used"). 32 bytes = 256 bits.
_MIN_JWT_SECRET_BYTES = 32

# Known insecure default values — these are the placeholders shipped
# in `.env.example` and the dev defaults in `Settings`.
_INSECURE_JWT_DEFAULT = "dev-jwt-secret-change-me"
_INSECURE_LINE_DEFAULT = "dev-line-channel-secret-change-me"
_INSECURE_STRIPE_PLACEHOLDERS = frozenset(
    {
        "",
        "sk_test_placeholder",
        "sk_live_placeholder",
    }
)


def _is_dev_or_test(env: str) -> bool:
    """True if the env allows insecure defaults for local development.

    `dev`, `test`, and any env starting with `dev-` or `test-`
    (e.g., `dev-jane-laptop`, `test-staging`) get the override.
    Production / staging / preview / any other env must pass full
    validation.
    """
    e = env.lower()
    return e == "dev" or e == "test" or e.startswith("dev-") or e.startswith("test-")


def validate_jwt_secret(value: str, *, env: str) -> None:
    """Raise ValueError if the JWT secret is unsafe for `env`.

    Args:
        value: The candidate `JWT_SECRET` string.
        env: The current `ENV` value (`dev`, `test`, `production`, ...).

    Raises:
        ValueError: If the secret is empty, equals the dev default
            in non-dev environments, or is shorter than 32 bytes.

    Production requirement: ≥32 bytes, not the default, not empty.
    """
    if _is_dev_or_test(env):
        # Dev override: accept any value so local + CI work without setup.
        # Explicitly note this in the error message so it's clear why
        # an empty secret would still pass in dev.
        return
    if not value:
        raise ValueError(
            "JWT_SECRET is empty; refusing to start. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )
    if value == _INSECURE_JWT_DEFAULT:
        raise ValueError(
            f"JWT_SECRET is set to the default value ({_INSECURE_JWT_DEFAULT!r}); "
            "refusing to start in a non-dev environment. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )
    byte_len = len(value.encode("utf-8"))
    if byte_len < _MIN_JWT_SECRET_BYTES:
        raise ValueError(
            f"JWT_SECRET must be at least {_MIN_JWT_SECRET_BYTES} bytes "
            f"(RFC 7518 §3.2 for HS256); got {byte_len} byte"
            f"{'s' if byte_len != 1 else ''}. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )


def validate_cors_origins(origins: list[str], *, env: str) -> None:
    """Raise ValueError if CORS origins are unsafe for `env`.

    Args:
        origins: The candidate `CORS_ORIGINS` list.
        env: The current `ENV` value.

    Raises:
        ValueError: If `origins` is empty, or contains `["*"]`
            in a non-dev environment.

    Production requirement: explicit list of allowed origins.
    The `["*"]` wildcard allows any browser to call authenticated
    endpoints, which is a CSRF vector.
    """
    if _is_dev_or_test(env):
        return
    if not origins:
        raise ValueError(
            "CORS_ORIGINS is empty; refusing to start. "
            "Set CORS_ORIGINS to a list of allowed origins, e.g. "
            'CORS_ORIGINS=["https://app.example.com"]'
        )
    if "*" in origins:
        raise ValueError(
            "CORS_ORIGINS contains '*'; refusing to start in a non-dev environment. "
            "Wildcard CORS with credentials is a CSRF vector. "
            "Set CORS_ORIGINS to a list of allowed origins, e.g. "
            'CORS_ORIGINS=["https://app.example.com","https://admin.example.com"]'
        )


def validate_line_channel_secret(value: str, *, env: str) -> None:
    """Raise ValueError if the LINE channel secret is unsafe for `env`.

    Args:
        value: The candidate `LINE_CHANNEL_SECRET` string.
        env: The current `ENV` value.

    Raises:
        ValueError: If the secret equals the dev default in non-dev
            environments. LINE secrets are 32+ bytes; we don't enforce
            a minimum because real LINE secrets vary in length.

    Production requirement: not the default.
    """
    if _is_dev_or_test(env):
        return
    if value == _INSECURE_LINE_DEFAULT:
        raise ValueError(
            f"LINE_CHANNEL_SECRET is set to the default value "
            f"({_INSECURE_LINE_DEFAULT!r}); refusing to start in a non-dev environment. "
            "Set it from your LINE Official Account Manager console."
        )


def validate_stripe_api_key(value: str, *, use_mocks: bool, env: str) -> None:
    """Raise ValueError if the Stripe API key is unsafe for `env`.

    Args:
        value: The candidate `STRIPE_API_KEY` string.
        use_mocks: The `USE_MOCKS` flag. When True, mocks are used and
            Stripe is never called, so any value (including the
            placeholder) is fine.
        env: The current `ENV` value.

    Raises:
        ValueError: If `use_mocks=False` and `value` is a known
            placeholder or empty.

    Production + real-mode requirement: a real `sk_live_...` or
    `sk_test_...` key. The placeholder is rejected because it
    would cause silent webhook-verification failures against Stripe.
    """
    if _is_dev_or_test(env):
        return
    if use_mocks:
        # Mock mode never calls Stripe, so the key is unused.
        return
    if value in _INSECURE_STRIPE_PLACEHOLDERS:
        raise ValueError(
            f"STRIPE_API_KEY is set to the placeholder ({value!r}) "
            "while USE_MOCKS=false; refusing to start. "
            "Get a real key at https://dashboard.stripe.com/apikeys "
            "and set STRIPE_API_KEY=sk_test_... or sk_live_..."
        )
    # Otherwise assume it's a real key. We don't validate the format
    # further because Stripe's key format may change.


def validate_jwt_secret_previous(value: str, *, env: str) -> None:
    """Raise ValueError if the previous JWT secret is unsafe for `env`.

    Used during the rollover window (cycle 6 T-604). An empty
    string means "no rotation in progress" and is always OK.
    A non-empty value must be ≥ 32 bytes — same standard as the
    primary `JWT_SECRET`.

    Why a separate validator: the cycle-5 `validate_jwt_secret`
    is keyed on `jwt_secret` (the default). The previous secret
    has different semantics (optional + usually short-lived) so
    it gets its own check rather than overloading the existing
    one.

    Args:
        value: The candidate `JWT_SECRET_PREVIOUS` string. May
            be empty (means "no rotation in progress").
        env: The current `ENV` value.

    Raises:
        ValueError: If `value` is non-empty in a non-dev environment
            and is shorter than 32 bytes.
    """
    if not value:
        # Empty means "no rotation" — always allowed.
        return
    if _is_dev_or_test(env):
        return
    byte_len = len(value.encode("utf-8"))
    if byte_len < _MIN_JWT_SECRET_BYTES:
        raise ValueError(
            f"JWT_SECRET_PREVIOUS must be at least {_MIN_JWT_SECRET_BYTES} bytes "
            f"when set in a non-dev environment (RFC 7518 §3.2 for HS256); "
            f"got {byte_len} byte{'s' if byte_len != 1 else ''}. "
            "Either clear it (no rotation in progress) or set it to a "
            "32+ byte secret."
        )
