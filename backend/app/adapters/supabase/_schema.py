"""Canonical schema — Python mirror of `migrations/*.sql`.

This is the **source of truth** for the mock Supabase adapter. The SQL
files are kept in sync as documentation for the real Postgres schema. A
test asserts both files declare the same tables.

Default-value semantics:
- Callables are invoked at insert time (per-row).
- Static defaults (`True`, `False`, `"agent"`, `"draft"`) are applied
  when the caller omits the column.

Types are PG types (e.g. `UUID`, `TEXT`, `BOOLEAN`, `NUMERIC`, `JSONB`,
`TIMESTAMPTZ`). The mock only uses them as metadata; the real adapter
passes them straight to Postgres.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ─── Default value factories ───────────────────────────────────────────
def _uuid() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    """ISO 8601 UTC timestamp with timezone suffix.

    Public helper — used by `mock.py` for `updated_at` re-stamping and
    anywhere else we need the canonical timestamp format.
    """
    return datetime.now(timezone.utc).isoformat()


# Internal alias preserved for the table definitions below.
_now = now_iso


def _true() -> bool:
    return True


def _false() -> bool:
    return False


def _role_agent() -> str:
    return "agent"


def _role_owner() -> str:
    return "owner"


def _status_draft() -> str:
    return "draft"


def _status_new() -> str:
    return "new"


def _status_active() -> str:
    return "active"


def _status_trialing() -> str:
    return "trialing"


def _line_source() -> str:
    return "line"


def _text_type() -> str:
    return "text"


def _json_array() -> list[Any]:
    return []


# ─── Schema data classes ───────────────────────────────────────────────
@dataclass(frozen=True)
class Column:
    name: str
    type: str  # PG type
    nullable: bool = True
    default: Callable[[], Any] | Any = None


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    unique_constraints: tuple[tuple[str, ...], ...] = ()
    _by_name: dict[str, Column] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_name", {c.name: c for c in self.columns})

    def has(self, col: str) -> bool:
        return col in self._by_name


@dataclass(frozen=True)
class Schema:
    tables: tuple[Table, ...]
    _by_name: dict[str, Table] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_name", {t.name: t for t in self.tables})

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    def get(self, name: str) -> Table:
        if name not in self._by_name:
            raise KeyError(f"Unknown table: {name!r}")
        return self._by_name[name]

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(self._by_name.keys())


# ─── Helpers to keep declarations tight ────────────────────────────────
def _col(name: str, type_: str, *, nullable: bool = True, default: Any = None) -> Column:
    """Sugar so each table can fit on one line."""
    if default is _MISSING:
        default = None
    return Column(name=name, type=type_, nullable=nullable, default=default)


_MISSING: Any = object()


# ─── Tables (mirror migrations/*.sql) ─────────────────────────────────
USERS = Table(
    "users",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("email", "TEXT", nullable=False),
        _col("full_name", "TEXT", nullable=False),
        _col("password_hash", "TEXT"),
        _col("phone", "TEXT"),
        _col("avatar_url", "TEXT"),
        _col("role", "TEXT", default=_role_agent),
        _col("team_id", "UUID"),
        _col("line_user_id", "TEXT"),
        _col("is_active", "BOOLEAN", default=_true),
        _col("created_at", "TIMESTAMPTZ", default=_now),
        _col("updated_at", "TIMESTAMPTZ", default=_now),
    ),
)

TEAMS = Table(
    "teams",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("name", "TEXT", nullable=False),
        _col("owner_id", "UUID", nullable=False),
        _col("plan", "TEXT", default=lambda: "starter"),
        _col("plan_limits", "JSONB"),
        _col("created_at", "TIMESTAMPTZ", default=_now),
        _col("updated_at", "TIMESTAMPTZ", default=_now),
        _col("deleted_at", "TIMESTAMPTZ"),
    ),
)

# 002_teams.sql: team_memberships join table
TEAM_MEMBERSHIPS = Table(
    "team_memberships",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("team_id", "UUID", nullable=False),
        _col("user_id", "UUID", nullable=False),
        _col("role", "TEXT", nullable=False, default=_role_agent),
        _col("joined_at", "TIMESTAMPTZ", default=_now),
        _col("left_at", "TIMESTAMPTZ"),
        _col("removed_by", "UUID"),
    ),
    unique_constraints=(("team_id", "user_id"),),
)

# 002_teams.sql: team_invitations
TEAM_INVITATIONS = Table(
    "team_invitations",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("team_id", "UUID", nullable=False),
        _col("email", "TEXT", nullable=False),
        _col("role", "TEXT", nullable=False, default=_role_agent),
        _col("token", "TEXT", nullable=False),
        _col("invited_by", "UUID", nullable=False),
        _col("invited_at", "TIMESTAMPTZ", default=_now),
        _col("expires_at", "TIMESTAMPTZ", nullable=False),
        _col("accepted_at", "TIMESTAMPTZ"),
        _col("accepted_by", "UUID"),
    ),
    unique_constraints=(("token",),),
)

# 003_billing.sql: billing_customers (NEW — cycle 4)
BILLING_CUSTOMERS = Table(
    "billing_customers",
    (
        _col("team_id", "UUID", nullable=False, default=_uuid),
        _col("stripe_customer_id", "TEXT"),
        _col("stripe_subscription_id", "TEXT"),
        _col("plan", "TEXT", default=lambda: "starter"),
        _col("status", "TEXT", default=_status_trialing),
        _col("current_period_start", "TIMESTAMPTZ"),
        _col("current_period_end", "TIMESTAMPTZ"),
        _col("cancel_at_period_end", "BOOLEAN", default=_false),
        _col("trial_ends_at", "TIMESTAMPTZ"),
        _col("created_at", "TIMESTAMPTZ", default=_now),
        _col("updated_at", "TIMESTAMPTZ", default=_now),
    ),
    unique_constraints=(("team_id",), ("stripe_customer_id",), ("stripe_subscription_id",)),
)

# 003_billing.sql: billing_events (NEW — cycle 4)
BILLING_EVENTS = Table(
    "billing_events",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("team_id", "UUID"),
        _col("stripe_event_id", "TEXT", nullable=False),
        _col("event_type", "TEXT", nullable=False),
        _col("payload", "JSONB", nullable=False),
        _col("received_at", "TIMESTAMPTZ", default=_now),
        _col("processed_at", "TIMESTAMPTZ"),
    ),
    unique_constraints=(("stripe_event_id",),),
)

PROPERTIES = Table(
    "properties",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("user_id", "UUID", nullable=False),
        _col("team_id", "UUID"),
        _col("title", "TEXT"),
        _col("description", "TEXT"),
        _col("property_type", "TEXT"),
        _col("price", "NUMERIC(15,2)"),
        _col("size_sqm", "NUMERIC(10,2)"),
        _col("bedrooms", "INTEGER"),
        _col("bathrooms", "INTEGER"),
        _col("floor", "INTEGER"),
        _col("address", "TEXT"),
        _col("district", "TEXT"),
        _col("province", "TEXT"),
        _col("near_bts_mrt", "TEXT"),
        _col("foreign_quota", "BOOLEAN", default=_false),
        _col("status", "TEXT", default=_status_draft),
        _col("images", "JSONB", default=_json_array),
        _col("created_at", "TIMESTAMPTZ", default=_now),
        _col("updated_at", "TIMESTAMPTZ", default=_now),
    ),
)

LEADS = Table(
    "leads",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("user_id", "UUID", nullable=False),
        _col("team_id", "UUID"),
        _col("name", "TEXT"),
        _col("phone", "TEXT"),
        _col("line_user_id", "TEXT"),
        _col("email", "TEXT"),
        _col("source", "TEXT", default=_line_source),
        _col("status", "TEXT", default=_status_new),
        _col("interest_type", "TEXT"),
        _col("budget_min", "NUMERIC(15,2)"),
        _col("budget_max", "NUMERIC(15,2)"),
        _col("preferred_areas", "TEXT[]", default=_json_array),
        _col("notes", "TEXT"),
        _col("last_contacted_at", "TIMESTAMPTZ"),
        _col("created_at", "TIMESTAMPTZ", default=_now),
        _col("updated_at", "TIMESTAMPTZ", default=_now),
    ),
)

MESSAGES = Table(
    "messages",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("lead_id", "UUID"),
        _col("user_id", "UUID", nullable=False),
        _col("team_id", "UUID"),
        _col("direction", "TEXT"),
        _col("message_type", "TEXT", default=_text_type),
        _col("content", "TEXT"),
        _col("raw_data", "JSONB"),
        _col("is_ai_generated", "BOOLEAN", default=_false),
        _col("created_at", "TIMESTAMPTZ", default=_now),
    ),
)

APPOINTMENTS = Table(
    "appointments",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("user_id", "UUID", nullable=False),
        _col("team_id", "UUID"),
        _col("lead_id", "UUID"),
        _col("property_id", "UUID"),
        _col("scheduled_at", "TIMESTAMPTZ", nullable=False),
        _col("duration_minutes", "INTEGER", default=lambda: 60),
        _col("status", "TEXT", default=lambda: "scheduled"),
        _col("notes", "TEXT"),
        _col("google_event_id", "TEXT"),
        _col("created_at", "TIMESTAMPTZ", default=_now),
        _col("updated_at", "TIMESTAMPTZ", default=_now),
    ),
)

GENERATED_LISTINGS = Table(
    "generated_listings",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("property_id", "UUID", nullable=False),
        _col("user_id", "UUID", nullable=False),
        _col("team_id", "UUID"),
        _col("platform", "TEXT"),
        _col("title", "TEXT"),
        _col("description", "TEXT"),
        _col("hashtags", "TEXT[]", default=_json_array),
        _col("seo_keywords", "TEXT[]", default=_json_array),
        _col("ai_model", "TEXT"),
        _col("prompt_used", "TEXT"),
        _col("raw_response", "JSONB"),
        _col("is_published", "BOOLEAN", default=_false),
        _col("created_at", "TIMESTAMPTZ", default=_now),
    ),
)

CONTRACTS = Table(
    "contracts",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("user_id", "UUID", nullable=False),
        _col("team_id", "UUID"),
        _col("property_id", "UUID"),
        _col("lead_id", "UUID"),
        _col("contract_type", "TEXT"),
        _col("status", "TEXT", default=lambda: "draft"),
        _col("content", "TEXT"),
        _col("file_url", "TEXT"),
        _col("signed_at", "TIMESTAMPTZ"),
        _col("created_at", "TIMESTAMPTZ", default=_now),
        _col("updated_at", "TIMESTAMPTZ", default=_now),
    ),
)

USER_SETTINGS = Table(
    "user_settings",
    (
        _col("user_id", "UUID", nullable=False, default=_uuid),
        _col("default_property_type", "TEXT"),
        _col("notification_preferences", "JSONB"),
        _col("ai_model_preference", "TEXT", default=lambda: "claude-3.5"),
        _col("created_at", "TIMESTAMPTZ", default=_now),
        _col("updated_at", "TIMESTAMPTZ", default=_now),
    ),
)

AUDIT_LOGS = Table(
    "audit_logs",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("user_id", "UUID"),
        _col("action", "TEXT", nullable=False),
        _col("table_name", "TEXT"),
        _col("record_id", "UUID"),
        _col("old_data", "JSONB"),
        _col("new_data", "JSONB"),
        _col("created_at", "TIMESTAMPTZ", default=_now),
    ),
)


# 006_team_rate_limits.sql: per-team overrides (NEW — cycle 7 T-702)
TEAM_RATE_LIMITS = Table(
    "team_rate_limits",
    (
        _col("team_id", "UUID", nullable=False, default=_uuid),
        _col("login_per_15min", "INT", nullable=False, default=lambda: 5),
        _col("signup_per_hour", "INT", nullable=False, default=lambda: 5),
        _col("invite_per_hour", "INT", nullable=False, default=lambda: 20),
        _col("updated_at", "TIMESTAMPTZ", nullable=False, default=_now),
    ),
    unique_constraints=(("team_id",),),
)


# 004_security_events.sql: append-only audit log (NEW — cycle 5 T-502)
SECURITY_EVENTS = Table(
    "security_events",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("actor_id", "UUID"),
        _col("action", "TEXT", nullable=False),
        _col("target_id", "UUID"),
        _col("ip", "TEXT"),
        _col("user_agent", "TEXT"),
        _col("success", "BOOLEAN", nullable=False),
        _col("metadata", "JSONB", default=lambda: {}),
        _col("created_at", "TIMESTAMPTZ", nullable=False, default=_now),
    ),
)


# 007_mfa.sql: TOTP MFA (NEW — cycle 8 T-801)
USER_MFA = Table(
    "user_mfa",
    (
        _col("user_id", "UUID", nullable=False, default=_uuid),
        _col("secret_encrypted", "TEXT", nullable=False),
        _col("enrolled_at", "TIMESTAMPTZ", nullable=False, default=_now),
        _col("last_verified_step", "INT"),
    ),
    unique_constraints=(("user_id",),),
)

MFA_RECOVERY_CODES = Table(
    "mfa_recovery_codes",
    (
        _col("id", "UUID", nullable=False, default=_uuid),
        _col("user_id", "UUID", nullable=False, default=_uuid),
        _col("code_hash", "TEXT", nullable=False),
        _col("used_at", "TIMESTAMPTZ"),
        _col("created_at", "TIMESTAMPTZ", nullable=False, default=_now),
    ),
)


DEFAULT_SCHEMA = Schema(
    (
        USERS,
        TEAMS,
        TEAM_MEMBERSHIPS,
        TEAM_INVITATIONS,
        BILLING_CUSTOMERS,  # NEW (cycle 4)
        BILLING_EVENTS,  # NEW (cycle 4)
        PROPERTIES,
        LEADS,
        MESSAGES,
        APPOINTMENTS,
        GENERATED_LISTINGS,
        CONTRACTS,
        USER_SETTINGS,
        AUDIT_LOGS,
        SECURITY_EVENTS,  # NEW (cycle 5)
        TEAM_RATE_LIMITS,  # NEW (cycle 7)
        USER_MFA,  # NEW (cycle 8)
        MFA_RECOVERY_CODES,  # NEW (cycle 8)
    )
)
