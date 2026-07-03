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
def auth_client(client: TestClient):
    """Augments `client` with a signed-up user and returns (client, user_id)."""
    sig = client.post(
        "/api/auth/signup",
        json={
            "email": "agent@example.com",
            "full_name": "Agent",
            "password": "password123",
        },
    ).json()
    return client, sig["user"]["id"]


def _sign(body: bytes) -> str:
    return sign_line_webhook(body, SECRET)


def _event(event_id: str, user_id: str = "U-test", text: str = "Hello") -> dict:
    return {
        "type": "message",
        "event_id": event_id,
        "timestamp": 1700000000000,
        "source": {"type": "user", "userId": user_id},
        "message": {"id": f"msg-{event_id}", "type": "text", "text": text},
    }


# ─── Lead + Message pipeline (T-009) ─────────────────────────────


def test_well_formed_event_creates_lead_and_message(auth_client) -> None:
    c, _agent_id = auth_client
    body = json.dumps({"events": [_event("evt-001")]}).encode()
    res = c.post(
        "/webhook/line",
        content=body,
        headers={SIGNATURE_HEADER: _sign(body), "Content-Type": "application/json"},
    )
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["ok"] is True
    assert j["received"] == 1
    assert j["processed"] == 1
    r = j["results"][0]
    assert r["processed"] is True
    assert r["new_lead"] is True
    assert r["new_message"] is True
    assert r["reason"] == "ok"


