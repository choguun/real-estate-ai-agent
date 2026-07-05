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
    # C1 sub-fix: plan is "starter" only at creation. Upgrades happen
    # via Stripe Checkout + webhook (T-403). Without this Literal a user
    # could self-promote to "enterprise" by sending plan=enterprise.
    plan: Literal["starter"] = "starter"


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
    user: User  # noqa: F821


# Late import to resolve the forward ref
from app.domain.user import User  # noqa: E402,F401  (intentional late import)


class TeamRateLimitsOut(BaseModel):
    """Effective rate-limit policy for a team.

    Returned by GET /api/teams/{id}/rate_limits. Each value is
    either the team's override OR the system default (5 / 5 / 20).
    """

    model_config = ConfigDict(extra="forbid")

    login_per_15min: int = Field(ge=1)
    signup_per_hour: int = Field(ge=1)
    invite_per_hour: int = Field(ge=1)


class TeamRateLimitsPatchIn(BaseModel):
    """PATCH /api/teams/{id}/rate_limits payload.

    All fields are optional. At least one is required (enforced by
    the router — an empty patch returns 422). Each value must be
    ≥ 1 (Pydantic Field validator).
    """

    model_config = ConfigDict(extra="forbid")

    login_per_15min: int | None = Field(default=None, ge=1)
    signup_per_hour: int | None = Field(default=None, ge=1)
    invite_per_hour: int | None = Field(default=None, ge=1)
