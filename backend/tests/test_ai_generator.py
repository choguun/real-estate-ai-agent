"""Tests for the listing generator — ST-006, ST-007 + fallback + latency."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.ai import (
    AnthropicMockAdapter,
    FallbackToNext,
    GeminiMockAdapter,
)
from app.deps import get_db_dep
from app.domain.listing import (
    GeneratedContent,
    ListingRequest,
    Platform,
)
from app.main import create_app
from app.services.listing_generator import ListingGeneratorService


# ─── Fixtures ───────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolate_state() -> Iterator[None]:
    from app.adapters.supabase._factory import reset_mock_singleton

    reset_mock_singleton()
    yield
    reset_mock_singleton()


def _condo_request(**overrides) -> ListingRequest:
    base = {
        "title": "คอนโดทดสอบ",
        "property_type": "condo",
        "price": 5_500_000.0,
        "size_sqm": 35.0,
        "bedrooms": 1,
        "bathrooms": 1,
        "floor": 12,
        "district": "Khlong Toei",
        "province": "Bangkok",
        "near_bts_mrt": "BTS Asok",
        "foreign_quota": True,
    }
    prop = {**base, **overrides.get("property", {})}
    return ListingRequest(property=prop, platforms=None, image_urls=None)


def _house_request() -> ListingRequest:
    return ListingRequest(
        property={
            "title": "บ้านเดี่ยว",
            "property_type": "house",
            "price": 12_000_000.0,
            "size_sqm": 200.0,
            "bedrooms": 4,
            "bathrooms": 3,
            "district": "Bang Na",
            "province": "Bangkok",
        },
        platforms=None,
        image_urls=None,
    )


# ─── ST-006: condo + ddproperty ────────────────────────────────────────
def test_condo_ddproperty_contains_thai_terms() -> None:
    gen = ListingGeneratorService(adapters=[AnthropicMockAdapter()])
    results = gen.generate(_condo_request())
    by_platform = {r.platform: r for r in results}
    dd = by_platform[Platform.ddproperty]
    assert "คอนโด" in dd.description
    assert "ตร.ม." in dd.description
    assert "ห้องนอน" in dd.description
    assert "BTS Asok" in dd.description


def test_condo_facebook_has_at_least_5_hashtags() -> None:
    gen = ListingGeneratorService(adapters=[AnthropicMockAdapter()])
    results = gen.generate(_condo_request())
    fb = next(r for r in results if r.platform == Platform.facebook)
    assert len(fb.hashtags) >= 5


def test_all_four_platforms_are_returned() -> None:
    gen = ListingGeneratorService(adapters=[AnthropicMockAdapter()])
    results = gen.generate(_condo_request())
    assert {r.platform for r in results} == set(Platform)


# ─── ST-007: house content ─────────────────────────────────────────────
def test_house_general_mentions_house() -> None:
    gen = ListingGeneratorService(adapters=[AnthropicMockAdapter()])
    results = gen.generate(_house_request())
    by_platform = {r.platform: r for r in results}
    gen_ = by_platform[Platform.general]
    blob = (gen_.title + " " + gen_.description).lower()
    assert "house" in blob or "บ้านเดี่ยว" in gen_.description


def test_house_ddproperty_mentions_size_in_thai() -> None:
    gen = ListingGeneratorService(adapters=[AnthropicMockAdapter()])
    results = gen.generate(_house_request())
    dd = next(r for r in results if r.platform == Platform.ddproperty)
    assert "200" in dd.description
    assert "ตร.ม." in dd.description


# ─── Latency budget (mock, 10 iterations × 4 platforms ≤ 2 s) ────────
def test_p99_latency_under_2s() -> None:
    gen = ListingGeneratorService(adapters=[AnthropicMockAdapter()])
    start = time.time()
    for _ in range(10):
        gen.generate(_condo_request())
    elapsed = time.time() - start
    assert elapsed < 2.0, f"Mock latency too high: {elapsed:.2f}s"


# ─── Fallback chain ────────────────────────────────────────────────────
class _FailingAdapter:
    """First in chain — always raises FallbackToNext."""

    @property
    def model_name(self) -> str:
        return "failing"

    def generate(self, request: ListingRequest) -> GeneratedContent:
        raise FallbackToNext("primary down")


def test_falls_back_when_primary_raises_fallback_to_next() -> None:
    chain = [_FailingAdapter(), GeminiMockAdapter()]
    gen = ListingGeneratorService(adapters=chain)
    results = gen.generate(_condo_request())
    assert len(results) == 4
    fb = next(r for r in results if r.platform == Platform.facebook)
    assert fb.ai_model == "gemini-2.0-flash-mock"


def test_4xx_surfaces_immediately_without_fallback() -> None:
    from app.adapters.ai.base import BadRequest

    class _BadAdapter:
        @property
        def model_name(self) -> str:
            return "bad"

        def generate(self, request: ListingRequest) -> GeneratedContent:
            raise BadRequest("invalid schema")

    chain = [_BadAdapter(), GeminiMockAdapter()]
    gen = ListingGeneratorService(adapters=chain)
    with pytest.raises(BadRequest, match="invalid schema"):
        gen.generate(_condo_request())


def test_falls_back_when_primary_raises_arbitrary_exception() -> None:
    class _BoomAdapter:
        @property
        def model_name(self) -> str:
            return "boom"

        def generate(self, request: ListingRequest) -> GeneratedContent:
            raise RuntimeError("network glitch")

    chain = [_BoomAdapter(), GeminiMockAdapter()]
    gen = ListingGeneratorService(adapters=chain)
    # Should NOT raise — falls back to Gemini.
    results = gen.generate(_condo_request())
    assert len(results) == 4


# ─── HTTP endpoint ─────────────────────────────────────────────────────
@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db_dep] = lambda: __import__(
        "app.adapters.supabase.mock", fromlist=["MockSupabaseAdapter"]
    ).MockSupabaseAdapter()
    with TestClient(app) as c:
        signup = c.post(
            "/api/auth/signup",
            json={"email": "ai@example.com", "full_name": "Ai", "password": "password123"},
        )
        token = signup.json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


def test_http_endpoint_returns_four_platforms(client: TestClient) -> None:
    res = client.post(
        "/api/generate-listing",
        json={
            "property": {
                "property_type": "condo",
                "price": 5_500_000.0,
                "size_sqm": 35.0,
                "bedrooms": 1,
                "bathrooms": 1,
                "district": "Khlong Toei",
                "near_bts_mrt": "BTS Asok",
            },
            "platforms": None,
            "image_urls": None,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body) == 4
    assert {b["platform"] for b in body} == {"ddproperty", "livinginsider", "facebook", "general"}


def test_http_endpoint_accepts_platform_filter(client: TestClient) -> None:
    res = client.post(
        "/api/generate-listing",
        json={
            "property": {"property_type": "house", "price": 1_000_000.0},
            "platforms": ["facebook"],
            "image_urls": None,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["platform"] == "facebook"


def test_http_endpoint_requires_auth() -> None:
    app = create_app()
    with TestClient(app) as c:
        res = c.post("/api/generate-listing", json={"property": {}, "platforms": None})
        assert res.status_code == 401


def test_http_endpoint_rejects_unknown_platform(client: TestClient) -> None:
    res = client.post(
        "/api/generate-listing",
        json={"property": {"property_type": "condo"}, "platforms": ["instagram"]},
    )
    # Pydantic's enum validator catches unknown platforms → 422 (handler raises BadRequest → 400).
    assert res.status_code in (400, 422)
