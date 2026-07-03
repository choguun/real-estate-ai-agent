"""Tests for generated_listings persistence — ST-008."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.supabase.mock import MockSupabaseAdapter
from app.deps import get_db_dep
from app.main import create_app


@pytest.fixture
def db() -> MockSupabaseAdapter:
    return MockSupabaseAdapter()


@pytest.fixture
def auth_client(db: MockSupabaseAdapter) -> Iterator[tuple[TestClient, str, str]]:
    """TestClient, token, and the user's property id (created on the fly)."""
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        signup = c.post(
            "/api/auth/signup",
            json={
                "email": "lister@example.com",
                "full_name": "Lister",
                "password": "password123",
            },
        )
        token = signup.json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        prop = c.post(
            "/api/properties",
            json={
                "title": "คอนโดทดสอบ",
                "property_type": "condo",
                "price": 5_500_000.0,
                "size_sqm": 35.0,
            },
        )
        property_id = prop.json()["id"]
        yield c, token, property_id


def _listing_payload(property_id: str, **overrides) -> dict:
    base = {
        "property_id": property_id,
        "platform": "facebook",
        "title": "🔥 ขายคอนโด",
        "description": "🚨 ขายด่วน! คอนโด\n💰 ฿5,500,000",
        "hashtags": ["#คอนโด", "#Bangkok"],
        "seo_keywords": [],
        "ai_model": "claude-3-5-sonnet-mock",
        "prompt_used": "facebook:condo",
    }
    base.update(overrides)
    return base


# ─── ST-008: round-trip ─────────────────────────────────────────────────
def test_create_listing_returns_row(auth_client) -> None:
    c, _, pid = auth_client
    res = c.post("/api/listings", json=_listing_payload(pid))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["id"]
    assert body["property_id"] == pid
    assert body["platform"] == "facebook"


def test_get_listings_returns_variants_for_property(auth_client) -> None:
    c, _, pid = auth_client
    c.post("/api/listings", json=_listing_payload(pid, platform="facebook", title="FB"))
    c.post("/api/listings", json=_listing_payload(pid, platform="ddproperty", title="DD"))
    c.post("/api/listings", json=_listing_payload(pid, platform="livinginsider", title="LI"))
    c.post("/api/listings", json=_listing_payload(pid, platform="general", title="Gen"))

    res = c.get(f"/api/listings?property_id={pid}")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 4
    platforms = {r["platform"] for r in rows}
    assert platforms == {"facebook", "ddproperty", "livinginsider", "general"}


def test_patch_listing_updates_fields(auth_client) -> None:
    c, _, pid = auth_client
    listing = c.post("/api/listings", json=_listing_payload(pid)).json()
    res = c.patch(
        f"/api/listings/{listing['id']}",
        json={"title": "🔥 Updated", "description": "new desc"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "🔥 Updated"
    assert body["description"] == "new desc"


def test_patch_listing_with_no_fields_is_noop(auth_client) -> None:
    c, _, pid = auth_client
    listing = c.post("/api/listings", json=_listing_payload(pid)).json()
    res = c.patch(f"/api/listings/{listing['id']}", json={})
    assert res.status_code == 200
    assert res.json()["title"] == listing["title"]


def test_delete_listing_removes_row(auth_client) -> None:
    c, _, pid = auth_client
    listing = c.post("/api/listings", json=_listing_payload(pid)).json()
    res = c.delete(f"/api/listings/{listing['id']}")
    assert res.status_code == 204
    res2 = c.get(f"/api/listings?property_id={pid}")
    assert res2.json() == []


# ─── Auth + scoping ────────────────────────────────────────────────────
def test_create_requires_auth(db: MockSupabaseAdapter) -> None:
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        res = c.post("/api/listings", json=_listing_payload("does-not-matter"))
        assert res.status_code == 401


def test_create_rejects_unknown_property(auth_client) -> None:
    c, _, _ = auth_client
    res = c.post("/api/listings", json=_listing_payload("no-such-property"))
    assert res.status_code == 404


def test_list_requires_property_id(auth_client) -> None:
    c, _, _ = auth_client
    res = c.get("/api/listings")
    assert res.status_code == 422  # missing required query param


def test_cross_user_listing_returns_404(db: MockSupabaseAdapter) -> None:
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        # User A creates a property + listing
        a = c.post(
            "/api/auth/signup",
            json={"email": "a@a.com", "full_name": "A", "password": "password123"},
        ).json()
        c.headers["Authorization"] = f"Bearer {a['token']}"
        prop = c.post("/api/properties", json={"title": "x"}).json()
        listing = c.post("/api/listings", json=_listing_payload(prop["id"])).json()

        # Switch to user B
        b = c.post(
            "/api/auth/liff",
            json={"line_user_id": "U-B", "display_name": "B"},
        ).json()
        c.headers["Authorization"] = f"Bearer {b['token']}"

        # B can't see, edit, or delete A's listing.
        assert c.get(f"/api/listings?property_id={prop['id']}").status_code == 404
        assert (
            c.patch(
                f"/api/listings/{listing['id']}",
                json={"title": "hacked"},
            ).status_code
            == 404
        )
        assert c.delete(f"/api/listings/{listing['id']}").status_code == 404


# ─── Validation ────────────────────────────────────────────────────────
def test_create_rejects_unknown_platform(auth_client) -> None:
    c, _, pid = auth_client
    res = c.post("/api/listings", json=_listing_payload(pid, platform="instagram"))
    assert res.status_code == 422


def test_create_rejects_empty_title(auth_client) -> None:
    c, _, pid = auth_client
    res = c.post("/api/listings", json=_listing_payload(pid, title=""))
    assert res.status_code == 422


def test_create_rejects_extra_fields(auth_client) -> None:
    c, _, pid = auth_client
    res = c.post(
        "/api/listings",
        json=_listing_payload(pid, evil_field="boom"),
    )
    assert res.status_code == 422
