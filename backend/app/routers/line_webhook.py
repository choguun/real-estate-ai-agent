"""LINE webhook — HMAC verify, then run events through the lead pipeline.

Wires ``LineDep`` so the dispatcher can cache reply tokens off inbound
``message`` events for outbound use. The reply-token cache is a
Protocol method on the adapter (no-op in mock, real cache when wired).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.adapters.line.base import (
    SIGNATURE_HEADER,
    WEBHOOK_BODY_MAX_BYTES,
    verify_line_webhook,
)
from app.deps import DBDep, LineDep, SettingsDep
from app.services.lead_pipeline import LeadPipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["line"])


@router.post("/webhook/line")
async def line_webhook(
    request: Request,
    settings: SettingsDep,
    db: DBDep,
    line: LineDep,
) -> dict[str, Any]:
    # 1. Read raw body bytes BEFORE any JSON parsing.
    body = await request.body()

    # Memory-exhaustion guard: Starlette's ``Request.body()`` reads the
    # entire body into memory with no built-in size cap; we cap
    # explicitly. Reject before doing any HMAC work on a body we'd
    # never accept. (uvicorn's ``h11_max_incomplete_event_size`` only
    # caps incomplete event headers, not bodies — proxy this with
    # ``client_max_body_size`` if you put nginx in front.)
    if len(body) > WEBHOOK_BODY_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="payload too large",
        )

    # 2. Read & verify the signature.
    signature = request.headers.get(SIGNATURE_HEADER)
    if not signature:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing {SIGNATURE_HEADER} header",
        )
    if not verify_line_webhook(body, signature, settings.line_channel_secret):
        logger.warning("LINE webhook: signature mismatch")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    # 3. NOW parse JSON.
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {exc.msg}",
        ) from exc

    events = payload.get("events", []) if isinstance(payload, dict) else []
    results: list[dict[str, Any]] = []

    # 4. Only resolve an agent if there are events to process.
    #
    # Routing priority (P1-W3):
    #   1. LINE_DEFAULT_TEAM_ID env var → attribute all events to that
    #      team directly (bypasses agent lookup). Use this for multi-tenant
    #      deploys where each LINE channel belongs to exactly one team.
    #   2. LINE_DEFAULT_AGENT_ID env var → attribute to that agent's team
    #      (uses the agent's users.team_id, which is set on signup).
    #   3. Fallback: first active user. Logs a warning since this is
    #      non-deterministic in multi-team setups.
    if events:
        if settings.line_default_team_id:
            agent_id = _agent_id_for_team(db, settings.line_default_team_id)
            if agent_id is None:
                logger.error(
                    "LINE webhook: LINE_DEFAULT_TEAM_ID=%s has no members",
                    settings.line_default_team_id,
                )
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="LINE_DEFAULT_TEAM_ID has no members",
                )
        elif settings.line_default_agent_id:
            agent_id = settings.line_default_agent_id
        else:
            candidates = db.query("users", filters={"is_active": True})
            if not candidates:
                logger.error(
                    "LINE webhook: no agent (set LINE_DEFAULT_TEAM_ID or "
                    "LINE_DEFAULT_AGENT_ID, or have at least one user in DB)"
                )
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="No agent configured to attribute LINE leads to",
                )
            agent_id = candidates[0]["id"]
            logger.warning(
                "LINE webhook: no LINE_DEFAULT_TEAM_ID or "
                "LINE_DEFAULT_AGENT_ID set; falling back to first active user. "
                "This is non-deterministic in multi-team setups — set the env "
                "vars for production."
            )

        pipeline = LeadPipeline(db)
        for event in events:
            try:
                # Cache the reply token off any inbound message event so
                # the eventual outbound Reply API can use it (free vs the
                # metered Push API). Both mock and real adapters expose
                # ``set_reply_token`` on the Protocol.
                if event.get("type") == "message":
                    _cache_reply_token(line, event)

                assert agent_id is not None
                results.append(_as_dict(pipeline.process_event(event, agent_id=agent_id)))
            except Exception:
                logger.exception("LINE pipeline crashed on event; skipping")

    processed_count = sum(1 for r in results if r.get("processed"))
    return {
        "ok": True,
        "received": len(results),
        "processed": processed_count,
        "results": results,
    }


def _agent_id_for_team(db: Any, team_id: str) -> str | None:
    """Return the first active user in `team_id`, or None if empty."""
    members = db.query(
        "team_memberships",
        filters={"team_id": team_id},
    )
    for m in members:
        if m.get("left_at") is not None:
            continue
        user = db.get_by_id("users", m["user_id"])
        if user and user.get("is_active", True):
            return str(user["id"])
    return None


def _cache_reply_token(line: Any, event: dict[str, Any]) -> None:
    """Best-effort cache of the inbound ``replyToken`` for later use.

    Skips silently if the event has no ``replyToken`` (some webhook
    events — e.g. follow/unfollow — don't carry one). Also skips if
    the source is missing a chat identifier (shouldn't happen on
    well-formed events but is defensive).
    """
    reply_token = event.get("replyToken")
    if not reply_token or not isinstance(reply_token, str):
        return
    source = event.get("source") or {}
    chat_id = source.get("userId") or source.get("groupId") or source.get("roomId")
    if not chat_id:
        return
    line.set_reply_token(chat_id, reply_token)


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
