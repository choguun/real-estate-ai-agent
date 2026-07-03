"""Teams router — /api/teams/* endpoints (cycle 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

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


# ── T-303: Member management (role change + remove + leave) ──


@router.patch(
    "/{team_id}/members/{member_user_id}",
    response_model=TeamMemberOut,
)
def change_member_role(
    team_id: UUID,
    member_user_id: UUID,
    payload: dict[str, Any],
    user_id: CurrentUserIdDep,
    supabase: DBDep,
) -> TeamMemberOut:
    """ST-MT-06: Owner changes a member's role. Cannot demote owner."""
    actor_role = user_role_in_team(supabase, user_id=UUID(user_id), team_id=team_id)
    if actor_role != "owner":
        raise HTTPException(status_code=403, detail="only owners can change roles")
    new_role = payload.get("role")
    if new_role not in ("owner", "admin", "agent"):
        raise HTTPException(status_code=422, detail="invalid role")

    # Critical: owner cannot demote themselves
    if str(member_user_id) == user_id and new_role != "owner":
        raise HTTPException(status_code=409, detail="owner cannot demote themselves")

    # Update the membership row
    memberships = supabase.query(
        "team_memberships",
        filters={"team_id": str(team_id), "user_id": str(member_user_id)},
    )
    if not memberships or memberships[0].get("left_at") is not None:
        raise HTTPException(status_code=404, detail="member not found")
    updated = supabase.update(
        "team_memberships",
        str(memberships[0]["id"]),
        {"role": new_role},
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="member not found")

    # Return the updated member shape
    user = supabase.get_by_id("users", str(member_user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return TeamMemberOut.model_validate(
        {
            "id": updated["id"],
            "team_id": updated["team_id"],
            "user_id": updated["user_id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": updated["role"],
            "joined_at": updated["joined_at"],
            "left_at": updated.get("left_at"),
        }
    )


@router.delete(
    "/{team_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_member(
    team_id: UUID,
    member_user_id: UUID,
    user_id: CurrentUserIdDep,
    supabase: DBDep,
) -> Response:
    """ST-MT-07: Owner removes a member (soft-delete via left_at)."""
    actor_role = user_role_in_team(supabase, user_id=UUID(user_id), team_id=team_id)
    if actor_role != "owner":
        raise HTTPException(status_code=403, detail="only owners can remove members")
    if str(member_user_id) == user_id:
        raise HTTPException(status_code=409, detail="owner cannot remove themselves")

    memberships = supabase.query(
        "team_memberships",
        filters={"team_id": str(team_id), "user_id": str(member_user_id)},
    )
    if not memberships or memberships[0].get("left_at") is not None:
        raise HTTPException(status_code=404, detail="member not found")
    supabase.update(
        "team_memberships",
        str(memberships[0]["id"]),
        {
            "left_at": datetime.now(timezone.utc).isoformat(),
            "removed_by": user_id,
        },
    )
    return Response(status_code=204)


@router.post("/{team_id}/leave", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def leave_team(
    team_id: UUID,
    user_id: CurrentUserIdDep,
    supabase: DBDep,
) -> Response:
    """ST-MT-08: Self-remove. Owner cannot leave (must delete team or transfer)."""
    actor_role = user_role_in_team(supabase, user_id=UUID(user_id), team_id=team_id)
    if actor_role is None:
        raise HTTPException(status_code=404, detail="not a member of this team")
    if actor_role == "owner":
        raise HTTPException(
            status_code=409,
            detail="owner cannot leave the team (delete the team or transfer ownership first)",
        )
    memberships = supabase.query(
        "team_memberships",
        filters={"team_id": str(team_id), "user_id": user_id},
    )
    if memberships and memberships[0].get("left_at") is None:
        supabase.update(
            "team_memberships",
            str(memberships[0]["id"]),
            {"left_at": datetime.now(timezone.utc).isoformat()},
        )
    return Response(status_code=204)
