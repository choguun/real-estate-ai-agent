"""FastAPI dependency injection.

Centralised so routers do `db: DBDep` and never instantiate adapters.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.adapters.supabase._factory import get_db
from app.adapters.supabase.base import SupabaseAdapter


def get_db_dep() -> SupabaseAdapter:
    """Per-request dependency. Singleton-per-request."""
    return get_db()


DBDep = Annotated[SupabaseAdapter, Depends(get_db_dep)]
