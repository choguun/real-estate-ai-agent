"""Billing DTOs (cycle 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PlanTier = Literal["starter", "growth", "team", "enterprise"]
BillingStatus = Literal["trialing", "active", "past_due", "canceled", "incomplete"]


class CheckoutRequest(BaseModel):
    """POST /api/billing/checkout payload."""

    model_config = ConfigDict(extra="forbid")

    plan: PlanTier = Field(description="Plan to upgrade to (e.g. 'growth').")


class CheckoutResponse(BaseModel):
    """Returned by POST /api/billing/checkout and /portal."""

    model_config = ConfigDict(extra="ignore")

    url: str
    session_id: str


class BillingStatusOut(BaseModel):
    """Returned by GET /api/billing/status."""

    model_config = ConfigDict(extra="ignore")

    plan: PlanTier
    status: BillingStatus
    seats_used: int
    seats_limit: int
    properties_used: int
    properties_limit: int
    ai_listings_used_month: int
    ai_listings_limit_month: int
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    trial_ends_at: datetime | None = None
    is_paid: bool = False
    is_within_plan_limits: bool = True


class WebhookEventIn(BaseModel):
    """Raw payload of POST /api/billing/webhook (real webhook)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: str
    data: dict[str, Any]


class WebhookAck(BaseModel):
    """Returned by POST /api/billing/webhook."""

    status: str
    received: int
    processed: int
