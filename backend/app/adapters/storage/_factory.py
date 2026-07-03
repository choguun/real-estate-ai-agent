"""Storage adapter factory."""

from __future__ import annotations

from app.adapters.storage.base import StorageAdapter
from app.adapters.storage.local_mock import LocalStorageAdapter
from app.adapters.storage.supabase_real import SupabaseStorageAdapter
from app.config import Settings, get_settings


def get_storage(settings: Settings | None = None) -> StorageAdapter:
    """Pick the storage adapter by configuration.

    `public_base_url` is used to build URLs returned to the client.
    """
    settings = settings or get_settings()
    if settings.use_real_supabase:
        return SupabaseStorageAdapter(
            base_url=settings.supabase_url,
            api_key=settings.supabase_service_role_key,
        )
    return LocalStorageAdapter(
        var_dir=settings.var_dir,
        public_base_url=settings.public_base_url,
    )
