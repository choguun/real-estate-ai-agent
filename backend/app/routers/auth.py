"""Auth router — signup, login, LIFF, /me."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.deps import DBDep, SettingsDep
from app.domain.user import AuthResponse, LiffIn, LoginIn, SignupIn, User
from app.services.auth import (
    AuthError,
    AuthService,
    DuplicateEmail,
    InvalidCredentials,
    UserNotFound,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_auth_service(
    db: DBDep,
    settings: SettingsDep,
) -> AuthService:
    return AuthService(db=db, settings=settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def _map_auth_error(exc: Exception) -> HTTPException:
    """Map a service exception to an HTTP error.

    Note: `UserNotFound` is intentionally NOT in the union — it's mapped
    by handlers that know the user expected a specific row (currently only
    `/me`, which returns 404 to distinguish "no such user" from "bad
    token"). Other callers that funnel through this mapper surface
    `InvalidCredentials` for "no such user" — which is the right thing
    for `login` (don't leak whether the email exists) and a no-op for
    `signup` (which can never raise `UserNotFound` because it errors
    earlier with `DuplicateEmail`).
    """
    if isinstance(exc, DuplicateEmail):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, InvalidCredentials):
        return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    if isinstance(exc, AuthError):
        return HTTPException(exc.http_status, detail=str(exc))
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="auth error",
    )


# ─── Endpoints ──────────────────────────────────────────────────────────
def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    """Pull the client IP + User-Agent for audit logging.

    Prefers the first hop of X-Forwarded-For (typical for Railway /
    Vercel / nginx in front of the app); falls back to the
    underlying socket address. Both are best-effort; the audit row
    uses `None` if neither is present.
    """
    ip: str | None = None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    elif request.client and request.client.host:
        ip = request.client.host
    ua = request.headers.get("user-agent")
    return ip, ua


@router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(
    payload: SignupIn,
    request: Request,
    svc: AuthServiceDep,
) -> dict[str, object]:
    ip, ua = _client_metadata(request)
    try:
        return svc.signup(
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            ip=ip,
            user_agent=ua,
        )
    except Exception as exc:
        raise _map_auth_error(exc) from exc


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginIn,
    request: Request,
    svc: AuthServiceDep,
) -> dict[str, object]:
    # TODO(security): add a rate limiter (e.g. slowapi, Redis counter) before
    # any non-dev exposure. Today /api/auth/login is brute-forceable.
    ip, ua = _client_metadata(request)
    try:
        return svc.login(
            email=payload.email,
            password=payload.password,
            ip=ip,
            user_agent=ua,
        )
    except Exception as exc:
        raise _map_auth_error(exc) from exc


@router.post("/liff", response_model=AuthResponse)
def liff(
    payload: LiffIn,
    request: Request,
    svc: AuthServiceDep,
) -> dict[str, object]:
    ip, ua = _client_metadata(request)
    return svc.liff_login(
        line_user_id=payload.line_user_id,
        display_name=payload.display_name,
        ip=ip,
        user_agent=ua,
    )


@router.get("/me", response_model=User)
def me(
    svc: AuthServiceDep,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        return svc.user_from_token(token)
    except UserNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
