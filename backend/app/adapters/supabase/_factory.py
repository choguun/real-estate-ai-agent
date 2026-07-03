"""Database adapter factory.

Single entry point for the rest of the app: call `get_db()` to receive
the adapter selected by env flags.

**Mock lifecycle:** the `MockSupabaseAdapter` is a process-singleton
so that data inserted by one request is visible to the next (production
behaviour in dev mode). Tests use the FastAPI `dependency_overrides`
mechanism to inject a fresh mock per test — the global singleton is not
used in tests.
"""

from __future__ import annotations

import threading

from app.adapters.supabase.base import SupabaseAdapter
from app.adapters.supabase.mock import MockSupabaseAdapter
from app.adapters.supabase.real import RealSupabaseAdapter
from app.config import Settings, get_settings

_mock_lock = threading.Lock()
_mock_singleton: MockSupabaseAdapter | None = None


def _get_or_init_mock() -> MockSupabaseAdapter:
    """Thread-safe singleton init for the in-memory mock."""
    global _mock_singleton
    if _mock_singleton is None:
        with _mock_lock:
            if _mock_singleton is None:
                _mock_singleton = MockSupabaseAdapter()
    return _mock_singleton


def get_db(settings: Settings | None = None) -> SupabaseAdapter:
    """Return a DB adapter based on configuration.

    `use_mocks=True` is the master switch and overrides every
    `use_real_*` flag — useful in CI / docs / laptop dev where you
    never want a real adapter even if the URL is filled in.
    """
    settings = settings or get_settings()
    if settings.use_mocks:
        return _get_or_init_mock()
    if settings.use_real_supabase:
        return RealSupabaseAdapter(
            base_url=settings.supabase_url,
            api_key=settings.supabase_anon_key,
            service_role_key=settings.supabase_service_role_key,
        )
    return _get_or_init_mock()


def reset_mock_singleton() -> None:
    """Drop the mock singleton. Tests/dev-tools call this between scenarios."""
    global _mock_singleton
    with _mock_lock:
        _mock_singleton = None
