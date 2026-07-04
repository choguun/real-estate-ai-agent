"""Teams router — /api/teams/* endpoints (cycle 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.adapters.supabase import SupabaseAdapter
from app.deps import CurrentUserIdDep, DBDep, EmailDep
from app.domain.team import (
    InvitationAcceptIn,
    InvitationAcceptOut,
    InvitationCreate,
    InvitationOut,
    TeamCreate,
    TeamMemberOut,
    TeamOut,
)
from app.domain.user import User  # noqa: E402
from app.services.auth import create_access_token, hash_password
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
    if not user_is_member(adapter, user_id=user_id, team_id=team_id):
        raise HTTPException(status_code=403, detail="not a member of this team")


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team_endpoint(
    payload: TeamCreate,
    user_id: CurrentUserIdDep,
    supabase: DBDep,
) -> TeamOut:
    """ST-MT-01: create a team + set caller as owner."""
    plan = payload.model_dump().get("plan") or "starter"
    team = create_team(supabase, name=payload.name, owner_id=UUID(user_id), plan=plan)
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


# ── Invitations + accept flow (T-307) ───────────────────────────


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
    email_svc: EmailDep,
) -> InvitationOut:
    """Owner invites a teammate by email. Sends an email with the invite link."""
    role = user_role_in_team(supabase, user_id=UUID(user_id), team_id=team_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="only owners can invite")

    existing_users = supabase.query("users", filters={"email": payload.email})
    existing_user = existing_users[0] if existing_users else None
    if existing_user and user_is_member(
        supabase,
        user_id=UUID(str(existing_user["id"])),
        team_id=team_id,
    ):
        raise HTTPException(status_code=409, detail="user is already a team member")

    from app.services.plan_limits import PlanLimitExceeded, assert_can_invite

    try:
        assert_can_invite(supabase, team_id=team_id)
    except PlanLimitExceeded as exc:
        raise HTTPException(
            status_code=403,
            detail=f"plan limit exceeded ({exc.code}): {exc.used}/{exc.limit}",
        ) from exc

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

    # Send the invite email (mock in dev: logs to console + records)
    team = supabase.get_by_id("teams", str(team_id))
    team_name = team["name"] if team else "your team"
    invite_url = f"/invite/{token}"
    email_svc.send(
        to=payload.email,
        subject=f"You've been invited to {team_name}",
        body=(
            f"You've been invited to join {team_name} on Real Estate AI.\n\n"
            f"Click the link below to accept (expires in 7 days):\n"
            f"https://app.realestateai.example.com{invite_url}\n"
        ),
    )

    return InvitationOut.model_validate({**invitation, "invite_url": invite_url})


@router.post(
    "/invitations/{token}/accept",
    response_model=InvitationAcceptOut,
)
def accept_invitation(
    token: str,
    payload: InvitationAcceptIn,
    request: Request,
    supabase: DBDep,
) -> InvitationAcceptOut:
    """ST-MT-09: Accept an invite — creates user (if new) + adds to team + returns JWT."""
    invites = supabase.query("team_invitations", filters={"token": token})
    if not invites:
        raise HTTPException(status_code=400, detail="invalid or expired invitation")
    invitation = invites[0]

    # Already accepted?
    if invitation.get("accepted_at") is not None:
        raise HTTPException(status_code=410, detail="invitation already accepted")
    # Expired?
    expires_at = datetime.fromisoformat(invitation["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="invitation expired")

    team_id = UUID(invitation["team_id"])
    email = invitation["email"]
    invite_role = invitation["role"]

    # Find or create the user
    existing_users = supabase.query("users", filters={"email": email})
    if existing_users:
        user = existing_users[0]
        user_id = UUID(user["id"])
        if not user.get("password_hash") and payload.password:
            # LIFF user being onboarded — set their password
            supabase.update(
                "users", str(user_id), {"password_hash": hash_password(payload.password)}
            )
    else:
        # New user
        from app.config import get_settings

        new_pw = payload.password
        if not new_pw:
            raise HTTPException(
                status_code=400,
                detail="password is required to create a new user",
            )
        user = supabase.insert(
            "users",
            {
                "email": email,
                "full_name": payload.full_name or email.split("@")[0],
                "password_hash": hash_password(new_pw),
            },
        )
        user_id = UUID(user["id"])

    # Add to team (skip if already a member). Enforce the seat cap
    # *before* inserting a new membership row — otherwise an invite
    # created while the team was on a higher plan could be accepted
    # after a downgrade and silently overshoot the new cap.
    from app.services.plan_limits import PlanLimitExceeded, assert_can_invite

    try:
        assert_can_invite(supabase, team_id=team_id)
    except PlanLimitExceeded as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    existing_memberships = supabase.query(
        "team_memberships",
        filters={"team_id": str(team_id), "user_id": str(user_id)},
    )
    if not existing_memberships:
        supabase.insert(
            "team_memberships",
            {
                "team_id": str(team_id),
                "user_id": str(user_id),
                "role": invite_role,
            },
        )
    else:
        # If the membership was soft-deleted (left_at set), un-soft-delete
        membership = existing_memberships[0]
        if membership.get("left_at") is not None:
            supabase.update(
                "team_memberships",
                str(membership["id"]),
                {"left_at": None, "role": invite_role, "removed_by": None},
            )

    # Mark invitation accepted
    supabase.update(
        "team_invitations",
        str(invitation["id"]),
        {
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "accepted_by": str(user_id),
        },
    )

    # Issue a JWT
    from app.config import get_settings  # noqa: F401

    settings = get_settings()
    access_token = create_access_token(str(user_id), email, settings=settings)

    # T-503: emit audit row (best-effort — write_event swallows errors)
    from app.audit_log import record_accept_invite

    fwd = request.headers.get("x-forwarded-for")
    ip = fwd.split(",")[0].strip() if fwd else None
    if not ip and request.client:
        ip = request.client.host
    ua = request.headers.get("user-agent")
    record_accept_invite(
        supabase,
        user_id=str(user_id),
        team_id=str(team_id),
        ip=ip,
        user_agent=ua,
    )

    return InvitationAcceptOut(
        access_token=access_token,
        token_type="bearer",
        team_id=team_id,
        user=User.model_validate({k: v for k, v in user.items() if k != "password_hash"}),
    )


# ── T-303: Member management ──


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
    if str(member_user_id) == user_id and new_role != "owner":
        raise HTTPException(status_code=409, detail="owner cannot demote themselves")

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


@router.post(
    "/{team_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def leave_team(
    team_id: UUID,
    user_id: CurrentUserIdDep,
    supabase: DBDep,
) -> Response:
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
