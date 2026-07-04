"""Shared pytest fixtures."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.billing import reset_cache as reset_billing_cache
from app.adapters.email import reset_cache as reset_email_cache
from app.adapters.supabase._factory import reset_mock_singleton
from app.main import create_app


def _reset_all_caches() -> None:
    """Clear adapter singletons so each test starts with a clean slate."""
    reset_mock_singleton()
    with contextlib.suppress(Exception):
        reset_email_cache()
    with contextlib.suppress(Exception):
        reset_billing_cache()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """FastAPI TestClient with the production factory."""
    _reset_all_caches()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    _reset_all_caches()
