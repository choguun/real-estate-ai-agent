"""FastAPI dependency injection.

Centralised so routers do `db: DBDep` and never instantiate adapters.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.adapters.supabase._factory import get_db
from app.adapters.supabase.base import SupabaseAdapter
from app.config import Settings, get_settings
from app.services.auth import decode_token


def get_db_dep() -> SupabaseAdapter:
    """Per-request dependency. Singleton-per-process for the mock."""
    return get_db()


DBDep = Annotated[SupabaseAdapter, Depends(get_db_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_current_user_id(
    authorization: Annotated[str | None, Header()] = None,
    settings: SettingsDep = None,  # type: ignore[assignment]
) -> str:
    """Decode the bearer token and return the user id (JWT `sub` claim).

    Raises 401 if the header is missing/malformed or the token is invalid.
    Does NOT touch the database — call this when you only need the scope.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token, settings)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )
    return sub


CurrentUserIdDep = Annotated[str, Depends(get_current_user_id)]
