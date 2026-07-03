"""T-305 — Supabase RLS policy smoke test (RUN_LIVE_SMOKE=1 only).

This test requires a real Supabase project with 002_rls.sql applied.
It:
  1. Creates 2 teams + 2 users + 1 property in each team (via service_role)
  2. Switches to a per-user JWT and attempts cross-team read
  3. Asserts RLS denies the cross-team read (returns 0 rows)

Skip in normal CI — guarded by RUN_LIVE_SMOKE=1.
"""

from __future__ import annotations

import os

import pytest

LIVE = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_SMOKE") != "1",
    reason="Set RUN_LIVE_SMOKE=1 to run RLS live smoke tests",
)


@LIVE
def test_rls_denies_cross_team_property_read() -> None:
    """T-305 AC-RW-09: real Supabase RLS denies cross-team read."""
    from uuid import uuid4

    import httpx

    env = {
        "url": os.environ["SUPABASE_URL"],
        "service_key": os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        "alice_token": os.environ.get("ALICE_TEST_JWT", ""),
        "bob_token": os.environ.get("BOB_TEST_JWT", ""),
    }
    if not env["alice_token"] or not env["bob_token"]:
        pytest.skip(
            "ALICE_TEST_JWT and BOB_TEST_JWT not set; "
            "create 2 test users + JWTs in your dev project"
        )

    # 1) Service-role sets up: 2 teams, 2 users, 1 property each
    service_headers = {
        "apikey": env["service_key"],
        "Authorization": f"Bearer {env['service_key']}",
    }
    team_a = str(uuid4())
    team_b = str(uuid4())
    user_a = str(uuid4())
    user_b = str(uuid4())
    prop_a = str(uuid4())
    prop_b = str(uuid4())

    with httpx.Client(base_url=env["url"], headers=service_headers, timeout=10) as s:
        # Insert test rows
        s.post(
            "/rest/v1/users",
            json=[
                {"id": user_a, "email": "alice-rls@x.com", "full_name": "Alice", "team_id": team_a},
                {"id": user_b, "email": "bob-rls@x.com", "full_name": "Bob", "team_id": team_b},
            ],
        )
        s.post(
            "/rest/v1/properties",
            json=[
                {"id": prop_a, "user_id": user_a, "team_id": team_a, "title": "Alice's"},
                {"id": prop_b, "user_id": user_b, "team_id": team_b, "title": "Bob's"},
            ],
        )

        # 2) Alice attempts to read team B's property (should return 0 rows)
        alice_res = s.get(
            "/rest/v1/properties",
            params={"id": f"eq.{prop_b}"},
            headers={
                "apikey": env["service_key"],
                "Authorization": f"Bearer {env['alice_token']}",
            },
        )
        assert alice_res.status_code == 200, alice_res.text
        assert alice_res.json() == [], "RLS leaked Bob's property to Alice!"

        # 3) Alice reads her own property (should return 1 row)
        alice_own = s.get(
            "/rest/v1/properties",
            params={"id": f"eq.{prop_a}"},
            headers={
                "apikey": env["service_key"],
                "Authorization": f"Bearer {env['alice_token']}",
            },
        )
        assert alice_own.status_code == 200
        rows = alice_own.json()
        assert len(rows) == 1
        assert rows[0]["id"] == prop_a

        # Cleanup
        s.delete(
            "/rest/v1/properties",
            params={"id": f"in.({prop_a},{prop_b})"},
        )
        s.delete(
            "/rest/v1/users",
            params={"id": f"in.({user_a},{user_b})"},
        )
