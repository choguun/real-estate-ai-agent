"""In-memory implementation of `SupabaseAdapter`.

Stores rows in `dict[table_name -> list[dict]]`. Order is preserved —
the list is append-only on insert, so `query()` returns rows in
insertion order when no `order_by` is given. That makes test fixtures
deterministic.

UUIDs are minted via `uuid.uuid4()`. Timestamps via UTC ISO 8601.
No persistence — the mock resets when the process exits.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from app.adapters.supabase._schema import DEFAULT_SCHEMA, Schema, Table


class MockSupabaseAdapter:
    """In-memory Supabase adapter for local dev + tests."""

    def __init__(self, schema: Schema | None = None) -> None:
        self._schema = schema or DEFAULT_SCHEMA
        # list per table preserves insertion order
        self._rows: dict[str, list[dict[str, Any]]] = {
            name: [] for name in self._schema.table_names
        }
        # secondary index for fast id lookups
        self._by_id: dict[str, dict[str, dict[str, Any]]] = {
            name: {} for name in self._schema.table_names
        }

    # ─── Introspection (test/diagnostic only) ─────────────────────────
    @property
    def schema(self) -> Schema:
        return self._schema

    def _assert_table(self, name: str) -> Table:
        try:
            return self._schema.get(name)
        except KeyError as e:
            raise ValueError(str(e)) from e

    # ─── SupabaseAdapter ──────────────────────────────────────────────
    def query(
        self,
        table: str,
        *,
        filters: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        desc: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self._assert_table(table)
        rows = [copy.deepcopy(r) for r in self._rows[table]]

        if filters:
            for key, expected in filters.items():
                rows = [r for r in rows if r.get(key) == expected]

        if order_by is not None:
            rows.sort(key=lambda r: (r.get(order_by) is None, r.get(order_by) or ""), reverse=desc)
        # else: insertion order — list is append-only.

        if offset:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]

        return rows

    def count(
        self,
        table: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> int:
        return len(self.query(table, filters=filters))

    def insert(self, table: str, data: Mapping[str, Any]) -> dict[str, Any]:
        table_def = self._assert_table(table)
        row: dict[str, Any] = dict(data)

        # Apply defaults for missing columns.
        for col in table_def.columns:
            if col.name in row:
                continue
            default = col.default
            if default is None:
                if not col.nullable:
                    missing_default = (
                        f"Column {table}.{col.name} is NOT NULL but missing "
                        "a default and no value was provided."
                    )
                    raise ValueError(missing_default)
                continue
            row[col.name] = default() if callable(default) else default

        if "id" not in row or row["id"] is None:
            row["id"] = _default_id(table_def)

        # Enforce UNIQUE constraints declared on the table.
        for constraint in table_def.unique_constraints:
            existing = self.query(table, filters={c: row.get(c) for c in constraint})
            if existing:
                raise ValueError(
                    f"UNIQUE constraint violation on {table}{constraint} "
                    f"(row={row.get(constraint[0])!r})"
                )

        self._rows[table].append(row)
        # Maintain the by-id index. If id is non-unique, last-wins.
        self._by_id[table][row["id"]] = row
        return copy.deepcopy(row)

    def update(
        self,
        table: str,
        id: str,
        patch: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        self._assert_table(table)
        row = self._by_id[table].get(id)
        if row is None:
            return None
        row.update(patch)
        # Re-stamp updated_at when the schema has one. (Same helper as
        # `_schema.py`; centralized there.)
        if self._schema.get(table).has("updated_at"):
            from app.adapters.supabase._schema import now_iso

            row["updated_at"] = now_iso()
        return copy.deepcopy(row)

    def delete(self, table: str, id: str) -> bool:
        self._assert_table(table)
        if id not in self._by_id[table]:
            return False
        del self._by_id[table][id]
        self._rows[table] = [r for r in self._rows[table] if r["id"] != id]
        return True

    def get_by_id(self, table: str, id: str) -> dict[str, Any] | None:
        self._assert_table(table)
        row = self._by_id[table].get(id)
        return copy.deepcopy(row) if row is not None else None

    # ─── Helpers (used by tests + dev tools) ─────────────────────────
    def reset(self) -> None:
        for name in self._schema.table_names:
            self._rows[name] = []
            self._by_id[name] = {}


# ─── Module-private helpers (called from MockSupabaseAdapter) ─────────
def _default_id(table_def: Table) -> str:
    """Mint a UUID4 in the canonical format."""
    import uuid as _uuid

    return str(_uuid.uuid4())


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
