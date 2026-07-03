"""Listing domain — DTOs and enums for AI-generated content."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Platform(str, Enum):
    ddproperty = "ddproperty"
    livinginsider = "livinginsider"
    facebook = "facebook"
    general = "general"


# ─── Input to the AI service ───────────────────────────────────────────
class PropertySummary(BaseModel):
    """The subset of property fields the AI actually uses."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    property_type: str | None = None  # accepts free-form; routes convert to enum
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

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PropertySummary:
        return cls(**{k: row.get(k) for k in cls.model_fields})


class ListingRequest(BaseModel):
    """Body of POST /api/generate-listing."""

    model_config = ConfigDict(extra="forbid")

    property: PropertySummary
    platforms: list[Platform] | None = None  # defaults to all 4
    image_urls: list[str] | None = None


# ─── Output ─────────────────────────────────────────────────────────────
class GeneratedContent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    platform: Platform
    title: str
    description: str
    hashtags: list[str] = Field(default_factory=list)
    seo_keywords: list[str] = Field(default_factory=list)
    ai_model: str
    prompt_used: str | None = None
