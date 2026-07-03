"""Tests for leads + outbound messages — T-010."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.line.mock import LineMockAdapter
from app.adapters.supabase.mock import MockSupabaseAdapter
from app.deps import get_db_dep, get_line_dep
from app.main import create_app


# ─── Fixtures ───────────────────────────────────────────────────────────
@pytest.fixture
def db() -> MockSupabaseAdapter:
    return MockSupabaseAdapter()


@pytest.fixture
def line_mock() -> LineMockAdapter:
    return LineMockAdapter(channel_secret="dev-line-channel-secret-change-me")


@pytest.fixture
def client(db, line_mock) -> Iterator[tuple[TestClient, str, LineMockAdapter]]:
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    app.dependency_overrides[get_line_dep] = lambda: line_mock
    with TestClient(app) as c:
        signup = c.post(
            "/api/auth/signup",
            json={"email": "agent@example.com", "full_name": "Agent", "password": "password123"},
        ).json()
        token = signup["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c, token, line_mock
    app.dependency_overrides.clear()


def _signed_event(event_id: str, line_user_id: str, text: str = "Hi") -> dict:
    return {
        "type": "message",
        "event_id": event_id,
        "timestamp": 1700000000000,
        "source": {"type": "user", "userId": line_user_id},
        "message": {"id": f"msg-{event_id}", "type": "text", "text": text},
    }


def _ingest(
    c: TestClient,
    lm: LineMockAdapter,
    line_user_id: str,
    text: str = "Hello",
    event_id: str | None = None,
) -> dict:
    body = json.dumps(
        {"events": [_signed_event(event_id or f"e-{line_user_id}", line_user_id, text)]}
    ).encode()
    sig = lm.sign(body)
    res = c.post(
        "/webhook/line",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    return res.json()["results"][0]


def _ingest_extra(
    c: TestClient, lm: LineMockAdapter, line_user_id: str, event_id: str, text: str
) -> None:
    body = json.dumps({"events": [_signed_event(event_id, line_user_id, text)]}).encode()
    sig = lm.sign(body)
    c.post(
        "/webhook/line",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )


# ─── List (T-304: team-scoped) ────────────────────────────────
def test_list_leads_returns_callers_team_only(client) -> None:
    """T-304: list returns leads from the caller's team, not all leads.

    With auto-create personal teams, two users live in different
    teams. Cross-team leads are NOT visible.
    """
    c, _, lm = client
    _ingest(c, lm, "U-alice", "hi")
    res = c.get("/api/leads")
    assert res.status_code == 200
    ids = {r["line_user_id"] for r in res.json()}
    assert ids == {"U-alice"}  # only Alice's lead is in her team


def test_cross_team_isolation_on_leads(client, db, line_mock) -> None:
    """T-304 ST-MT-04: Alice's team cannot see Bob's leads (and vice versa)."""
    c_a, _, lm = client  # Alice's client
    _ingest(c_a, lm, "U-alice", "Alice's lead")

    # Bob signs up via liff → gets a separate personal team
    from app.main import create_app

    c_b = TestClient(create_app())
    bob_liff = c_b.post(
        "/api/auth/liff",
        json={"line_user_id": "U-bob", "display_name": "Bob"},
    ).json()
    c_b.headers["Authorization"] = f"Bearer {bob_liff['token']}"
    _ingest(c_b, line_mock, "U-bob", "Bob's lead")

    # Alice sees only Alice's lead
    alice_ids = {r["line_user_id"] for r in c_a.get("/api/leads").json()}
    assert alice_ids == {"U-alice"}
    # Bob sees only Bob's lead
    bob_ids = {r["line_user_id"] for r in c_b.get("/api/leads").json()}
    assert bob_ids == {"U-bob"}


def test_list_filters_by_status(client) -> None:
    c, _, lm = client
    _ingest(c, lm, "U-new", "hi")
    res = c.get("/api/leads?status=new")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["status"] == "new"
    res = c.get("/api/leads?status=closed")
    assert res.json() == []


def test_list_requires_auth(db) -> None:
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        assert c.get("/api/leads").status_code == 401


# ─── Get ────────────────────────────────────────────────────────────────
def test_get_lead_returns_messages_in_created_order(client) -> None:
    c, _, lm = client
    first = _ingest(c, lm, "U-thread", "first")
    lead_id = first["lead_id"]
    _ingest_extra(c, lm, "U-thread", "e-2", "second")

    res = c.get(f"/api/leads/{lead_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["line_user_id"] == "U-thread"
    msgs = body["messages"]
    assert [m["content"] for m in msgs] == ["first", "second"]


def test_get_lead_cross_user_returns_404(client) -> None:
    c, _, lm = client
    r = _ingest(c, lm, "U-cross-get", "hi from A")
    lead_id_a = r["lead_id"]
    # Switch to user B (LIFF) — distinct line_user_id
    b = c.post(
        "/api/auth/liff",
        json={"line_user_id": "U-B-other", "display_name": "B"},
    ).json()
    c.headers["Authorization"] = f"Bearer {b['token']}"
    res = c.get(f"/api/leads/{lead_id_a}")
    assert res.status_code == 404


def test_get_lead_unknown_returns_404(client) -> None:
    c, _, _ = client
    res = c.get("/api/leads/no-such-id")
    assert res.status_code == 404


# ─── Patch ──────────────────────────────────────────────────────────────
def test_patch_lead_updates_fields(client) -> None:
    c, _, lm = client
    r = _ingest(c, lm, "U-edit", "hi")
    lead_id = r["lead_id"]
    res = c.patch(
        f"/api/leads/{lead_id}",
        json={"name": "Khun Alice", "status": "contacted", "notes": "want 1BR"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Khun Alice"
    assert body["status"] == "contacted"
    assert body["notes"] == "want 1BR"


def test_patch_rejects_unknown_status(client) -> None:
    c, _, lm = client
    r = _ingest(c, lm, "U-x", "hi")
    res = c.patch(f"/api/leads/{r['lead_id']}", json={"status": "alien"})
    assert res.status_code == 422


def test_patch_rejects_extra_fields(client) -> None:
    c, _, lm = client
    r = _ingest(c, lm, "U-y", "hi")
    res = c.patch(f"/api/leads/{r['lead_id']}", json={"name": "x", "evil": "boom"})
    assert res.status_code == 422


# ─── Send reply (outbound) ─────────────────────────────────────────────
def test_send_reply_inserts_outbound_and_calls_line_adapter(client, line_mock) -> None:
    c, _, lm = client
    r = _ingest(c, lm, "U-chat", "hello")
    lead_id = r["lead_id"]

    before = len(line_mock.sent_replies)
    res = c.post(
        f"/api/leads/{lead_id}/messages",
        json={"text": "สวัสดีครับ สนใจคอนโดไหม?"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["message"]["direction"] == "outbound"
    assert body["message"]["is_ai_generated"] is False
    assert body["message"]["content"] == "สวัสดีครับ สนใจคอนโดไหม?"
    assert body["line_reply"]["line_user_id"] == "U-chat"

    # The mock recorded the outbound message.
    assert len(line_mock.sent_replies) == before + 1
    assert line_mock.sent_replies[-1].line_user_id == "U-chat"


def test_send_reply_then_get_lead_returns_both_directions(client) -> None:
    c, _, lm = client
    r = _ingest(c, lm, "U-convo", "I'm looking")
    lead_id = r["lead_id"]
    c.post(f"/api/leads/{lead_id}/messages", json={"text": "Got it — budget?"})

    res = c.get(f"/api/leads/{lead_id}")
    msgs = res.json()["messages"]
    assert len(msgs) == 2
    directions = [m["direction"] for m in msgs]
    assert directions == ["inbound", "outbound"]


def test_send_reply_rejects_lead_without_line_user_id(client, db) -> None:
    c, _, _ = client
    user_id = c.get("/api/auth/me").json()["id"]
    user = db.query("users", filters={"id": user_id})[0]
    user_team = user.get("team_id")
    lead = db.insert("leads", {"user_id": user_id, "team_id": user_team, "line_user_id": None})
    res = c.post(f"/api/leads/{lead['id']}/messages", json={"text": "hi"})
    assert res.status_code == 400


def test_send_reply_cross_user_returns_404(client) -> None:
    c, _, lm = client
    r_a = _ingest(c, lm, "U-cross-send", "hi from A")
    lead_id_a = r_a["lead_id"]
    b = c.post(
        "/api/auth/liff",
        json={"line_user_id": "U-B-the-other", "display_name": "B"},
    ).json()
    c.headers["Authorization"] = f"Bearer {b['token']}"
    res = c.post(f"/api/leads/{lead_id_a}/messages", json={"text": "hijack"})
    assert res.status_code == 404


def test_send_reply_requires_auth(db, line_mock) -> None:
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    app.dependency_overrides[get_line_dep] = lambda: line_mock
    with TestClient(app) as c:
        res = c.post("/api/leads/abc/messages", json={"text": "hi"})
        assert res.status_code == 401
