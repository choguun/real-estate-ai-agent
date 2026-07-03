"""Tests for the mock Supabase adapter — ST-020 + adapter round-trips."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.supabase._factory import get_db
from app.adapters.supabase._schema import DEFAULT_SCHEMA
from app.adapters.supabase.base import SupabaseAdapter
from app.adapters.supabase.mock import MockSupabaseAdapter
from app.adapters.supabase.real import RealSupabaseAdapter
from app.config import Settings
from app.main import create_app


# ─── Fixtures ───────────────────────────────────────────────────────────
@pytest.fixture
def db() -> MockSupabaseAdapter:
    return MockSupabaseAdapter()


@pytest.fixture
def client_with_db(db: MockSupabaseAdapter):
    """TestClient whose `get_db_dep` returns the injected mock."""
    from app.deps import get_db_dep

    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: db
    with TestClient(app) as c:
        yield c, db
    app.dependency_overrides.clear()


# ─── Schema presence (acceptance criterion from T-002) ─────────────────
EXPECTED_TABLES = {
    "users",
    "teams",
    "properties",
    "leads",
    "messages",
    "appointments",
    "generated_listings",
    "contracts",
    "user_settings",
    "audit_logs",
}


def test_all_required_tables_are_in_schema() -> None:
    assert EXPECTED_TABLES.issubset(set(DEFAULT_SCHEMA.table_names))


def test_schema_dict_lookup(db: MockSupabaseAdapter) -> None:
    assert "users" in db.schema
    assert db.schema.get("users").has("email")
    assert db.schema.get("users").columns[0].name == "id"


def test_query_unknown_table_raises(db: MockSupabaseAdapter) -> None:
    with pytest.raises(ValueError, match="Unknown table"):
        db.query("nonexistent_table")


# ─── SQL ↔ mock-schema parity ───────────────────────────────────────────
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def test_sql_matches_mock_schema_tables() -> None:
    """If a table exists in SQL, it must exist in the mock (and vice versa)."""
    sql_path = MIGRATIONS_DIR / "001_init.sql"
    assert sql_path.exists(), "migrations/001_init.sql must exist for the real Supabase DB"
    sql = sql_path.read_text()

    sql_tables = set(re.findall(r"CREATE TABLE\s+(\w+)", sql))
    mock_tables = set(DEFAULT_SCHEMA.table_names)

    assert mock_tables == sql_tables, (
        f"Mock/SQL table mismatch.\n"
        f"  mock ↛ sql: {mock_tables - sql_tables}\n"
        f"  sql ↛ mock: {sql_tables - mock_tables}"
    )


# ─── Round-trip CRUD (ST-020) ───────────────────────────────────────────
def test_users_insert_and_query(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "agent@example.com", "full_name": "Somchai"})
    assert user["id"] is not None
    assert user["email"] == "agent@example.com"
    assert user["role"] == "agent"  # default
    assert user["is_active"] is True  # default

    rows = db.query("users", filters={"email": "agent@example.com"})
    assert len(rows) == 1
    assert rows[0]["id"] == user["id"]


def test_properties_round_trip(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "x@x.com", "full_name": "X"})
    prop = db.insert(
        "properties",
        {
            "user_id": user["id"],
            "title": "คอนโดใจกลางกรุงเทพ",
            "property_type": "condo",
            "price": 5_500_000.0,
            "size_sqm": 35.0,
            "district": "Khlong Toei",
            "province": "Bangkok",
            "bedrooms": 1,
            "bathrooms": 1,
        },
    )
    assert prop["status"] == "draft"  # default

    updated = db.update("properties", prop["id"], {"status": "active", "title": "ใหม่"})
    assert updated is not None
    assert updated["status"] == "active"
    assert updated["title"] == "ใหม่"

    fetched = db.get_by_id("properties", prop["id"])
    assert fetched is not None
    assert fetched["status"] == "active"

    assert db.delete("properties", prop["id"]) is True
    assert db.get_by_id("properties", prop["id"]) is None


def test_leads_filter_by_user_id(db: MockSupabaseAdapter) -> None:
    u1 = db.insert("users", {"email": "a@a.com", "full_name": "A"})
    u2 = db.insert("users", {"email": "b@b.com", "full_name": "B"})

    for n in ("Lead A1", "Lead A2", "Lead A3"):
        db.insert("leads", {"user_id": u1["id"], "name": n})
    db.insert("leads", {"user_id": u2["id"], "name": "Lead B1"})

    a_leads = db.query("leads", filters={"user_id": u1["id"]})
    b_leads = db.query("leads", filters={"user_id": u2["id"]})

    assert len(a_leads) == 3
    assert len(b_leads) == 1
    assert b_leads[0]["name"] == "Lead B1"


# ─── Defaults & auto-id ───────────────────────────────────────────────
def test_insert_auto_id_is_uuid_format(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "auto@x.com", "full_name": "Auto"})
    assert isinstance(user["id"], str)
    assert len(user["id"]) == 36  # canonical UUID form
    assert user["id"].count("-") == 4


def test_default_user_role_is_agent(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "x@x.com", "full_name": "X"})
    assert user["role"] == "agent"


def test_default_property_status_is_draft(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "x@x.com", "full_name": "X"})
    prop = db.insert("properties", {"user_id": user["id"], "property_type": "condo"})
    assert prop["status"] == "draft"


def test_default_lead_source_is_line(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "x@x.com", "full_name": "X"})
    lead = db.insert("leads", {"user_id": user["id"]})
    assert lead["source"] == "line"
    assert lead["status"] == "new"


# ─── Error paths ──────────────────────────────────────────────────────
def test_update_unknown_id_returns_none(db: MockSupabaseAdapter) -> None:
    assert db.update("users", "no-such-id", {"full_name": "X"}) is None


def test_delete_unknown_id_returns_false(db: MockSupabaseAdapter) -> None:
    assert db.delete("users", "no-such-id") is False


def test_insert_required_non_nullable_raises(db: MockSupabaseAdapter) -> None:
    # users.email and users.full_name are NOT NULL with no default.
    with pytest.raises(ValueError, match="NOT NULL"):
        db.insert("users", {"email": "x@x.com"})  # missing full_name


# ─── Counts & ordering ────────────────────────────────────────────────
def test_count_with_and_without_filters(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "x@x.com", "full_name": "X"})
    db.insert("leads", {"user_id": user["id"], "name": "L1"})
    db.insert("leads", {"user_id": user["id"], "name": "L2"})

    assert db.count("leads") == 2
    assert db.count("leads", filters={"name": "L1"}) == 1


def test_query_returns_insertion_order(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "x@x.com", "full_name": "X"})
    l1 = db.insert("leads", {"user_id": user["id"], "name": "First"})
    l2 = db.insert("leads", {"user_id": user["id"], "name": "Second"})
    l3 = db.insert("leads", {"user_id": user["id"], "name": "Third"})

    rows = db.query("leads")
    assert [r["id"] for r in rows] == [l1["id"], l2["id"], l3["id"]]


def test_query_order_by_descending(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "x@x.com", "full_name": "X"})
    db.insert("leads", {"user_id": user["id"], "name": "alpha"})
    db.insert("leads", {"user_id": user["id"], "name": "zeta"})
    db.insert("leads", {"user_id": user["id"], "name": "mid"})

    rows = db.query("leads", order_by="name", desc=True)
    assert [r["name"] for r in rows] == ["zeta", "mid", "alpha"]


def test_query_limit_and_offset(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "x@x.com", "full_name": "X"})
    for i in range(5):
        db.insert("leads", {"user_id": user["id"], "name": f"L{i}"})

    page1 = db.query("leads", limit=2)
    page2 = db.query("leads", limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2


# ─── Snapshot stability (ST-020) ───────────────────────────────────────
def test_snapshot_stability_across_adapters() -> None:
    """Two freshly constructed mocks must have identical schemas."""
    a = MockSupabaseAdapter()
    b = MockSupabaseAdapter()

    def schema_snapshot(adapter: MockSupabaseAdapter) -> list[tuple[str, tuple[str, str, bool]]]:
        return sorted(
            (
                t.name,
                tuple(sorted((c.name, c.type, c.nullable) for c in t.columns)),
            )
            for t in adapter.schema.tables
        )

    assert schema_snapshot(a) == schema_snapshot(b)


# ─── Factory selection ────────────────────────────────────────────────
def test_factory_returns_mock_by_default() -> None:
    settings = Settings(use_real_supabase=False)
    adapter = get_db(settings=settings)
    assert isinstance(adapter, MockSupabaseAdapter)
    # Protocol check (runtime_checkable)
    assert isinstance(adapter, SupabaseAdapter)


def test_factory_returns_real_when_flag_set() -> None:
    settings = Settings(
        use_real_supabase=True,
        use_mocks=False,  # master switch off so the real path is reachable
        supabase_url="http://example.supabase.co",
        supabase_anon_key="test-anon",
        supabase_service_role_key="test-svc",
    )
    adapter = get_db(settings=settings)
    assert isinstance(adapter, RealSupabaseAdapter)
    assert isinstance(adapter, SupabaseAdapter)


def test_factory_master_switch_overrides_real_flag() -> None:
    """use_mocks=True wins even when use_real_supabase=True is set."""
    settings = Settings(
        use_real_supabase=True,
        use_mocks=True,
        supabase_url="http://example.supabase.co",
        supabase_anon_key="test-anon",
        supabase_service_role_key="test-svc",
    )
    adapter = get_db(settings=settings)
    assert isinstance(adapter, MockSupabaseAdapter)


# ─── Update auto-timestamp ────────────────────────────────────────────
def test_update_bumps_updated_at(db: MockSupabaseAdapter) -> None:
    user = db.insert("users", {"email": "x@x.com", "full_name": "X"})
    original_updated_at = user["updated_at"]
    updated = db.update("users", user["id"], {"full_name": "Y"})
    assert updated is not None
    assert updated["updated_at"] >= original_updated_at
    assert updated["full_name"] == "Y"
