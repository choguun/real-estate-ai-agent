"""Tests for the LINE webhook signature gate — ST-009 + ST-010 + edges."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.line import (
    SIGNATURE_HEADER,
    sign_line_webhook,
    verify_line_webhook,
)
from app.adapters.line.mock import LineMockAdapter
from app.config import Settings
from app.main import create_app

# ─── Fixtures ───────────────────────────────────────────────────────────
SECRET = "test-channel-secret-12345"
LINE_BODY = json.dumps(
    {
        "destination": "Uxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "events": [
            {
                "type": "message",
                "timestamp": 1700000000000,
                "source": {"type": "user", "userId": "U-test"},
                "message": {"id": "1", "type": "text", "text": "Hello"},
            }
        ],
    }
).encode("utf-8")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient wired with the secret baked into Settings."""
    app = create_app(Settings(line_channel_secret=SECRET, use_real_line=False))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_line() -> LineMockAdapter:
    return LineMockAdapter(channel_secret=SECRET)


# ─── ST-009: valid signature ───────────────────────────────────────────
def test_valid_signature_returns_200(client: TestClient, mock_line: LineMockAdapter) -> None:
    sig = mock_line.sign(LINE_BODY)
    res = client.post(
        "/webhook/line",
        content=LINE_BODY,
        headers={
            SIGNATURE_HEADER: sig,
            "Content-Type": "application/json",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["received"] == 1


# ─── ST-010: bad signature ─────────────────────────────────────────────
def test_invalid_signature_returns_401(client: TestClient) -> None:
    res = client.post(
        "/webhook/line",
        content=LINE_BODY,
        headers={
            SIGNATURE_HEADER: "definitely-not-valid-base64-hmac",
            "Content-Type": "application/json",
        },
    )
    assert res.status_code == 401
    assert "Invalid signature" in res.json()["detail"]


def test_missing_signature_returns_401(client: TestClient) -> None:
    res = client.post(
        "/webhook/line",
        content=LINE_BODY,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 401
    assert "Missing" in res.json()["detail"]


def test_body_tampered_after_signing_returns_401(
    client: TestClient, mock_line: LineMockAdapter
) -> None:
    sig = mock_line.sign(LINE_BODY)
    tampered = LINE_BODY + b"  "  # trailing whitespace
    res = client.post(
        "/webhook/line",
        content=tampered,
        headers={
            SIGNATURE_HEADER: sig,
            "Content-Type": "application/json",
        },
    )
    assert res.status_code == 401


def test_signature_from_different_secret_returns_401() -> None:
    app = create_app(Settings(line_channel_secret="server-secret"))
    other = LineMockAdapter(channel_secret="attacker-secret")
    sig = other.sign(LINE_BODY)
    with TestClient(app) as c:
        res = c.post(
            "/webhook/line",
            content=LINE_BODY,
            headers={
                SIGNATURE_HEADER: sig,
                "Content-Type": "application/json",
            },
        )
    assert res.status_code == 401


def test_empty_string_signature_returns_401(client: TestClient) -> None:
    res = client.post(
        "/webhook/line",
        content=LINE_BODY,
        headers={SIGNATURE_HEADER: "", "Content-Type": "application/json"},
    )
    assert res.status_code == 401


# ─── Verification bypasses ─────────────────────────────────────────────
def test_invalid_json_after_signature_passes_returns_400(
    client: TestClient, mock_line: LineMockAdapter
) -> None:
    bad = b"not-json-at-all"
    sig = mock_line.sign(bad)
    res = client.post(
        "/webhook/line",
        content=bad,
        headers={
            SIGNATURE_HEADER: sig,
            "Content-Type": "application/json",
        },
    )
    # Signature verified → body parsing fails → 400, NOT 401.
    assert res.status_code == 400


def test_no_db_writes_on_unverified_request(
    client: TestClient,
) -> None:
    """Even if a body sends 'events', unverified requests must write nothing."""
    # Override the DB so we can inspect it.
    app = client.app  # the TestClient's app
    from app.adapters.supabase.mock import MockSupabaseAdapter
    from app.deps import get_db_dep

    fresh = MockSupabaseAdapter()
    app.dependency_overrides[get_db_dep] = lambda: fresh
    payload = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "source": {"userId": "U-evil"},
                    "message": {"type": "text", "text": "data"},
                }
            ]
        }
    ).encode("utf-8")
    res = client.post(
        "/webhook/line",
        content=payload,
        headers={SIGNATURE_HEADER: "garbage"},
    )
    assert res.status_code == 401
    leads = fresh.query("leads")
    msgs = fresh.query("messages")
    assert leads == []
    assert msgs == []
    app.dependency_overrides.clear()


# ─── Helper coverage ───────────────────────────────────────────────────
def test_sign_helper_round_trips() -> None:
    sig = sign_line_webhook(LINE_BODY, SECRET)
    assert verify_line_webhook(LINE_BODY, sig, SECRET) is True


def test_verify_returns_false_for_none_signature() -> None:
    assert verify_line_webhook(LINE_BODY, None, SECRET) is False


def test_verify_returns_false_for_empty_signature() -> None:
    assert verify_line_webhook(LINE_BODY, "", SECRET) is False


def test_replay_of_same_signed_payload_returns_200_twice(
    client: TestClient, mock_line: LineMockAdapter
) -> None:
    """Idempotency lives in T-009; for T-008 we just verify the gate passes twice."""
    sig = mock_line.sign(LINE_BODY)
    headers = {SIGNATURE_HEADER: sig, "Content-Type": "application/json"}

    r1 = client.post("/webhook/line", content=LINE_BODY, headers=headers)
    r2 = client.post("/webhook/line", content=LINE_BODY, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
