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
    # Cycle 6 T-602: rate limiter is per-process state; reset between
    # tests so one test's signup doesn't hit another test's quota.
    with contextlib.suppress(Exception):
        from app.rate_limit_factory import reset_cache as reset_rl_cache

        reset_rl_cache()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """FastAPI TestClient with the production factory."""
    _reset_all_caches()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    _reset_all_caches()


@pytest.fixture(autouse=True)
def _reset_rate_limiter_between_tests() -> Iterator[None]:
    """Cycle 6 T-602: clear the rate-limiter singleton before each test.

    Most tests bypass the `client` fixture and build their own
    TestClient, so the per-client reset doesn't reach them. An
    autouse fixture runs once per test regardless of which fixtures
    the test requests.
    """
    with contextlib.suppress(Exception):
        from app.rate_limit_factory import reset_cache as reset_rl_cache

        reset_rl_cache()
    yield
    with contextlib.suppress(Exception):
        from app.rate_limit_factory import reset_cache as reset_rl_cache

        reset_rl_cache()
