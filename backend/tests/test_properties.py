"""Properties tests — ST-005 + cross-user scoping + soft delete."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.adapters.supabase.mock import MockSupabaseAdapter
from app.deps import get_db_dep
from app.main import create_app


# ─── Fixtures ───────────────────────────────────────────────────────────
@pytest.fixture
def db() -> MockSupabaseAdapter:
    return MockSupabaseAdapter()


@pytest.fixture
def auth_client(db: MockSupabaseAdapter) -> Iterator[tuple[TestClient, MockSupabaseAdapter, str]]:
    """TestClient with mock DB + a signed-in user's token attached."""
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        signup = c.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "full_name": "Test", "password": "password123"},
        )
        assert signup.status_code == 201, signup.text
        token = signup.json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c, db, token
    app.dependency_overrides.clear()


def _create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    base = {
        "title": "คอนโดทดสอบ",
        "property_type": "condo",
        "price": 5_500_000.0,
        "size_sqm": 35.0,
        "bedrooms": 1,
        "bathrooms": 1,
        "district": "Khlong Toei",
        "province": "Bangkok",
    }
    base.update(overrides)
    res = client.post("/api/properties", json=base)
    assert res.status_code == 201, res.text
    return res.json()


# ─── Auth gate ──────────────────────────────────────────────────────────
def test_list_requires_auth(db: MockSupabaseAdapter) -> None:
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        res = c.get("/api/properties")
        assert res.status_code == 401
    app.dependency_overrides.clear()


def test_create_requires_auth(db: MockSupabaseAdapter) -> None:
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        res = c.post("/api/properties", json={"title": "x"})
        assert res.status_code == 401
    app.dependency_overrides.clear()


# ─── ST-005: CRUD round-trip ────────────────────────────────────────────
def test_create_property_returns_row_with_defaults(auth_client) -> None:
    c, db, _ = auth_client
    row = _create(c)

    assert row["id"]
    assert row["title"] == "คอนโดทดสอบ"
    assert row["property_type"] == "condo"
    assert row["price"] == 5_500_000.0
    assert row["status"] == "draft"  # default from schema
    assert row["foreign_quota"] is False  # default


def test_list_returns_only_callers_properties(auth_client) -> None:
    c, db, _ = auth_client
    _create(c)
    _create(c, title="อีกห้อง")
    rows = c.get("/api/properties").json()
    assert len(rows) == 2
    assert all(r["user_id"] for r in rows)


def test_get_property_by_id(auth_client) -> None:
    c, _, _ = auth_client
    row = _create(c)
    res = c.get(f"/api/properties/{row['id']}")
    assert res.status_code == 200
    assert res.json()["id"] == row["id"]


def test_patch_property_updates_fields(auth_client) -> None:
    c, _, _ = auth_client
    row = _create(c)
    res = c.patch(
        f"/api/properties/{row['id']}",
        json={"title": "ใหม่", "status": "active", "price": 6_000_000.0},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "ใหม่"
    assert body["status"] == "active"
    assert body["price"] == 6_000_000.0


def test_patch_property_rejects_negative_price(auth_client) -> None:
    c, _, _ = auth_client
    row = _create(c)
    res = c.patch(f"/api/properties/{row['id']}", json={"price": -1})
    assert res.status_code == 422


def test_archive_property_hides_it_from_default_list(auth_client) -> None:
    c, _, _ = auth_client
    _create(c, title="Visible")
    p2 = _create(c, title="Will be archived")

    res = c.post(f"/api/properties/{p2['id']}/archive")
    assert res.status_code == 200
    assert res.json()["status"] == "archived"

    listed = c.get("/api/properties").json()
    titles = [r["title"] for r in listed]
    assert "Visible" in titles
    assert "Will be archived" not in titles


def test_archive_is_idempotent(auth_client) -> None:
    c, _, _ = auth_client
    row = _create(c)
    c.post(f"/api/properties/{row['id']}/archive")
    second = c.post(f"/api/properties/{row['id']}/archive")
    assert second.status_code == 200
    assert second.json()["status"] == "archived"


def test_include_archived_flag_brings_them_back(auth_client) -> None:
    c, _, _ = auth_client
    row = _create(c, title="Hidden")
    c.post(f"/api/properties/{row['id']}/archive")

    listed = c.get("/api/properties?include_archived=true").json()
    titles = [r["title"] for r in listed]
    assert "Hidden" in titles


def test_status_filter(auth_client) -> None:
    c, _, _ = auth_client
    p1 = _create(c, title="Active one")
    _create(c, title="Draft one")
    c.patch(f"/api/properties/{p1['id']}", json={"status": "active"})

    active = c.get("/api/properties?status=active").json()
    assert [r["id"] for r in active] == [p1["id"]]


# ─── Cross-user scoping (security) ─────────────────────────────────────
def test_cross_user_get_returns_404(db: MockSupabaseAdapter) -> None:
    """Property belongs to user A; user B cannot see it."""
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        # User A
        a = c.post(
            "/api/auth/signup",
            json={"email": "a@a.com", "full_name": "A", "password": "password123"},
        ).json()
        c.headers["Authorization"] = f"Bearer {a['token']}"
        p = _create(c, title="A's property")

        # Switch to user B
        b = c.post(
            "/api/auth/liff",
            json={"line_user_id": "U-B", "display_name": "B"},
        ).json()
        c.headers["Authorization"] = f"Bearer {b['token']}"

        # B cannot read, patch, or archive A's property.
        assert c.get(f"/api/properties/{p['id']}").status_code == 404
        assert c.patch(f"/api/properties/{p['id']}", json={"title": "X"}).status_code == 404
        assert c.post(f"/api/properties/{p['id']}/archive").status_code == 404

        # But B's list does NOT include A's property either.
        rows = c.get("/api/properties").json()
        assert all(r["id"] != p["id"] for r in rows)
    app.dependency_overrides.clear()


def test_unknown_property_id_returns_404(auth_client) -> None:
    c, _, _ = auth_client
    res = c.get("/api/properties/no-such-id")
    assert res.status_code == 404


# ─── Validation ─────────────────────────────────────────────────────────
def test_create_rejects_unknown_property_type(auth_client) -> None:
    c, _, _ = auth_client
    res = c.post("/api/properties", json={"title": "x", "property_type": "spaceship"})
    assert res.status_code == 422


def test_create_accepts_minimal_payload(auth_client) -> None:
    c, _, _ = auth_client
    res = c.post("/api/properties", json={})
    assert res.status_code == 201
    body = res.json()
    assert body["title"] is None
    assert body["status"] == "draft"


def test_create_rejects_extra_fields(auth_client) -> None:
    c, _, _ = auth_client
    res = c.post("/api/properties", json={"title": "x", "evil_field": "rm -rf"})
    assert res.status_code == 422
