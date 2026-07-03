"""Teams router — /api/teams/* endpoints (cycle 3)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.adapters.supabase import SupabaseAdapter
from app.deps import CurrentUserIdDep, DBDep
from app.domain.team import (
    InvitationCreate,
    InvitationOut,
    TeamCreate,
    TeamMemberOut,
    TeamOut,
)
from app.services.team_service import (
    create_team,
    generate_invite_token,
    get_user_team,
    list_members,
    user_is_member,
    user_role_in_team,
)

router = APIRouter(prefix="/api/teams", tags=["teams"])


def _require_member(adapter: SupabaseAdapter, *, user_id: UUID, team_id: UUID) -> None:
    """Raise 403 if `user_id` is not an active member of `team_id`."""
    if not user_is_member(adapter, user_id=user_id, team_id=team_id):
        raise HTTPException(status_code=403, detail="not a member of this team")


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team_endpoint(
    payload: TeamCreate,
    user_id: CurrentUserIdDep,
    supabase: DBDep,
) -> TeamOut:
    """ST-MT-01: create a team + set caller as owner."""
    team = create_team(supabase, name=payload.name, owner_id=UUID(user_id))
    return TeamOut.model_validate(team)


@router.get("/me", response_model=TeamOut | None)
def get_my_team(
    user_id: CurrentUserIdDep,
    supabase: DBDep,
) -> TeamOut | None:
    """ST-MT-02: get caller's team (MVP: at most one)."""
    team = get_user_team(supabase, user_id=UUID(user_id))
    if team is None:
        return None
    return TeamOut.model_validate(team)


@router.get("/{team_id}", response_model=TeamOut)
def get_team(
    team_id: UUID,
    user_id: CurrentUserIdDep,
    supabase: DBDep,
) -> TeamOut:
    """Get a team the caller is a member of. 403 if not a member."""
    _require_member(supabase, user_id=UUID(user_id), team_id=team_id)
    team = supabase.get_by_id("teams", str(team_id))
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    return TeamOut.model_validate(team)


@router.get("/{team_id}/members", response_model=list[TeamMemberOut])
def list_team_members(
    team_id: UUID,
    user_id: CurrentUserIdDep,
    supabase: DBDep,
) -> list[TeamMemberOut]:
    """ST-MT-03: list all active members of the team (must be a member)."""
    _require_member(supabase, user_id=UUID(user_id), team_id=team_id)
    rows = list_members(supabase, team_id=team_id)
    return [TeamMemberOut.model_validate(r) for r in rows]


# ── Invitations (token generation lives here; accept flow in T-307) ──


@router.post(
    "/{team_id}/invitations",
    response_model=InvitationOut,
    status_code=status.HTTP_201_CREATED,
)
def invite_member(
    team_id: UUID,
    payload: InvitationCreate,
    user_id: CurrentUserIdDep,
    supabase: DBDep,
) -> InvitationOut:
    """Owner invites a teammate by email. Returns the token (mock: logged)."""
    role = user_role_in_team(supabase, user_id=UUID(user_id), team_id=team_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="only owners can invite")

    # Check if email already belongs to a team member
    existing_users = supabase.query("users", filters={"email": payload.email})
    existing_user = existing_users[0] if existing_users else None
    if existing_user and user_is_member(
        supabase,
        user_id=UUID(str(existing_user["id"])),
        team_id=team_id,
    ):
        raise HTTPException(status_code=409, detail="user is already a team member")

    from datetime import datetime, timedelta, timezone

    token = generate_invite_token()
    invitation = supabase.insert(
        "team_invitations",
        {
            "team_id": str(team_id),
            "email": payload.email,
            "role": payload.role,
            "token": token,
            "invited_by": user_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        },
    )
    return InvitationOut.model_validate({**invitation, "invite_url": f"/invite/{token}"})
