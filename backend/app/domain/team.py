"""Team DTOs (cycle 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

TeamRole = Literal["owner", "admin", "agent"]
InvitableRole = Literal["admin", "agent"]  # owner is set automatically
TeamPlan = Literal["starter", "growth", "team"]


class TeamCreate(BaseModel):
    """POST /api/teams payload."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class TeamOut(BaseModel):
    """Team shape returned to clients."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    name: str
    plan: str
    owner_id: UUID
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class TeamMemberOut(BaseModel):
    """Member of a team (joined with users)."""

    model_config = ConfigDict(extra="ignore")

    id: UUID  # membership id
    team_id: UUID
    user_id: UUID
    email: str
    full_name: str
    role: str
    joined_at: datetime
    left_at: datetime | None = None


class InvitationCreate(BaseModel):
    """POST /api/teams/{id}/invitations payload."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: InvitableRole = "agent"


class InvitationOut(BaseModel):
    """Created invitation (token is visible only on creation)."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    team_id: UUID
    email: str
    role: str
    token: str
    invited_by: UUID
    invited_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    accepted_by: UUID | None = None
    # Dev-only convenience: the URL to put in the email
    invite_url: str | None = None


class InvitationAcceptIn(BaseModel):
    """POST /api/teams/invitations/{token}/accept payload (optional fields)."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class InvitationAcceptOut(BaseModel):
    """Successful accept: returns the same shape as signup/login (AuthToken)."""

    model_config = ConfigDict(extra="ignore")

    access_token: str
    token_type: str = "bearer"
    team_id: UUID
    user: User


# Late import to resolve the forward ref
from app.domain.user import User  # noqa: E402,F401  (intentional late import)
