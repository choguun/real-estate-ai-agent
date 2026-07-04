"""Billing router — /api/billing/* endpoints (cycle 4)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request

from app.deps import (
    BillingDep,
    CurrentTeamIdDep,
    CurrentUserIdDep,
    DBDep,
    SettingsDep,
)
from app.domain.billing import (
    BillingStatusOut,
    CheckoutRequest,
    CheckoutResponse,
    WebhookAck,
)
from app.services.billing_service import (
    get_billing_status,
    handle_webhook_event,
    start_checkout,
    start_portal,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/status", response_model=BillingStatusOut)
def billing_status(
    team_id: CurrentTeamIdDep,
    supabase: DBDep,
) -> BillingStatusOut:
    """AC-BL-01: full billing status (plan, status, seat counts, etc.)."""
    status_dict = get_billing_status(supabase, team_id=UUID(team_id))
    return BillingStatusOut.model_validate(status_dict)


@router.post("/checkout", response_model=CheckoutResponse)
def checkout(
    payload: CheckoutRequest,
    user_id: CurrentUserIdDep,
    team_id: CurrentTeamIdDep,
    supabase: DBDep,
    billing: BillingDep,
    settings: SettingsDep,
) -> CheckoutResponse:
    """AC-BL-02: create a Stripe Checkout session for upgrading."""
    from app.services.team_service import user_role_in_team

    role = user_role_in_team(supabase, user_id=UUID(user_id), team_id=UUID(team_id))
    if role is None:
        raise HTTPException(status_code=403, detail="not a member of this team")

    success_url = f"{settings.frontend_url}/dashboard/billing?upgrade=success"
    cancel_url = f"{settings.frontend_url}/dashboard/billing?upgrade=canceled"
    session = start_checkout(
        adapter=supabase,
        billing=billing,
        team_id=UUID(team_id),
        plan=payload.plan,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return CheckoutResponse.model_validate(session)


@router.post("/portal", response_model=CheckoutResponse)
def portal(
    user_id: CurrentUserIdDep,
    team_id: CurrentTeamIdDep,
    supabase: DBDep,
    billing: BillingDep,
    settings: SettingsDep,
) -> CheckoutResponse:
    """AC-BL-03: open the Stripe Customer Portal for self-service."""
    from app.services.team_service import user_role_in_team

    role = user_role_in_team(supabase, user_id=UUID(user_id), team_id=UUID(team_id))
    if role is None:
        raise HTTPException(status_code=403, detail="not a member of this team")

    return_url = f"{settings.frontend_url}/dashboard/billing"
    session = start_portal(
        adapter=supabase,
        billing=billing,
        team_id=UUID(team_id),
        return_url=return_url,
    )
    return CheckoutResponse.model_validate(session)


@router.post("/webhook", response_model=WebhookAck)
async def billing_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
    supabase: DBDep = None,  # type: ignore[assignment]
    billing: BillingDep = None,  # type: ignore[assignment]
) -> WebhookAck:
    """AC-BL-04: verify Stripe signature, dispatch event handlers.

    Real mode (T-405): Stripe HMAC-SHA256 signature verified against
    STRIPE_WEBHOOK_SECRET.
    Mock mode: accepts unsigned payloads (test-only).
    """
    import os

    if stripe_signature is None:
        if os.environ.get("USE_MOCKS", "true").lower() == "true":
            stripe_signature = "mock-signature"
        else:
            raise HTTPException(status_code=400, detail="missing Stripe-Signature header")

    payload = await request.body()
    try:
        result = handle_webhook_event(
            adapter=supabase,
            billing=billing,
            payload=payload,
            signature_header=stripe_signature,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return WebhookAck(status=result["status"], received=1, processed=1)
