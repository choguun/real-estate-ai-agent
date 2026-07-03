"""User domain — DTOs and value objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """Public user shape — NEVER includes `password_hash`."""

    model_config = ConfigDict(extra="ignore")

    id: str
    email: str | None
    full_name: str
    phone: str | None = None
    avatar_url: str | None = None
    role: str | None = None
    team_id: str | None = None
    line_user_id: str | None = None
    is_active: bool | None = None
    created_at: str | datetime | None = None
    updated_at: str | datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> User:
        return cls(**{k: v for k, v in row.items() if k != "password_hash"})


# ─── Inbound payloads ────────────────────────────────────────────────────
class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class LiffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_user_id: str = Field(min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=200)


# ─── Outbound ───────────────────────────────────────────────────────────
class AuthResponse(BaseModel):
    user: User
    token: str
