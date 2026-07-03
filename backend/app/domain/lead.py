"""Lead domain — Pydantic DTOs for the leads table."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Lead(BaseModel):
    """A lead row — passed through from the Supabase adapter without transformation."""

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
