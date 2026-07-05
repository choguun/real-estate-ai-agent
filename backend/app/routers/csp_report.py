"""CSP violation report endpoint — cycle 7 T-703 (AC-CSP-01..03).

Browsers that block a script per the CSP can be configured to
report the violation. The standard format is:

    Content-Type: application/csp-report
    Body: { "csp-report": {
        "document-uri": "...",
        "violated-directive": "script-src 'self'",
        "blocked-uri": "...",
        ...
    }

This endpoint:

1. Accepts the request body (browsers can't send auth headers,
   so the endpoint is unauthenticated).
2. Parses the csp-report JSON.
3. Extracts violated-directive + blocked-uri.
4. Writes one row to security_events with
   action='csp.violation', metadata={violated_directive, blocked_uri}.
5. Returns 204 No Content (the browser doesn't retry on 204).

The endpoint is permissive on malformed bodies: a non-JSON body,
a missing csp-report key, or a missing field all return 204
without raising. The audit row is only written when the body
parses + has the expected shape; otherwise the violation is
silently dropped (best-effort; browsers shouldn't retry).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request, Response, status

from app.audit_log import ACTION_CSP_VIOLATION, AuditEvent, write_event
from app.deps import DBDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/csp-report", tags=["csp"])


@router.post("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def csp_report(request: Request, supabase: DBDep) -> Response:
    """Receive a CSP violation report from the browser.

    Returns 204 No Content on success OR on malformed body (the
    browser shouldn't retry CSP reports — they could spam).
    """
    raw = await request.body()
    if not raw:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        logger.warning("csp_report: malformed JSON (%s)", exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if not isinstance(payload, dict):
        logger.warning("csp_report: payload not a dict (got %s)", type(payload).__name__)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    report = payload.get("csp-report")
    if not isinstance(report, dict):
        logger.warning("csp_report: missing or non-dict csp-report key")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    violated_directive = report.get("violated-directive") or "unknown"
    blocked_uri = report.get("blocked-uri") or "unknown"

    # Write the audit row. write_event is best-effort: any DB
    # exception is logged + swallowed. The endpoint still returns
    # 204 — a failed audit-log write must not break the browser.
    write_event(
        supabase,
        AuditEvent(
            actor_id=None,
            action=ACTION_CSP_VIOLATION,
            target_id=None,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            success=True,
            metadata={
                "violated_directive": str(violated_directive),
                "blocked_uri": str(blocked_uri),
                "document_uri": str(report.get("document-uri") or "unknown"),
            },
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _client_ip(request: Request) -> str | None:
    """Same helper as the auth router's _client_metadata."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return None
