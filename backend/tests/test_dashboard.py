"""Tests for the dashboard endpoint — ST-013 (API returns 3 blocks)."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.line.mock import LineMockAdapter
from app.adapters.supabase.mock import MockSupabaseAdapter
from app.deps import get_db_dep, get_line_dep
from app.main import create_app


@pytest.fixture
def db() -> MockSupabaseAdapter:
    return MockSupabaseAdapter()


@pytest.fixture
def line_mock() -> LineMockAdapter:
    return LineMockAdapter(channel_secret="dev-line-channel-secret-change-me")


@pytest.fixture
def client(db, line_mock) -> Iterator[tuple[TestClient, str]]:
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
        yield c, token
    app.dependency_overrides.clear()


def _signed_event(event_id: str, line_user_id: str, text: str = "Hi") -> dict:
    return {
        "type": "message",
        "event_id": event_id,
        "timestamp": 1700000000000,
        "source": {"type": "user", "userId": line_user_id},
        "message": {"id": f"msg-{event_id}", "type": "text", "text": text},
    }


def _ingest(c: TestClient, lm: LineMockAdapter, line_user_id: str, text: str = "Hello") -> None:
    body = json.dumps({"events": [_signed_event(f"e-{line_user_id}", line_user_id, text)]}).encode()
    sig = lm.sign(body)
    res = c.post(
        "/webhook/line",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200, res.text


def _create_property(c: TestClient, **kwargs) -> dict:
    base = {
        "title": "คอนโดทดสอบ",
        "property_type": "condo",
        "price": 5_500_000.0,
        "size_sqm": 35.0,
        "district": "Khlong Toei",
    }
    base.update(kwargs)
    res = c.post("/api/properties", json=base)
    assert res.status_code == 201, res.text
    return res.json()


# ─── ST-013: API returns the three blocks ─────────────────────────────
def test_dashboard_returns_three_blocks(client) -> None:
    c, _ = client
    res = c.get("/api/dashboard")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"new_leads_count", "recent_inbound", "recent_properties"}
    assert body["new_leads_count"] == 0
    assert body["recent_inbound"] == []
    assert body["recent_properties"] == []


def test_dashboard_counts_new_leads(client, line_mock) -> None:
    c, _ = client
    _ingest(c, line_mock, "U-alice")
    _ingest(c, line_mock, "U-bob")
    res = c.get("/api/dashboard")
    assert res.json()["new_leads_count"] == 2


def test_dashboard_recent_inbound_includes_lead_preview(client, line_mock) -> None:
    c, _ = client
    _ingest(c, line_mock, "U-alice", "looking for 1BR")
    res = c.get("/api/dashboard")
    body = res.json()
    assert len(body["recent_inbound"]) == 1
    msg = body["recent_inbound"][0]
    assert msg["direction"] == "inbound"
    assert msg["content"] == "looking for 1BR"
    assert msg["lead"] is not None
    assert msg["lead"]["line_user_id"] == "U-alice"


def test_dashboard_recent_properties_newest_first(client) -> None:
    c, _ = client
    p1 = _create_property(c, title="อันแรก")
    p2 = _create_property(c, title="อันสอง")
    res = c.get("/api/dashboard")
    props = res.json()["recent_properties"]
    assert len(props) == 2
    # Newest first.
    assert props[0]["id"] == p2["id"]
    assert props[1]["id"] == p1["id"]


def test_dashboard_excludes_archived_properties(client) -> None:
    """The dashboard returns only active/draft/sold/rented (not archived)."""
    c, _ = client
    p = _create_property(c, title="archived one")
    c.post(f"/api/properties/{p['id']}/archive")
    res = c.get("/api/dashboard")
    props = res.json()["recent_properties"]
    assert all(x["id"] != p["id"] for x in props)


def test_dashboard_requires_auth(db) -> None:
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        assert c.get("/api/dashboard").status_code == 401


def test_dashboard_cross_user_doesnt_leak(client, line_mock) -> None:
    """Agent B cannot see agent A's leads/messages/properties."""
    c, _ = client
    _ingest(c, line_mock, "U-only-A")
    _create_property(c, title="A's property")
    # Switch to user B
    b = c.post(
        "/api/auth/liff",
        json={"line_user_id": "U-B-the-other", "display_name": "B"},
    ).json()
    c.headers["Authorization"] = f"Bearer {b['token']}"
    res = c.get("/api/dashboard")
    body = res.json()
    assert body["new_leads_count"] == 0
    assert body["recent_inbound"] == []
    assert body["recent_properties"] == []


def test_dashboard_inbound_capped_at_20(client, line_mock) -> None:
    """Recent inbound is capped at 20."""
    c, _ = client
    for i in range(25):
        _ingest(c, line_mock, f"U-{i:03d}", f"msg {i}")
    res = c.get("/api/dashboard")
    assert len(res.json()["recent_inbound"]) == 20
