"""Auth service — bcrypt + JWT + LIFF-user upsert.

Single interface (`AuthService`) that the auth router uses. All
bcrypt + PyJWT calls live here so the routers stay thin.

In real mode (USE_REAL_LINE + real Supabase Auth) this service becomes
a Supabase Auth client: `sign_up`, `sign_in_with_password`,
`sign_in_with_id_token` (LIFF). The router doesn't change; only the
class binding flips.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.adapters.supabase.base import SupabaseAdapter
from app.audit_log import (
    record_login_failure,
    record_login_success,
    record_signup,
)
from app.config import Settings

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Base class for auth errors. Subclasses get HTTP mapping in the router."""

    http_status = 400


class DuplicateEmail(AuthError):
    http_status = 409


class InvalidCredentials(AuthError):
    http_status = 401


class UserNotFound(AuthError):
    http_status = 404


# ─── Hashing helpers (could swap for argon2 in prod) ───────────────────
def hash_password(plaintext: str) -> str:
    """Bcrypt with default cost (12). Truncate to 72 bytes to avoid overflow."""
    truncated = plaintext.encode("utf-8")[:72]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("ascii")


def verify_password(plaintext: str, hashed: str) -> bool:
    truncated = plaintext.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(truncated, hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


# ─── JWT helpers ────────────────────────────────────────────────────────
def create_access_token(
    user_id: str,
    email: str | None,
    *,
    settings: Settings,
) -> str:
    """Issue a short-lived HS256 JWT."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_ttl_seconds)).timestamp()),
        "jti": secrets.token_urlsafe(16),
        "iss": settings.app_name,
    }
    token: str = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)
    return token


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode + verify a JWT. Raises `jwt.PyJWTError` subclasses on bad input."""
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_alg],
        options={"require": ["exp", "iat", "sub"]},
    )
    return payload


# ─── Service ────────────────────────────────────────────────────────────
class AuthService:
    """Domain service. Receives the DB adapter via DI."""

    def __init__(self, db: SupabaseAdapter, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    # ─── signup ───────────────────────────────────────────────────────
    def signup(
        self,
        *,
        email: str,
        full_name: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        existing = self._db.query("users", filters={"email": email})
        if existing:
            raise DuplicateEmail(f"Email already registered: {email}")

        user = self._db.insert(
            "users",
            {
                "email": email,
                "full_name": full_name,
                "password_hash": hash_password(password),
            },
        )

        # T-304: every user belongs to a personal team on signup so the
        # team-scoped routers can resolve team_id without a separate
        # create-team step.
        from app.services.team_service import create_team

        personal = create_team(
            self._db,
            name=f"Personal {str(user['id'])[:8]}",
            owner_id=user["id"],
        )
        user = self._db.update("users", user["id"], {"team_id": personal["id"]}) or user

        token = create_access_token(user["id"], user["email"], settings=self._settings)
        # T-503: emit audit row (best-effort — write_event swallows errors)
        record_signup(self._db, user_id=user["id"], ip=ip, user_agent=user_agent)
        return {"user": _public_user(user), "token": token}

    # ─── login ────────────────────────────────────────────────────────
    def login(
        self,
        *,
        email: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        rows = self._db.query("users", filters={"email": email})
        if not rows:
            # Constant-time-ish (still tell the truth but log nothing)
            record_login_failure(self._db, email=email, ip=ip, user_agent=user_agent)
            raise InvalidCredentials("Invalid email or password")
        user = rows[0]
        if not user.get("password_hash") or not verify_password(password, user["password_hash"]):
            record_login_failure(self._db, email=email, ip=ip, user_agent=user_agent)
            raise InvalidCredentials("Invalid email or password")
        token = create_access_token(user["id"], user["email"], settings=self._settings)
        record_login_success(self._db, user_id=user["id"], ip=ip, user_agent=user_agent)
        return {"user": _public_user(user), "token": token}

    # ─── LIFF (LINE) login ───────────────────────────────────────────
    def liff_login(
        self,
        *,
        line_user_id: str,
        display_name: str | None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        rows = self._db.query("users", filters={"line_user_id": line_user_id})
        if rows:
            user = rows[0]
        else:
            # LIFF users have no email by default — synthesise a stable placeholder.
            placeholder_email = f"line_{line_user_id}@line.placeholder"
            user = self._db.insert(
                "users",
                {
                    "email": placeholder_email,
                    "full_name": display_name or "LINE user",
                    "line_user_id": line_user_id,
                },
            )
        token = create_access_token(user["id"], user["email"], settings=self._settings)
        record_login_success(self._db, user_id=user["id"], ip=ip, user_agent=user_agent)
        return {"user": _public_user(user), "token": token}

    # ─── session lookup ──────────────────────────────────────────────
    def user_from_token(self, token: str) -> dict[str, Any]:
        """Decode a JWT and load the matching user record."""
        payload = decode_token(token, self._settings)
        user_id = payload["sub"]
        user = self._db.get_by_id("users", user_id)
        if user is None:
            raise UserNotFound("Token valid but user no longer exists")
        return _public_user(user)


def _public_user(row: dict[str, Any]) -> dict[str, Any]:
    """Strip the password_hash before returning user to clients."""
    return {k: v for k, v in row.items() if k != "password_hash"}
