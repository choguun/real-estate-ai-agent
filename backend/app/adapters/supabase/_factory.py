"""Database adapter factory.

Single entry point for the rest of the app: call `get_db()` to receive
the adapter selected by env flags. Routers depend on this through
`app.deps.get_db_dep`.
"""

from __future__ import annotations

from app.adapters.supabase.base import SupabaseAdapter
from app.adapters.supabase.mock import MockSupabaseAdapter
from app.adapters.supabase.real import RealSupabaseAdapter
from app.config import Settings, get_settings


def get_db(settings: Settings | None = None) -> SupabaseAdapter:
    """Return a fresh DB adapter based on configuration.

    Pass an explicit `settings` for tests; otherwise reads from env/cache.
    """
    settings = settings or get_settings()
    if settings.use_real_supabase:
        return RealSupabaseAdapter(
            base_url=settings.supabase_url,
            api_key=settings.supabase_anon_key,
            service_role_key=settings.supabase_service_role_key,
        )
    return MockSupabaseAdapter()
