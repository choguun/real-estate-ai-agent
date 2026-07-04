"""Audit log — cycle 5 T-502 (AC-SEC-07).

Append-only audit log for security-relevant events. The model is
frozen pydantic so accidental mutation in helper code raises
immediately. Writes are best-effort: an audit-write failure logs
to stderr but does NOT raise to the caller — the user's primary
request must succeed even if the audit table is degraded.

Layering:
- `AuditEvent` — the immutable event payload (pydantic model)
- `write_event(adapter, event)` — best-effort INSERT into security_events
- `record_*` helpers — typed wrappers for common actions

The full event taxonomy (action strings) is locked at module load
time so ops dashboards and SIEM rules can match against them
without parsing comments.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.supabase.base import SupabaseAdapter

logger = logging.getLogger(__name__)


# ── Action constants ────────────────────────────────────────────────
# Lock the namespace. These strings are part of the audit log's
# contract — changing them breaks every dashboard rule downstream.

ACTION_SIGNUP = "auth.signup"
ACTION_LOGIN_SUCCESS = "auth.login"
ACTION_LOGIN_FAILURE = "auth.login.failure"
ACTION_ACCEPT_INVITE = "team.accept_invite"
ACTION_CHECKOUT = "billing.checkout"
ACTION_PORTAL = "billing.portal"
ACTION_PAYMENT_FAILED = "billing.payment_failed"


# ── AuditEvent model ────────────────────────────────────────────────


class AuditEvent(BaseModel):
    """An immutable audit event ready to write.

    Fields:
        actor_id: The user who triggered the action (UUID string).
            None for anonymous actions (e.g., failed login where we
            don't yet know who the user is).
        action: The dotted-namespaced action name (e.g.,
            "auth.login", "billing.checkout").
        target_id: The resource acted on (team_id, user_id, etc.).
            None for actions without a specific target.
        ip: Client IP address. Prefer the first hop of
            X-Forwarded-For; falls back to `request.client.host`.
        user_agent: Browser/client User-Agent header.
        success: True if the action succeeded, False if rejected /
            denied / failed. Use this for "failure spike" alerts.
        metadata: Free-form JSONB dict for action-specific context
            (e.g., {"email": "alice@example.com"} for failed logins
            so we can trace the attack without exposing the password).

    Frozen so accidental mutation in helper code raises immediately.
    `extra='forbid'` on metadata would be nice but pydantic doesn't
    support that on dict fields — use a typed sub-model if it
    becomes a problem.
    """

    model_config = ConfigDict(frozen=True)

    actor_id: str | None
    action: str
    target_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    success: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── write_event (best-effort) ───────────────────────────────────────


def write_event(adapter: SupabaseAdapter, event: AuditEvent) -> None:
    """Insert an audit event. Swallows adapter exceptions.

    AC: best-effort. An audit-write failure must NOT propagate to
    the caller. The user's signup must succeed even if the audit
    table is degraded. Ops dashboards alert on
    `logger.error("audit write failed: ...")` instead.
    """
    try:
        adapter.insert(
            "security_events",
            {
                "actor_id": event.actor_id,
                "action": event.action,
                "target_id": event.target_id,
                "ip": event.ip,
                "user_agent": event.user_agent,
                "success": event.success,
                "metadata": event.metadata,
            },
        )
    except Exception as exc:  # noqa: BLE001 — intentional best-effort
        logger.error(
            "audit write failed (action=%s actor=%s): %s",
            event.action,
            event.actor_id,
            exc,
        )


# ── Typed helpers ───────────────────────────────────────────────────
# One per common action. Helpers centralize the action string + the
# shape so callers don't drift.


def record_signup(
    adapter: SupabaseAdapter,
    *,
    user_id: str,
    ip: str | None,
    user_agent: str | None,
) -> None:
    """A new user signed up. The user is both actor and target."""
    write_event(
        adapter,
        AuditEvent(
            actor_id=user_id,
            action=ACTION_SIGNUP,
            target_id=user_id,
            ip=ip,
            user_agent=user_agent,
            success=True,
        ),
    )


def record_login_success(
    adapter: SupabaseAdapter,
    *,
    user_id: str,
    ip: str | None,
    user_agent: str | None,
) -> None:
    """A user successfully authenticated."""
    write_event(
        adapter,
        AuditEvent(
            actor_id=user_id,
            action=ACTION_LOGIN_SUCCESS,
            target_id=user_id,
            ip=ip,
            user_agent=user_agent,
            success=True,
        ),
    )


def record_login_failure(
    adapter: SupabaseAdapter,
    *,
    email: str,
    ip: str | None,
    user_agent: str | None,
) -> None:
    """A login attempt was rejected (bad password, unknown email).

    `actor_id` is None because we don't yet know who they are. The
    email goes into metadata for forensic lookup — failed-login
    spikes can be triaged by `email`.
    """
    write_event(
        adapter,
        AuditEvent(
            actor_id=None,
            action=ACTION_LOGIN_FAILURE,
            target_id=None,
            ip=ip,
            user_agent=user_agent,
            success=False,
            metadata={"email": email},
        ),
    )


def record_accept_invite(
    adapter: SupabaseAdapter,
    *,
    user_id: str,
    team_id: str,
    ip: str | None,
    user_agent: str | None,
    success: bool = True,
) -> None:
    """A user accepted an invitation (or the accept was rejected)."""
    write_event(
        adapter,
        AuditEvent(
            actor_id=user_id,
            action=ACTION_ACCEPT_INVITE,
            target_id=team_id,
            ip=ip,
            user_agent=user_agent,
            success=success,
        ),
    )
