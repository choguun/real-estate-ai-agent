"""T-105 — Live smoke tests for the real adapters.

These tests hit the REAL Supabase project + REAL LINE Messaging API +
REAL Anthropic API. They are **skipped by default** because:

1. They require real credentials (secrets) not available by default
2. Local dev should run on mocks (`USE_MOCKS=true`) for speed

Run locally against a dev project:

```bash
export RUN_LIVE_SMOKE=1
export SUPABASE_URL=https://abc.supabase.co
export SUPABASE_ANON_KEY=eyJ...
export SUPABASE_SERVICE_ROLE_KEY=eyJ...  # admin
export LINE_CHANNEL_SECRET=...
export LINE_CHANNEL_ACCESS_TOKEN=...
export ANTHROPIC_API_KEY=sk-...
export SUPABASE_STORAGE_BUCKET=uploads
export SUPABASE_STORAGE_PRIVATE=false
pytest -q tests/test_live_smoke.py
```

**Cleanup:** each test uses a unique ID prefix so reruns don't collide.
A live smoke run creates real rows in your dev project; clean them up
with the `cleanup_live_smoke` test at the end.
"""

from __future__ import annotations

import os
import uuid

import pytest

LIVE = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_SMOKE") != "1",
    reason="Set RUN_LIVE_SMOKE=1 to run live smoke tests against a real dev project.",
)


def _live_env() -> dict[str, str]:
    """Snapshot of required env vars. Skips if any are missing."""
    keys = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "LINE_CHANNEL_SECRET",
        "LINE_CHANNEL_ACCESS_TOKEN",
        "ANTHROPIC_API_KEY",
    ]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"missing env: {', '.join(missing)}")
    return {k: os.environ[k] for k in keys}


def _run_id() -> str:
    return f"smoke-{uuid.uuid4().hex[:12]}"


@LIVE
def test_supabase_signup_and_lookup() -> None:
    """Live: POST /api/auth/signup creates a real row in Supabase."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    _live_env()
    client = TestClient(create_app())
    email = f"{_run_id()}@live-smoke.example.com"
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "supersecret123", "full_name": "Smoke"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email


@LIVE
def test_line_webhook_signature_against_live_creds() -> None:
    """Live: signing + verifying with the real LINE channel secret works."""
    import json

    from app.adapters.line.base import (
        sign_line_webhook,
        verify_line_webhook,
    )

    env = _live_env()
    body = json.dumps({"events": []}, separators=(",", ":")).encode("utf-8")
    signature = sign_line_webhook(body, env["LINE_CHANNEL_SECRET"])
    assert verify_line_webhook(body, signature, env["LINE_CHANNEL_SECRET"]) is True
    # Tampered body → fail
    assert verify_line_webhook(body + b"x", signature, env["LINE_CHANNEL_SECRET"]) is False


@LIVE
def test_anthropic_real_listing_generation() -> None:
    """Live: real Anthropic API generates a Thai listing."""
    from app.adapters.ai.anthropic_real import AnthropicRealAdapter
    from app.domain.listing import ListingRequest, Platform, PropertySummary

    env = _live_env()
    adapter = AnthropicRealAdapter(api_key=env["ANTHROPIC_API_KEY"])
    request = ListingRequest(
        property=PropertySummary(
            title="คอนโดทดสอบ live",
            property_type="condo",
            price=3_500_000,
            size_sqm=32,
            bedrooms=1,
            bathrooms=1,
            district="วัฒนา",
            province="กรุงเทพมหานคร",
            near_bts_mrt="BTS ทองหล่อ",
        ),
        platforms=[Platform.ddproperty],
    )
    result = adapter.generate(request)
    assert result.title
    assert result.description
    assert "คอนโด" in result.title or "คอนโด" in result.description


@LIVE
def test_storage_upload_and_get() -> None:
    """Live: real Supabase Storage upload + get round-trip."""
    from app.adapters.storage.supabase_real import SupabaseStorageAdapter

    env = _live_env()
    adapter = SupabaseStorageAdapter(
        base_url=env["SUPABASE_URL"],
        api_key=env["SUPABASE_SERVICE_ROLE_KEY"],
        bucket=os.environ.get("SUPABASE_STORAGE_BUCKET", "uploads"),
        private=os.environ.get("SUPABASE_STORAGE_PRIVATE", "false").lower() == "true",
    )
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    obj = adapter.upload(png_bytes, filename=f"{_run_id()}.png", content_type="image/png")
    assert obj.key.endswith(".png")
    assert obj.size == len(png_bytes)
    # Round-trip
    fetched = adapter.get(obj.key)
    assert fetched is not None
    data, ct = fetched
    assert data == png_bytes
    # Cleanup
    assert adapter.delete(obj.key) is True


@LIVE
def test_cleanup_live_smoke() -> None:
    """No-op placeholder. Real cleanup happens in each test (delete after upload).

    For Supabase rows created by test_supabase_signup_and_lookup: clean
    them up via SQL in your dev project's SQL editor, or run:
        DELETE FROM users WHERE email LIKE 'smoke-%@live-smoke.example.com';
    """
    pass
