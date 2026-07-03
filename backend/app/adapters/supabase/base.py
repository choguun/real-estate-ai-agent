"""Database adapter Protocol — every adapter (mock + real) implements this.

Design goals:
- Minimal surface — only the operations the routers actually use.
- Stable ordering — `query()` returns rows in insertion order unless
  the caller passes `order_by`. This makes tests deterministic.
- Filters as a dict — every key is an `eq` filter, all combined with `AND`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SupabaseAdapter(Protocol):
    """The single interface the rest of the app uses."""

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
        """Return rows matching `filters` (all AND)."""
        ...

    def count(
        self,
        table: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> int:
        """Return the number of rows matching `filters`."""
        ...

    def insert(self, table: str, data: Mapping[str, Any]) -> dict[str, Any]:
        """Insert one row. Returns the stored row including auto-defaults."""
        ...

    def update(
        self,
        table: str,
        id: str,
        patch: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Patch by id. Returns updated row or None if no such id."""
        ...

    def delete(self, table: str, id: str) -> bool:
        """Delete by id. Returns True if a row was removed."""
        ...

    def get_by_id(self, table: str, id: str) -> dict[str, Any] | None:
        """Fetch by primary key. Returns None if no such id."""
        ...
