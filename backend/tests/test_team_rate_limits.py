"""T-702 — Per-team rate-limit thresholds (cycle 7 AC-TRL-01..06).

8 tests covering:

Schema + table presence:
- team_rate_limits table exists in mock schema
- table has the expected columns

CRUD endpoints:
- GET /api/teams/{id}/rate_limits returns effective limits
- PATCH /api/teams/{id}/rate_limits updates overrides (owner only)
- PATCH as non-owner returns 403
- Validator rejects 0 / negative values

Enforcement:
- A team with override=3 hits 429 after 3 invites (not the
  system default of 20)
- Defaults-fallback: a team without an override row gets the
  system defaults
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.supabase._factory import get_db, reset_mock_singleton
from app.adapters.supabase.base import SupabaseAdapter
from app.config import get_settings
from app.main import create_app

# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def db() -> SupabaseAdapter:
    reset_mock_singleton()
    return get_db(get_settings())


@pytest.fixture
def app(db: SupabaseAdapter):
    return create_app()


# ── Schema presence (AC-TRL-01) ─────────────────────────────────────


def test_team_rate_limits_table_is_in_schema(db: SupabaseAdapter) -> None:
    """AC-TRL-01: the new table is in DEFAULT_SCHEMA."""
    assert "team_rate_limits" in db.schema.table_names


def test_team_rate_limits_has_required_columns(db: SupabaseAdapter) -> None:
    """AC-TRL-01: table has the override columns + FK + updated_at."""
    table = db.schema.get("team_rate_limits")
    cols = {c.name for c in table.columns}
    assert {
        "team_id",
        "login_per_15min",
        "signup_per_hour",
        "invite_per_hour",
        "updated_at",
    } <= cols


# ── CRUD: GET effective limits (AC-TRL-02) ──────────────────────────


def test_get_returns_system_defaults_when_no_override(app, db: SupabaseAdapter) -> None:
    """AC-TRL-02 + AC-TRL-06 (defaults fallback): a team without an
    override row gets the system defaults.
    """
    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/signup",
            json={
                "email": "owner-trl@example.com",
                "password": "supersecret123",
                "full_name": "Owner",
            },
        ).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        team = c.post("/api/teams", json={"name": "DefaultsTest"}).json()

        r = c.get(f"/api/teams/{team['id']}/rate_limits")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["login_per_15min"] == 5
        assert body["signup_per_hour"] == 5
        assert body["invite_per_hour"] == 20


# ── CRUD: PATCH overrides (AC-TRL-03, AC-TRL-05) ────────────────────


def test_patch_updates_overrides_and_returns_new_values(app, db: SupabaseAdapter) -> None:
    """AC-TRL-03: PATCH sets the override and the response reflects it."""
    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/signup",
            json={
                "email": "owner-trl-patch@example.com",
                "password": "supersecret123",
                "full_name": "Owner",
            },
        ).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        team = c.post("/api/teams", json={"name": "PatchTest"}).json()

        r = c.patch(
            f"/api/teams/{team['id']}/rate_limits",
            json={"login_per_15min": 3, "signup_per_hour": 2, "invite_per_hour": 5},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["login_per_15min"] == 3
        assert body["signup_per_hour"] == 2
        assert body["invite_per_hour"] == 5

        r2 = c.get(f"/api/teams/{team['id']}/rate_limits")
        assert r2.json()["login_per_15min"] == 3


def test_patch_rejects_non_owner_with_403(app, db: SupabaseAdapter) -> None:
    """AC-TRL-03: PATCH is owner-only. Non-owners get 403."""
    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/signup",
            json={
                "email": "owner-trl-priv@example.com",
                "password": "supersecret123",
                "full_name": "Owner",
            },
        ).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        team = c.post("/api/teams", json={"name": "PrivTest"}).json()

        other_tok = c.post(
            "/api/auth/signup",
            json={
                "email": "random-trl@example.com",
                "password": "supersecret123",
                "full_name": "Random",
            },
        ).json()["token"]
        c.headers["Authorization"] = f"Bearer {other_tok}"

        r = c.patch(
            f"/api/teams/{team['id']}/rate_limits",
            json={"login_per_15min": 99},
        )
        assert r.status_code == 403


def test_patch_validator_rejects_zero_and_negative(app, db: SupabaseAdapter) -> None:
    """AC-TRL-05: PATCH payload validator rejects 0 / negative values."""
    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/signup",
            json={
                "email": "owner-trl-val@example.com",
                "password": "supersecret123",
                "full_name": "Owner",
            },
        ).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        team = c.post("/api/teams", json={"name": "ValTest"}).json()

        r = c.patch(
            f"/api/teams/{team['id']}/rate_limits",
            json={"login_per_15min": 0},
        )
        assert r.status_code == 422, r.text

        r = c.patch(
            f"/api/teams/{team['id']}/rate_limits",
            json={"login_per_15min": -5},
        )
        assert r.status_code == 422, r.text


# ── Enforcement (AC-TRL-04) ────────────────────────────────────────


def test_team_override_lowers_invite_cap(app, db: SupabaseAdapter) -> None:
    """AC-TRL-04: a team with invite_per_hour=3 hits 429 after the 3rd
    invite (system default is 20).
    """
    import json as _json
    import uuid as _uuid

    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/signup",
            json={
                "email": "owner-trl-enf@example.com",
                "password": "supersecret123",
                "full_name": "Owner",
            },
        ).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        team = c.post("/api/teams", json={"name": "EnfTest"}).json()

        # Upgrade to team plan (10 seats) so seat cap doesn't trip
        payload = _json.dumps(
            {
                "id": f"evt-up-test-{team['id'][:8]}-{_uuid.uuid4().hex[:8]}",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "metadata": {"team_id": team["id"], "plan": "team"},
                        "customer": "cus_trl_enf-" + team["id"],
                        "subscription": "sub_trl_enf-" + team["id"],
                    }
                },
            }
        ).encode()
        c.post(
            "/api/billing/webhook",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": "test-mock-sig",
            },
        )

        r = c.patch(
            f"/api/teams/{team['id']}/rate_limits",
            json={"invite_per_hour": 3},
        )
        assert r.status_code == 200, r.text

        for i in range(3):
            inv = c.post(
                f"/api/teams/{team['id']}/invitations",
                json={"email": f"invitee-{i}@example.com", "role": "agent"},
            )
            assert inv.status_code == 201, (
                f"invite {i + 1} should succeed under override; got {inv.status_code}: {inv.text}"
            )
        r4 = c.post(
            f"/api/teams/{team['id']}/invitations",
            json={"email": "invitee-4@example.com", "role": "agent"},
        )
        assert r4.status_code == 429, r4.text


def test_team_default_uses_system_defaults_when_no_override(app, db: SupabaseAdapter) -> None:
    """AC-TRL-06 (defaults fallback): a team without an override row
    uses the system default invite_per_hour=20.
    """
    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/signup",
            json={
                "email": "owner-trl-defaults@example.com",
                "password": "supersecret123",
                "full_name": "Owner",
            },
        ).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        team = c.post("/api/teams", json={"name": "D"}).json()
        r = c.get(f"/api/teams/{team['id']}/rate_limits")
        assert r.status_code == 200
        assert r.json()["invite_per_hour"] == 20


# ── Service-layer unit test ───────────────────────────────────────


def test_get_effective_rate_limits_merges_overrides(db: SupabaseAdapter) -> None:
    """Service-layer merge: defaults + overrides = per-team effective."""
    from app.rate_limit_factory import get_rate_limiter
    from app.services.team_service import get_effective_rate_limits

    team = db.insert("teams", {"name": "ServiceLayerTest", "owner_id": "u-1"})

    # Without override row → all defaults
    defaults = get_rate_limiter()._limits  # noqa: SLF001
    eff = get_effective_rate_limits(db, team_id=team["id"])
    assert eff["login_per_15min"] == defaults["auth.login"].max_calls
    assert eff["signup_per_hour"] == defaults["auth.signup"].max_calls
    assert eff["invite_per_hour"] == defaults["team.invite"].max_calls

    # With override → that value is used, others stay default
    db.insert(
        "team_rate_limits",
        {
            "team_id": team["id"],
            "login_per_15min": 2,
            "signup_per_hour": 99,
            "invite_per_hour": 1,
        },
    )
    eff2 = get_effective_rate_limits(db, team_id=team["id"])
    assert eff2["login_per_15min"] == 2
    assert eff2["signup_per_hour"] == 99
    assert eff2["invite_per_hour"] == 1