def test_replay_of_same_event_id_is_ignored(auth_client) -> None:
    c, _ = auth_client
    body = json.dumps({"events": [_event("evt-dup")]}).encode()
    sig = _sign(body)
    headers = {SIGNATURE_HEADER: sig, "Content-Type": "application/json"}
    r1 = c.post("/webhook/line", content=body, headers=headers)
    r2 = c.post("/webhook/line", content=body, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["processed"] == 0
    assert r2.json()["results"][0]["reason"] == "replay"


def test_two_events_same_user_one_lead_two_messages(auth_client) -> None:
    c, _ = auth_client
    body = json.dumps({"events": [_event("evt-A"), _event("evt-B", text="second")]}).encode()
    sig = _sign(body)
    res = c.post(
        "/webhook/line",
        content=body,
        headers={SIGNATURE_HEADER: sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["received"] == 2
    assert j["processed"] == 2
    assert j["results"][0]["new_lead"] is True
    assert j["results"][1]["new_lead"] is False
    # Both messages should reference the same lead_id.
    assert j["results"][0]["lead_id"] == j["results"][1]["lead_id"]


def test_non_message_event_is_ignored(auth_client) -> None:
    c, _ = auth_client
    body = json.dumps(
        {
            "events": [
                {
                    "type": "follow",
                    "event_id": "follow-1",
                    "source": {"type": "user", "userId": "U-new"},
                    "timestamp": 1,
                }
            ]
        }
    ).encode()
    sig = _sign(body)
    res = c.post(
        "/webhook/line",
        content=body,
        headers={SIGNATURE_HEADER: sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200
    r = res.json()["results"][0]
    assert r["processed"] is False
    assert r["reason"] == "non_message"


def test_event_missing_source_is_ignored(auth_client) -> None:
    c, _ = auth_client
    body = json.dumps({"events": [{"type": "message", "event_id": "x"}]}).encode()
    sig = _sign(body)
    res = c.post(
        "/webhook/line",
        content=body,
        headers={SIGNATURE_HEADER: sig, "Content-Type": "application/json"},
    )
    r = res.json()["results"][0]
    assert r["processed"] is False
    assert r["reason"] == "no_source"


def test_event_missing_event_id_is_ignored(auth_client) -> None:
    c, _ = auth_client
    body = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "source": {"userId": "U-x"},
                    "message": {"type": "text", "text": "y"},
                }
            ]
        }
    ).encode()
    sig = _sign(body)
    res = c.post(
        "/webhook/line",
        content=body,
        headers={SIGNATURE_HEADER: sig, "Content-Type": "application/json"},
    )
    r = res.json()["results"][0]
    assert r["processed"] is False
    assert r["reason"] == "no_event_id"


def test_empty_events_returns_200(auth_client) -> None:
    c, _ = auth_client
    body = json.dumps({"events": []}).encode()
    sig = _sign(body)
    res = c.post(
        "/webhook/line",
        content=body,
        headers={SIGNATURE_HEADER: sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["received"] == 0
    assert res.json()["processed"] == 0


def test_webhook_without_any_user_returns_503(client: TestClient) -> None:
    body = json.dumps({"events": [_event("evt-orphan")]}).encode()
    sig = _sign(body)
    res = client.post(
        "/webhook/line",
        content=body,
        headers={SIGNATURE_HEADER: sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 503


@pytest.fixture
def mock_line() -> LineMockAdapter:
    return LineMockAdapter(channel_secret=SECRET)


# ─── ST-009: valid signature ───────────────────────────────────────────
def test_valid_signature_returns_200(client: TestClient, mock_line: LineMockAdapter) -> None:
    # Use an empty-events payload so the signature gate is exercised without
    # needing an agent (T-009 covered well-formed events end-to-end).
    empty = json.dumps({"events": []}).encode()
    sig = mock_line.sign(empty)
    res = client.post(
        "/webhook/line",
        content=empty,
        headers={
            SIGNATURE_HEADER: sig,
            "Content-Type": "application/json",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["received"] == 0


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


@pytest.fixture(autouse=True)
def _isolate():
    from app.adapters.supabase._factory import reset_mock_singleton

    reset_mock_singleton()
    yield
    reset_mock_singleton()

    # ─── Helper coverage ───────────────────────────────────────────────────

    sig = sign_line_webhook(LINE_BODY, SECRET)
    assert verify_line_webhook(LINE_BODY, sig, SECRET) is True


def test_verify_returns_false_for_none_signature() -> None:
    assert verify_line_webhook(LINE_BODY, None, SECRET) is False


def test_verify_returns_false_for_empty_signature() -> None:
    assert verify_line_webhook(LINE_BODY, "", SECRET) is False


def test_replay_of_same_signed_payload_returns_200_twice(
    client: TestClient, mock_line: LineMockAdapter
) -> None:
    """Idempotency lives in T-009; for T-008 we just verify the gate passes twice.

    Use an empty-events payload so we don't trigger the agent check.
    """
    payload = json.dumps({"events": []}).encode()
    sig = mock_line.sign(payload)
    headers = {SIGNATURE_HEADER: sig, "Content-Type": "application/json"}

    r1 = client.post("/webhook/line", content=payload, headers=headers)
    r2 = client.post("/webhook/line", content=payload, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200


# ─── Body cap (hermes-agent#23197 takeaway) ─────────────────────────
def test_oversized_body_rejected_with_413(client: TestClient, mock_line: LineMockAdapter) -> None:
    """Body cap (1 MiB) defended before any signature work. 413 on oversize."""
    from app.adapters.line.base import WEBHOOK_BODY_MAX_BYTES

    big = b'{"events":[]}' + b"x" * (WEBHOOK_BODY_MAX_BYTES + 1)
    sig = mock_line.sign(big)
    res = client.post(
        "/webhook/line",
        content=big,
        headers={SIGNATURE_HEADER: sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 413
    assert "too large" in res.json()["detail"]


def test_body_at_exact_cap_passes_through(
    client: TestClient, mock_line: LineMockAdapter
) -> None:
    """Boundary case — a body of exactly 1 MiB is the largest accepted."""
    from app.adapters.line.base import WEBHOOK_BODY_MAX_BYTES

    # 'x' * cap = body that is exactly the cap. (We use a raw byte string
    # because we're only testing the size gate, not the JSON parser.)
    body = b"x" * WEBHOOK_BODY_MAX_BYTES
    sig = mock_line.sign(body)
    res = client.post(
        "/webhook/line",
        content=body,
        headers={SIGNATURE_HEADER: sig, "Content-Type": "application/json"},
    )
    # JSON parse will fail (size gate passes, but body isn't JSON) —
    # the route must return 400, NOT 413, to prove the cap is `<=`.
    assert res.status_code == 400
