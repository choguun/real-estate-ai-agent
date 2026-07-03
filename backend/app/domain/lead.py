"""Lead domain — Pydantic DTOs and enums."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LeadStatus(str, Enum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    viewing = "viewing"
    negotiation = "negotiation"
    closed = "closed"
    lost = "lost"


class Lead(BaseModel):
    """A lead row, scoped to a user (agent)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    user_id: str
    team_id: str | None = None
    name: str | None = None
    phone: str | None = None
    line_user_id: str | None = None
    email: str | None = None
    source: str | None = None
    status: str | None = None
    interest_type: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    preferred_areas: list[str] | None = None
    notes: str | None = None
    last_contacted_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Lead:
        return cls(**row)


class LeadUpdate(BaseModel):
    """Partial update for PATCH /api/leads/{id}."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=320)
    status: LeadStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)
    interest_type: str | None = Field(default=None, max_length=100)
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    preferred_areas: list[str] | None = None
