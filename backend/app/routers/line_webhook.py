"""LINE webhook handler — verifies HMAC, never processes unverified events.

The security property here is that the signature is verified against
**raw request bytes** BEFORE JSON parsing. A body-tampering attacker
cannot smuggle events past verification because the bytes they signed
will not equal the bytes we received.

T-008 stops at "verified, ack". T-009 adds lead + message persistence.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.adapters.line.base import SIGNATURE_HEADER, verify_line_webhook

logger = logging.getLogger(__name__)

router = APIRouter(tags=["line"])


@router.post("/webhook/line")
async def line_webhook(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings

    # 1. Read raw body bytes BEFORE any JSON parsing.
    body = await request.body()

    # 2. Read the signature header.
    signature = request.headers.get(SIGNATURE_HEADER)
    if not signature:
        logger.info("LINE webhook: missing signature header")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing {SIGNATURE_HEADER} header",
        )

    # 3. Verify against the configured channel secret.
    if not verify_line_webhook(body, signature, settings.line_channel_secret):
        logger.warning("LINE webhook: signature mismatch")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    # 4. ONLY now do we parse JSON. Signature has been proven valid.
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {exc.msg}",
        ) from exc

    events = payload.get("events", []) if isinstance(payload, dict) else []
    return {"ok": True, "received": len(events)}


# Suppress unused import — Response used for type clarity above.
_ = Response
