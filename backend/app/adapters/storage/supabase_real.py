"""Supabase Storage adapter — stub for MVP.

Wires to `https://{project}.supabase.co/storage/v1/object/{bucket}/{key}`.
For Month-1 MVP, every method raises `NotImplementedError`. The mock
runs the dev experience so the rest of the app is unaffected.
"""

from __future__ import annotations

from app.adapters.storage.base import StoredObject


class SupabaseStorageAdapter:
    """Real Supabase Storage client implementing `StorageAdapter`."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        bucket: str = "property-images",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._bucket = bucket

    def upload(
        self,
        content: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> StoredObject:
        raise NotImplementedError(
            "SupabaseStorageAdapter.upload is not wired yet. "
            "Set USE_REAL_SUPABASE=false (or use_mocks=true) for local dev."
        )

    def get(self, key: str) -> tuple[bytes, str] | None:
        raise NotImplementedError("SupabaseStorageAdapter.get is not wired yet.")

    def delete(self, key: str) -> bool:
        raise NotImplementedError("SupabaseStorageAdapter.delete is not wired yet.")
