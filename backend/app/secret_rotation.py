"""JWT secret rotation helper — cycle 6 T-604 (AC-SR-01..04).

Zero-downtime JWT secret rotation. During a rollover window,
operators deploy with both:
    JWT_SECRET=<new>
    JWT_SECRET_PREVIOUS=<old>

Tokens signed with either secret verify successfully. New
tokens are issued with `jwt_secret`. After the window closes
(operator's call — convention is 24h, matching the default
`jwt_ttl_seconds`), drop `JWT_SECRET_PREVIOUS` and tokens
signed with the old secret start failing.

Why this exists: a strict `validate_security()` (cycle 5 T-501)
rejects deploys with weak `JWT_SECRET`. But once you're past
that gate, the only way to rotate is to wait for every old
token to expire (`jwt_ttl_seconds = 86400` = 24h). During those
24 hours, users get logged out if their token expires during
the rotation moment. With `jwt_secret_previous`, the rollover
is zero-downtime.
"""

from __future__ import annotations

from typing import Any

import jwt

from app.config import Settings


def decode_token_rotating(token: str, settings: Settings) -> dict[str, Any]:
    """Decode + verify a JWT, trying current + previous secret.

    Tries each candidate secret in order (current first, previous
    second). The first one that decodes successfully wins. If
    neither works, raises `jwt.InvalidTokenError` (or a subclass
    like `jwt.InvalidSignatureError`).

    Args:
        token: The JWT string from the `Authorization: Bearer ...`
            header.
        settings: The current `Settings`. Reads `jwt_secret` and
            `jwt_secret_previous`.

    Returns:
        The decoded payload dict.

    Raises:
        jwt.InvalidTokenError: If the token can't be decoded by
            either secret (or if it's malformed / expired).
    """
    candidates: list[str] = []
    if settings.jwt_secret:
        candidates.append(settings.jwt_secret)
    if settings.jwt_secret_previous:
        candidates.append(settings.jwt_secret_previous)

    if not candidates:
        # Both empty — defensive: refuse to verify anything.
        raise jwt.InvalidTokenError("no JWT secrets configured; cannot verify token")

    last_error: Exception | None = None
    for secret in candidates:
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                secret,
                algorithms=[settings.jwt_alg],
                options={"require": ["exp", "iat", "sub"]},
            )
            return payload
        except jwt.InvalidTokenError as exc:
            # An InvalidSignatureError means "wrong secret" — try the
            # next one. Anything else (ExpiredSignatureError,
            # DecodeError, MissingRequiredClaimError) is fatal —
            # no point trying with another secret.
            if not isinstance(exc, jwt.InvalidSignatureError):
                raise
            last_error = exc

    # All candidates exhausted (and all rejected with
    # InvalidSignatureError — meaning the token parsed but was
    # signed by none of the configured secrets).
    raise jwt.InvalidTokenError(f"token not signed by current or previous secret: {last_error}")
