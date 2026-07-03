"""FastAPI dependency injection.

Centralised so routers do `db: DBDep` and never instantiate adapters.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.adapters.ai._factory import build_ai_chain
from app.adapters.ai.base import AiAdapter
from app.adapters.email import build_email_adapter
from app.adapters.email.base import EmailAdapter
from app.adapters.line._factory import get_line_adapter
from app.adapters.line.base import LineAdapter
from app.adapters.storage._factory import get_storage
from app.adapters.storage.base import StorageAdapter
from app.adapters.supabase._factory import get_db
from app.adapters.supabase.base import SupabaseAdapter
from app.config import Settings, get_settings
from app.services.auth import decode_token
from app.services.team_service import get_user_team


def get_db_dep() -> SupabaseAdapter:
    """Per-request dependency. Singleton-per-process for the mock."""
    return get_db()


DBDep = Annotated[SupabaseAdapter, Depends(get_db_dep)]


def get_settings_dep(request: Request) -> Settings:
    """Resolve settings from the app's state, not the global cache.

    Tests pass explicit `Settings(...)` to `create_app`; this dep picks
    them up regardless of any other call to `get_settings()`.
    """
    return getattr(request.app.state, "settings", None) or get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_storage_dep(settings: SettingsDep) -> StorageAdapter:
    """Per-request storage adapter (uses settings from request.app.state)."""
    return get_storage(settings=settings)


StorageDep = Annotated[StorageAdapter, Depends(get_storage_dep)]


def get_ai_chain(settings: SettingsDep) -> list[AiAdapter]:
    """Per-request AI adapter chain."""
    return build_ai_chain(settings=settings)


AIChainDep = Annotated[list[AiAdapter], Depends(get_ai_chain)]


def get_line_dep(settings: SettingsDep) -> LineAdapter:
    """Per-request LINE adapter (mock unless use_real_line=true)."""
    return get_line_adapter(settings=settings)


LineDep = Annotated[LineAdapter, Depends(get_line_dep)]


def get_email() -> EmailAdapter:
    """Per-request email adapter (mock unless use_mocks=false)."""
    return build_email_adapter()


EmailDep = Annotated[EmailAdapter, Depends(get_email)]


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


def get_current_team(
    user_id: CurrentUserIdDep,
    db: DBDep,
) -> str:
    """Resolve the caller's team_id, auto-creating a personal team if needed.

    This keeps the cycle 1 flow working: a user who signs up without
    creating a team explicitly gets a 'personal-{uuid}' team auto-created
    on first authenticated request. Multi-tenant features (invites,
    role changes) operate on the same team.

    Returns:
        The caller's team_id (str).
    """
    from uuid import UUID

    team = get_user_team(db, user_id=UUID(user_id))
    if team is not None:
        return str(team["id"])

    # Auto-create a personal team so existing flows keep working
    # without users having to explicitly POST /api/teams.
    from app.services.team_service import create_team

    new_team = create_team(db, name=f"Personal {user_id[:8]}", owner_id=UUID(user_id))
    return str(new_team["id"])


CurrentTeamIdDep = Annotated[str, Depends(get_current_team)]
