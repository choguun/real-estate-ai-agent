"""Email adapter factory."""

from __future__ import annotations

from functools import lru_cache

from app.adapters.email.base import EmailAdapter
from app.adapters.email.mock import MockEmailAdapter
from app.adapters.email.real import ResendEmailAdapter
from app.config import Settings, get_settings


@lru_cache(maxsize=1)
def _build(use_mocks: bool) -> EmailAdapter:
    return MockEmailAdapter() if use_mocks else ResendEmailAdapter(api_key="real-key")


def build_email_adapter(settings: Settings | None = None) -> EmailAdapter:
    s = settings or get_settings()
    return _build(s.use_mocks)


def reset_cache() -> None:
    _build.cache_clear()
