"""Property domain — DTOs + enums."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ─── Enums ──────────────────────────────────────────────────────────────
class PropertyType(str, Enum):
    condo = "condo"
    house = "house"
    townhouse = "townhouse"
    land = "land"
    commercial = "commercial"


class PropertyStatus(str, Enum):
    draft = "draft"
    active = "active"
    sold = "sold"
    rented = "rented"
    archived = "archived"


# ─── Field constraints (re-used by Create + Update) ────────────────────
_TITLE = Field(default=None, max_length=300)
_ADDRESS = Field(default=None, max_length=500)
_DISTRICT = Field(default=None, max_length=100)
_PROVINCE = Field(default=None, max_length=100)
_BTS = Field(default=None, max_length=200)
_GE0 = Field(default=None, ge=0)


# ─── Create (POST /api/properties) ─────────────────────────────────────
class PropertyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = _TITLE
    description: str | None = None
    property_type: PropertyType | None = None
    price: float | None = _GE0
    size_sqm: float | None = _GE0
    bedrooms: int | None = _GE0
    bathrooms: int | None = _GE0
    floor: int | None = _GE0
    address: str | None = _ADDRESS
    district: str | None = _DISTRICT
    province: str | None = _PROVINCE
    near_bts_mrt: str | None = _BTS
    foreign_quota: bool | None = None
    images: list[str] | None = None


# ─── Update (PATCH /api/properties/{id}) ───────────────────────────────
class PropertyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = _TITLE
    description: str | None = None
    property_type: PropertyType | None = None
    price: float | None = _GE0
    size_sqm: float | None = _GE0
    bedrooms: int | None = _GE0
    bathrooms: int | None = _GE0
    floor: int | None = _GE0
    address: str | None = _ADDRESS
    district: str | None = _DISTRICT
    province: str | None = _PROVINCE
    near_bts_mrt: str | None = _BTS
    foreign_quota: bool | None = None
    images: list[str] | None = None
    status: PropertyStatus | None = None


# ─── Response (GET /api/properties, GET /{id}, POST, PATCH) ────────────
class Property(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    user_id: str
    title: str | None = None
    description: str | None = None
    property_type: str | None = None
    price: float | None = None
    size_sqm: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    floor: int | None = None
    address: str | None = None
    district: str | None = None
    province: str | None = None
    near_bts_mrt: str | None = None
    foreign_quota: bool | None = None
    status: str | None = None
    images: list[str] | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Property:
        return cls(**row)
