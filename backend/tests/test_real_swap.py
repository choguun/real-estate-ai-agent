"""Verify the real adapter classes implement their Protocol.

These tests are SKIPPED by default — they instantiate the `_real.py`
classes which raise NotImplementedError for every method that would
actually hit a network.

Run with:  RUN_REAL_ADAPTER_TESTS=1 pytest -m real_adapter

The goal is to prove the *wire is complete*: switching mocks → real
adapters via env flags requires zero router changes. We do this without
exercising any real HTTP — just instantiating each class, verifying the
class's module resolves cleanly, and that the result satisfies the
Protocol via `isinstance`.
"""

from __future__ import annotations

import pytest

from app.adapters.ai import (
    AiAdapter,
    AnthropicRealAdapter,
    GeminiRealAdapter,
)
from app.adapters.line import (
    LineAdapter,
    LineRealAdapter,
)
from app.adapters.storage import (
    StorageAdapter,
    SupabaseStorageAdapter,
)
from app.adapters.supabase import (
    RealSupabaseAdapter,
    SupabaseAdapter,
)

pytestmark = pytest.mark.real_adapter


def _skip_unless_enabled():
    import os

    if os.environ.get("RUN_REAL_ADAPTER_TESTS") != "1":
        pytest.skip("Set RUN_REAL_ADAPTER_TESTS=1 to run real-adapter swap tests")


def test_real_supabase_adapter_satisfies_protocol() -> None:
    _skip_unless_enabled()
    client = RealSupabaseAdapter(
        base_url="https://example.supabase.co",
        api_key="test-anon-key",
        service_role_key="test-service-role",
    )
    assert isinstance(client, SupabaseAdapter)


def test_real_anthropic_adapter_satisfies_protocol() -> None:
    _skip_unless_enabled()
    client = AnthropicRealAdapter(api_key="sk-test", model="claude-3-5-sonnet-latest")
    assert isinstance(client, AiAdapter)


def test_real_gemini_adapter_satisfies_protocol() -> None:
    _skip_unless_enabled()
    client = GeminiRealAdapter(api_key="test-gemini-key", model="gemini-2.0-flash-exp")
    assert isinstance(client, AiAdapter)


def test_real_line_adapter_satisfies_protocol() -> None:
    _skip_unless_enabled()
    client = LineRealAdapter(
        channel_secret="test-line-secret",
        channel_access_token="test-line-token",
    )
    assert isinstance(client, LineAdapter)


def test_real_supabase_storage_adapter_satisfies_protocol() -> None:
    _skip_unless_enabled()
    client = SupabaseStorageAdapter(
        base_url="https://example.supabase.co",
        api_key="test-service-role",
        bucket="property-images",
    )
    assert isinstance(client, StorageAdapter)


def test_sign_helpers_round_trip() -> None:
    """The signature path the LINE webhook relies on — same code as mock + real."""
    from app.adapters.line import sign_line_webhook, verify_line_webhook

    body = b'{"events":[]}'
    secret = "abc"
    sig = sign_line_webhook(body, secret)
    assert verify_line_webhook(body, sig, secret) is True
    assert verify_line_webhook(body, sig, "wrong") is False
