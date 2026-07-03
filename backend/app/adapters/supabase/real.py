"""Real Supabase adapter — PostgREST client.

Implements the generic ``SupabaseAdapter`` Protocol (query/count/insert/
update/delete/get_by_id) using httpx against
``{SUPABASE_URL}/rest/v1/{table}`` — Supabase's PostgREST endpoint.

**Auth:** the service-role key is used for every call (bypasses RLS, can
insert on behalf of any user). For the MVP we don't enable RLS; the
service key is fine. When RLS lands, we'll swap to a per-user JWT.

**Scoping:** PostgREST filters are passed as ``?col=eq.value`` query
params. The router is responsible for adding ``user_id=eq.<uuid>`` to
every query; this adapter does not enforce tenant isolation.

**Tests:** ``tests/adapters/test_real_supabase.py`` exercises every
method via httpx.MockTransport — no network in CI.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import urlencode

import httpx

from app.adapters.supabase.base import SupabaseAdapter
from app.adapters.supabase.errors import PermissionError

_SAFE_COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_ORDER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _safe_json(response: httpx.Response, *, table: str, op: str) -> list[dict[str, Any]]:
    """Decode response body as JSON list-of-dicts; raise typed error on failure.

    Bypasses raw ``response.json()`` so a malformed body (e.g. an HTML
    error page from a proxy in front of PostgREST) raises a typed
    error instead of escaping as a generic ``json.JSONDecodeError``.
    """
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Supabase {op} on {table!r} returned non-JSON "
            f"(status={response.status_code}): {response.text[:200]!r}"
        ) from exc
    if isinstance(payload, dict):
        # PostgREST with Prefer: return=single returns a dict, not a list.
        return [payload]
    if not isinstance(payload, list):
        raise RuntimeError(
            f"Supabase {op} on {table!r} returned non-list payload "
            f"(status={response.status_code})"
        )
    return payload


class RealSupabaseAdapter(SupabaseAdapter):
    """Supabase REST client implementing ``SupabaseAdapter``."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        service_role_key: str | None = None,
        http_client: httpx.Client | None = None,
        transport: httpx.MockTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        # Lazy-allow the transport kwarg so tests can inject MockTransport
        # without spinning up a real httpx Client.
        if transport is not None:
            self._client = httpx.Client(transport=transport, timeout=timeout)
        elif http_client is not None:
            self._client = http_client
        else:
            self._client = httpx.Client(timeout=timeout)
        self._owns_client = transport is None and http_client is None
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._service_role_key = service_role_key or api_key

    # ─── Internal helpers ────────────────────────────────────────────
    def _url(self, table: str) -> str:
        if not _SAFE_COLUMN.match(table):
            raise ValueError(f"unsafe table name: {table!r}")
        return f"{self._base_url}/rest/v1/{table}"

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        h = {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def _check_status(self, response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise PermissionError(f"Supabase auth failed ({response.status_code}): {response.text}")

    @staticmethod
    def _encode_filters(filters: Mapping[str, Any] | None) -> str:
        if not filters:
            return ""
        params: list[tuple[str, str]] = []
        for col, val in filters.items():
            if not _SAFE_COLUMN.match(col):
                raise ValueError(f"unsafe filter column: {col!r}")
            params.append((f"{col}", f"eq.{val}"))
        return urlencode(params)

    # ─── SupabaseAdapter ─────────────────────────────────────────────
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
        params: list[tuple[str, str]] = []
        for part in self._encode_filters(filters).split("&"):
            if part:
                key, _, val = part.partition("=")
                params.append((key, val))
        if order_by:
            if not _SAFE_ORDER.match(order_by):
                raise ValueError(f"unsafe order_by: {order_by!r}")
            params.append(("order", f"{order_by}.{'desc' if desc else 'asc'}"))
        if limit is not None:
            params.append(("limit", str(limit)))
        if offset:
            params.append(("offset", str(offset)))

        response = self._client.get(
            self._url(table),
            params=httpx.QueryParams(cast(list[tuple[str, Any]], params)),
            headers=self._headers(),
        )
        self._check_status(response)
        if response.status_code == 204 or not response.content:
            return []
        return _safe_json(response, table=table, op="query")

    def count(
        self,
        table: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> int:
        params: list[tuple[str, str]] = []
        for part in self._encode_filters(filters).split("&"):
            if part:
                key, _, val = part.partition("=")
                params.append((key, val))
        # PostgREST returns the count in Content-Range when Prefer: count=exact
        response = self._client.get(
            self._url(table),
            params=cast(list[tuple[str, Any]], params),
            headers=self._headers(prefer="count=exact"),
        )
        self._check_status(response)
        # Content-Range: 0-9/42  →  42 rows
        content_range = response.headers.get("content-range", "")
        if "/" in content_range:
            tail = content_range.rsplit("/", 1)[-1]
            try:
                return int(tail)
            except ValueError:
                return 0
        # If the server didn't honour Prefer (e.g. empty table → no header),
        # fall back to counting the returned body.
        if response.status_code == 204 or not response.content:
            return 0
        body = _safe_json(response, table=table, op="count")
        return len(body)

    def insert(self, table: str, data: Mapping[str, Any]) -> dict[str, Any]:
        response = self._client.post(
            self._url(table),
            json=dict(data),
            headers=self._headers(prefer="return=representation"),
        )
        self._check_status(response)
        # PostgREST returns the inserted row(s) with Prefer: return=representation
        rows = _safe_json(response, table=table, op="insert")
        if not rows:
            raise RuntimeError(
                f"Supabase insert returned no row for {table!r} " f"(status={response.status_code})"
            )
        return rows[0]

    def update(
        self,
        table: str,
        id: str,
        patch: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        response = self._client.patch(
            self._url(table),
            params=[("id", f"eq.{id}")],
            json=dict(patch),
            headers=self._headers(prefer="return=representation"),
        )
        self._check_status(response)
        if response.status_code == 204 or not response.content:
            return None
        rows = _safe_json(response, table=table, op="update")
        return rows[0] if rows else None

    def delete(self, table: str, id: str) -> bool:
        response = self._client.delete(
            self._url(table),
            params=[("id", f"eq.{id}")],
            headers=self._headers(),
        )
        self._check_status(response)
        # PostgREST returns 204 on successful delete, 404 if no matching row
        return response.status_code == 204

    def get_by_id(self, table: str, id: str) -> dict[str, Any] | None:
        rows = self.query(table, filters={"id": id})
        return rows[0] if rows else None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
