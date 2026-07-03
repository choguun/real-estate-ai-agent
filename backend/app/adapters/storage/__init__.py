"""Storage adapters — local disk (mock) + Supabase Storage (real stub)."""

from app.adapters.storage.base import StorageAdapter, StoredObject
from app.adapters.storage.local_mock import LocalStorageAdapter
from app.adapters.storage.supabase_real import SupabaseStorageAdapter

__all__ = [
    "StorageAdapter",
    "StoredObject",
    "LocalStorageAdapter",
    "SupabaseStorageAdapter",
]
