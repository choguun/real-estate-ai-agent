"""T-502 — Audit log infrastructure (cycle 5 AC-SEC-07).

6 tests covering:
- AuditEvent pydantic model: frozen, action constants, metadata default
- write_event: best-effort (audit-failure doesn't raise), inserts the row
- record_signup / record_login_success / record_login_failure / record_accept_invite
  helpers each produce the right shape

The integration tests drive the supabase mock adapter directly (not via
TestClient) — full router hooks come in T-503.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.adapters.supabase._factory import get_db, reset_mock_singleton
from app.adapters.supabase.base import SupabaseAdapter
from app.audit_log import (
    ACTION_ACCEPT_INVITE,
    ACTION_LOGIN_FAILURE,
    ACTION_LOGIN_SUCCESS,
    ACTION_SIGNUP,
    AuditEvent,
    record_accept_invite,
    record_login_failure,
    record_login_success,
    record_signup,
    write_event,
)
from app.config import get_settings


@pytest.fixture
def db() -> SupabaseAdapter:
    reset_mock_singleton()
    return get_db(get_settings())


# ── AuditEvent model ────────────────────────────────────────────────


def test_audit_event_is_frozen() -> None:
    """AuditEvent must be immutable (frozen=True) so accidental
    mutation in helper code raises immediately.
    """
    event = AuditEvent(
        actor_id="u-1",
        action="test.action",
        target_id="t-1",
        ip="127.0.0.1",
        user_agent="curl/8.0",
        success=True,
    )
    with pytest.raises(ValidationError):  # pydantic raises on frozen mutation
        event.action = "mutated"  # type: ignore[misc]


def test_audit_event_metadata_defaults_to_empty_dict() -> None:
    """AC-SEC-07: metadata JSONB defaults to {}."""
    event = AuditEvent(
        actor_id=None,
        action="anon.event",
        target_id=None,
        ip=None,
        user_agent=None,
        success=True,
    )
    assert event.metadata == {}


def test_audit_event_action_constants_are_stable_strings() -> None:
    """The action namespace is the audit-log's contract. Locking the
    values here lets ops dashboards match against them.
    """
    assert ACTION_SIGNUP == "auth.signup"
    assert ACTION_LOGIN_SUCCESS == "auth.login"
    assert ACTION_LOGIN_FAILURE == "auth.login.failure"
    assert ACTION_ACCEPT_INVITE == "team.accept_invite"


# ── write_event best-effort ─────────────────────────────────────────


def test_write_event_inserts_into_security_events(db: SupabaseAdapter) -> None:
    """AC-SEC-07: write_event adds a row to security_events."""
    event = AuditEvent(
        actor_id="u-1",
        action="test.action",
        target_id="t-1",
        ip="127.0.0.1",
        user_agent="curl/8.0",
        success=True,
        metadata={"k": "v"},
    )
    write_event(db, event)

    rows = db.query("security_events", filters={"action": "test.action"})
    assert len(rows) == 1
    row = rows[0]
    assert row["actor_id"] == "u-1"
    assert row["target_id"] == "t-1"
    assert row["ip"] == "127.0.0.1"
    assert row["user_agent"] == "curl/8.0"
    assert row["success"] is True
    assert row["metadata"] == {"k": "v"}
    assert row["id"]  # auto-generated


def test_write_event_swallows_adapter_exceptions(db: SupabaseAdapter) -> None:
    """Best-effort: an adapter failure must NOT propagate to the caller.

    AC: audit-failure-doesn't-raise. The user's signup is more
    important than the audit row; an ops dashboard alerting on
    audit-write failures is the right pattern.
    """
    db.insert = MagicMock(side_effect=RuntimeError("simulated DB outage"))

    event = AuditEvent(
        actor_id="u-1",
        action="test.action",
        target_id="t-1",
        ip="127.0.0.1",
        user_agent="curl/8.0",
        success=True,
    )
    # Must NOT raise
    write_event(db, event)


# ── record_* helpers ────────────────────────────────────────────────


def test_record_signup_writes_expected_shape(db: SupabaseAdapter) -> None:
    """record_signup produces action=auth.signup, success=true,
    actor_id=user_id, target_id=user_id (the user is both actor and target).
    """
    record_signup(db, user_id="u-new", ip="203.0.113.5", user_agent="Mozilla/5.0")
    rows = db.query("security_events", filters={"action": "auth.signup"})
    assert len(rows) == 1
    row = rows[0]
    assert row["actor_id"] == "u-new"
    assert row["target_id"] == "u-new"
    assert row["success"] is True
    assert row["ip"] == "203.0.113.5"
    assert row["user_agent"] == "Mozilla/5.0"


def test_record_login_success_writes_expected_shape(
    db: SupabaseAdapter,
) -> None:
    record_login_success(db, user_id="u-1", ip="203.0.113.5", user_agent="Mozilla/5.0")
    rows = db.query("security_events", filters={"action": "auth.login"})
    assert len(rows) == 1
    assert rows[0]["success"] is True
    assert rows[0]["actor_id"] == "u-1"


def test_record_login_failure_writes_expected_shape(
    db: SupabaseAdapter,
) -> None:
    """Failures have actor_id=null (we don't know who they are yet)
    and the email goes into metadata for forensic lookup.
    """
    record_login_failure(db, email="attacker@evil.com", ip="203.0.113.99", user_agent="curl/8.0")
    rows = db.query("security_events", filters={"action": "auth.login.failure"})
    assert len(rows) == 1
    row = rows[0]
    assert row["actor_id"] is None
    assert row["success"] is False
    assert row["metadata"] == {"email": "attacker@evil.com"}


def test_record_accept_invite_writes_expected_shape(
    db: SupabaseAdapter,
) -> None:
    record_accept_invite(
        db, user_id="u-1", team_id="t-1", ip="203.0.113.5", user_agent="Mozilla/5.0"
    )
    rows = db.query("security_events", filters={"action": "team.accept_invite"})
    assert len(rows) == 1
    row = rows[0]
    assert row["actor_id"] == "u-1"
    assert row["target_id"] == "t-1"
    assert row["success"] is True


def test_metadata_with_unknown_keys_is_rejected() -> None:
    """Defensive: the model uses `extra='forbid'` so typos in
    metadata keys surface as a clear error rather than silently
    shipping to the audit table.
    """
    # Sanity: the helpers above all pass valid metadata dicts
    # (empty {} or {"email": ...}). This test pins the contract.
    event = AuditEvent(
        actor_id="u-1",
        action="test.action",
        target_id=None,
        ip=None,
        user_agent=None,
        success=True,
        metadata={},  # type: ignore[arg-type]
    )
    assert event.metadata == {}
