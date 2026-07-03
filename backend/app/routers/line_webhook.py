"""LINE webhook — HMAC verify, then run events through the lead pipeline."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.adapters.line.base import SIGNATURE_HEADER, verify_line_webhook
from app.adapters.supabase._factory import get_db
from app.services.lead_pipeline import LeadPipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["line"])


@router.post("/webhook/line")
async def line_webhook(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    db = get_db(settings=settings)

    # 1. Read raw body bytes BEFORE parsing.
    body = await request.body()

    # 2. Read & verify the signature.
    signature = request.headers.get(SIGNATURE_HEADER)
    if not signature:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail=f"Missing {SIGNATURE_HEADER} header"
        )
    if not verify_line_webhook(body, signature, settings.line_channel_secret):
        logger.warning("LINE webhook: signature mismatch")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    # 3. NOW parse JSON.
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON: {exc.msg}") from exc

    events = payload.get("events", []) if isinstance(payload, dict) else []
    results: list[dict[str, Any]] = []

    # 4. Only resolve an agent if there are events to process.
    if events:
        agent_id = settings.line_default_agent_id
        if not agent_id:
            # Dev/mock fallback: pick the first active user.
            candidates = db.query("users", filters={"is_active": True})
            if not candidates:
                logger.error("LINE webhook: no agent (no LINE_DEFAULT_AGENT_ID and no users in DB)")
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="No agent configured to attribute LINE leads to",
                )
            agent_id = candidates[0]["id"]

        # 5. Run each event through the pipeline.
        pipeline = LeadPipeline(db)
        for event in events:
            try:
                results.append(_as_dict(pipeline.process_event(event, agent_id=agent_id)))
            except Exception:
                # Never let a misbehaving event crash the webhook — log + skip.
                logger.exception("LINE pipeline crashed on event; skipping")

    processed_count = sum(1 for r in results if r.get("processed"))
    return {
        "ok": True,
        "received": len(results),
        "processed": processed_count,
        "results": results,
    }


def _as_dict(result: Any) -> dict[str, Any]:
    return {
        "event_id": result.event_id,
        "processed": result.processed,
        "new_lead": result.new_lead,
        "new_message": result.new_message,
        "lead_id": result.lead_id,
        "message_id": result.message_id,
        "reason": result.reason,
    }
