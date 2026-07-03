"""Real Supabase adapter — stub for MVP.

When `USE_REAL_SUPABASE=true`, this client replaces the mock. For
Month-1 MVP, the real client is wired through the same Protocol so
the rest of the app is unaffected. Network calls land against the
Supabase REST API: `POST/GET/PATCH/DELETE /rest/v1/<table>`.

This module ships as a stub:
- Constructor accepts a `base_url` + `api_key` and an optional `httpx.Client`.
- All operations raise `NotImplementedError` until they are wired in
  later tasks (T-003 auth → T-007 listings).
- The Protocol is implemented so `isinstance(client, SupabaseAdapter)` returns True.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.adapters.supabase.base import SupabaseAdapter


class RealSupabaseAdapter:
    """Supabase REST client implementing `SupabaseAdapter`."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        service_role_key: str | None = None,
        http_client: Any | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._service_role_key = service_role_key or api_key
        self._http = http_client  # httpx.Client created lazily to keep imports lazy

    # ─── Internal helpers ─────────────────────────────────────────────
    def _url(self, table: str) -> str:
        return f"{self._base_url}/rest/v1/{table}"

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    # ─── SupabaseAdapter (stubs) ──────────────────────────────────────
    def query(  # noqa: D401
        self,
        table: str,
        *,
        filters: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        desc: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "RealSupabaseAdapter.query will be wired in a later task (T-003+). "
            "Set USE_REAL_SUPABASE=false to use the mock."
        )

    def count(
        self,
        table: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> int:
        raise NotImplementedError("RealSupabaseAdapter.count is not wired yet.")

    def insert(self, table: str, data: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("RealSupabaseAdapter.insert is not wired yet.")

    def update(
        self,
        table: str,
        id: str,
        patch: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        raise NotImplementedError("RealSupabaseAdapter.update is not wired yet.")

    def delete(self, table: str, id: str) -> bool:
        raise NotImplementedError("RealSupabaseAdapter.delete is not wired yet.")

    def get_by_id(self, table: str, id: str) -> dict[str, Any] | None:
        raise NotImplementedError("RealSupabaseAdapter.get_by_id is not wired yet.")

    # ─── Type-checker hint ────────────────────────────────────────────
    def __class_getitem__(cls, _item: Any) -> type:  # pragma: no cover
        return SupabaseAdapter
