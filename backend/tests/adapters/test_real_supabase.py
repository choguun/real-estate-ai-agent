"""T-101 — Real Supabase adapter tests (httpx.MockTransport, no network).

The merged cycle-1 work uses a generic CRUD Protocol
(query/count/insert/update/delete/get_by_id). The real adapter must
implement all 6 methods to talk to Supabase REST (PostgREST) with the
same shape the routers already use.

These tests verify the HTTP call shape (URL, method, headers, body,
query params) using httpx.MockTransport — no network in CI.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.adapters.supabase import SupabaseAdapter
from app.adapters.supabase._factory import get_db
from app.adapters.supabase.errors import PermissionError
from app.adapters.supabase.real import RealSupabaseAdapter
from app.config import Settings

SUPABASE_URL = "https://abc.supabase.co"
ANON_KEY = "eyJ-test-anon-key"
SERVICE_KEY = "eyJ-test-service-key"


def _settings() -> Settings:
    return Settings(
        use_mocks=False,
        use_real_supabase=True,
        supabase_url=SUPABASE_URL,
        supabase_anon_key=ANON_KEY,
        supabase_service_role_key=SERVICE_KEY,
    )


def _new_id() -> str:
    return str(uuid4())


def _capturing_handler(responses: list[tuple[int, Any]]):
    """Build a sync handler that pops canned responses and records requests."""
    captured: list[httpx.Request] = []
    queue = list(responses)

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if not queue:
            return httpx.Response(500, json={"error": "no more canned responses"})
        status, body = queue.pop(0)
        if isinstance(body, dict | list):
            return httpx.Response(status, json=body)
        return httpx.Response(status, text=str(body))

    return handle, captured


# ── Protocol compliance ──────────────────────────────────────


def test_real_satisfies_protocol() -> None:
    """RealSupabaseAdapter must implement the SupabaseAdapter Protocol."""
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
    )
    assert isinstance(adapter, SupabaseAdapter)


# ── factory routing ───────────────────────────────────────


def test_factory_returns_real_when_use_real_supabase() -> None:
    """get_db() with use_real_supabase=True must return RealSupabaseAdapter."""
    from app.adapters.supabase._factory import _mock_singleton, reset_mock_singleton

    reset_mock_singleton()
    adapter = get_db(_settings())
    assert isinstance(adapter, RealSupabaseAdapter)
    assert isinstance(adapter, SupabaseAdapter)
    # And it's NOT the mock singleton
    assert adapter is not _mock_singleton


# ── query ─────────────────────────────────────────────────


def test_query_hits_rest_v1_with_eq_filters_and_order() -> None:
    handle, captured = _capturing_handler([(200, [])])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    adapter.query(
        "properties",
        filters={"user_id": _new_id(), "status": "active"},
        order_by="created_at",
        desc=True,
        limit=10,
    )
    assert len(captured) == 1
    req = captured[0]
    assert req.method == "GET"
    assert str(req.url).startswith(f"{SUPABASE_URL}/rest/v1/properties")
    assert "user_id=eq." in str(req.url)
    assert "status=eq.active" in str(req.url)
    assert "order=created_at.desc" in str(req.url)
    assert "limit=10" in str(req.url)
    assert req.headers.get("apikey") == SERVICE_KEY
    assert req.headers.get("Authorization") == f"Bearer {SERVICE_KEY}"


def test_query_returns_empty_list_on_no_rows() -> None:
    handle, _ = _capturing_handler([(200, [])])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    assert adapter.query("users", filters={"email": "x@x.com"}) == []


def test_query_returns_list_of_dicts() -> None:
    user_id = _new_id()
    rows = [
        {
            "id": user_id,
            "email": "a@b.com",
            "full_name": "A B",
            "password_hash": "$2...",
            "phone": None,
            "avatar_url": None,
            "role": "agent",
            "team_id": None,
            "line_user_id": None,
            "is_active": True,
            "created_at": "2026-07-03T00:00:00+00:00",
            "updated_at": "2026-07-03T00:00:00+00:00",
        }
    ]
    handle, _ = _capturing_handler([(200, rows)])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    found = adapter.query("users", filters={"email": "a@b.com"})
    assert len(found) == 1
    assert found[0]["email"] == "a@b.com"


# ── count ──────────────────────────────────────────────────


def test_count_uses_prefer_count_exact_header() -> None:
    handle, captured = _capturing_handler(
        [
            (
                200,
                [],
            )
        ]
    )  # body irrelevant
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    n = adapter.count("leads", filters={"status": "new"})
    assert n == 0
    req = captured[0]
    assert req.method == "GET"
    assert "status=eq.new" in str(req.url)
    assert req.headers.get("Prefer") == "count=exact"


def test_count_parses_content_range_header() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-range": "0-9/42"})

    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    n = adapter.count("users")
    assert n == 42


# ── get_by_id ─────────────────────────────────────────────


def test_get_by_id_uses_eq_id_filter() -> None:
    user_id = _new_id()
    handle, captured = _capturing_handler([(200, [{"id": user_id, "email": "a@b.com"}])])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    row = adapter.get_by_id("users", user_id)
    assert row is not None
    assert row["id"] == user_id
    assert f"id=eq.{user_id}" in str(captured[0].url)


def test_get_by_id_returns_none_on_empty_list() -> None:
    handle, _ = _capturing_handler([(200, [])])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    assert adapter.get_by_id("users", _new_id()) is None


# ── insert ────────────────────────────────────────────────


def test_insert_posts_with_return_representation_prefer() -> None:
    user_id = _new_id()
    created = {
        "id": user_id,
        "email": "new@example.com",
        "full_name": "New",
        "password_hash": "$2...",
        "phone": None,
        "avatar_url": None,
        "role": "agent",
        "team_id": None,
        "line_user_id": None,
        "is_active": True,
        "created_at": "2026-07-03T00:00:00+00:00",
        "updated_at": "2026-07-03T00:00:00+00:00",
    }
    handle, captured = _capturing_handler([(201, [created])])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    row = adapter.insert(
        "users",
        {
            "email": "new@example.com",
            "full_name": "New",
            "password_hash": "$2...",
        },
    )
    assert row["email"] == "new@example.com"
    insert_req = captured[0]
    assert insert_req.method == "POST"
    assert str(insert_req.url).startswith(f"{SUPABASE_URL}/rest/v1/users")
    body = json.loads(insert_req.content)
    assert body["email"] == "new@example.com"
    prefer = insert_req.headers.get("Prefer", "")
    assert "return=representation" in prefer


# ── update ────────────────────────────────────────────────


def test_update_patches_by_id_with_eq_filter() -> None:
    user_id = _new_id()
    updated = {
        "id": user_id,
        "email": "a@b.com",
        "full_name": "Renamed",
        "created_at": "2026-07-03T00:00:00+00:00",
        "updated_at": "2026-07-03T00:01:00+00:00",
    }
    handle, captured = _capturing_handler([(200, [updated])])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    row = adapter.update("users", user_id, {"full_name": "Renamed"})
    assert row is not None
    assert row["full_name"] == "Renamed"
    update_req = captured[0]
    # PostgREST PATCH with ?id=eq.<uuid> for the row to patch
    assert update_req.method == "PATCH"
    assert f"id=eq.{user_id}" in str(update_req.url)
    body = json.loads(update_req.content)
    assert body == {"full_name": "Renamed"}


def test_update_returns_none_on_empty_list() -> None:
    handle, _ = _capturing_handler([(200, [])])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    assert adapter.update("users", _new_id(), {"full_name": "x"}) is None


# ── delete ────────────────────────────────────────────────


def test_delete_returns_true_on_2xx() -> None:
    handle, captured = _capturing_handler([(204, "")])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    assert adapter.delete("users", _new_id()) is True
    req = captured[0]
    assert req.method == "DELETE"


def test_delete_returns_false_on_404() -> None:
    handle, _ = _capturing_handler([(404, "Not Found")])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    assert adapter.delete("users", _new_id()) is False


# ── error mapping ────────────────────────────────────────


def test_401_raises_permission_error() -> None:
    handle, _ = _capturing_handler([(401, {"message": "JWT expired"})])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    with pytest.raises(PermissionError):
        adapter.query("users", filters={"email": "x@x.com"})


def test_403_raises_permission_error() -> None:
    handle, _ = _capturing_handler([(403, {"message": "forbidden"})])
    adapter = RealSupabaseAdapter(
        base_url=SUPABASE_URL,
        api_key=ANON_KEY,
        service_role_key=SERVICE_KEY,
        transport=httpx.MockTransport(handle),
    )
    with pytest.raises(PermissionError):
        adapter.get_by_id("users", _new_id())
