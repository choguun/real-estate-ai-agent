"""T-103 — Real Anthropic adapter tests (httpx.MockTransport, no network).

Exercises the real Anthropic Claude adapter through the official SDK
by injecting ``http_client=httpx.Client(transport=httpx.MockTransport(...))``
— same shape the production code path uses, no real API calls in CI.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.adapters.ai.anthropic_real import AnthropicRealAdapter
from app.adapters.ai.base import AiAdapter, BadRequest, FallbackToNext
from app.domain.listing import (
    GeneratedContent,
    ListingRequest,
    Platform,
    PropertySummary,
)


def _ok_response(text: str) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-3-5-sonnet-latest",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


def _capture_handler(responses: list[tuple[int, Any]]):
    captured: list[httpx.Request] = []
    queue = list(responses)

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if not queue:
            return httpx.Response(500, json={"error": "no canned response"})
        status, body = queue.pop(0)
        if isinstance(body, dict | list):
            return httpx.Response(status, json=body)
        return httpx.Response(status, text=str(body))

    return handle, captured


def _adapter(handler) -> AnthropicRealAdapter:
    return AnthropicRealAdapter(
        api_key="sk-test",
        model="claude-3-5-sonnet-latest",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _sample_request() -> ListingRequest:
    return ListingRequest(
        property=PropertySummary(
            title="คอนโดใกล้ BTS ทองหล่อ",
            property_type="condo",
            price=3_500_000,
            size_sqm=32,
            bedrooms=1,
            bathrooms=1,
            district="วัฒนา",
            province="กรุงเทพมหานคร",
            near_bts_mrt="BTS ทองหล่อ",
        ),
        platforms=[Platform.ddproperty],
    )


# ── Protocol compliance ──────────────────────────────────────


def test_real_satisfies_protocol() -> None:
    """AnthropicRealAdapter must implement the AiAdapter Protocol."""
    assert isinstance(_adapter(lambda r: httpx.Response(200, json={})), AiAdapter)


# ── Happy path ──────────────────────────────────────────────


def test_generate_parses_json_response_into_generated_content() -> None:
    payload = _ok_response(
        json.dumps(
            {
                "title": "คอนโดทองหล่อ",
                "description": "ห้องสวย วิวเมือง",
                "hashtags": ["#คอนโด", "#BTS"],
                "seo_keywords": ["คอนโด ทองหล่อ", "BTS"],
            },
            ensure_ascii=False,
        )
    )
    handle, captured = _capture_handler([(200, payload)])
    adapter = _adapter(handle)

    result = adapter.generate(_sample_request())

    assert isinstance(result, GeneratedContent)
    assert result.platform == Platform.ddproperty
    assert result.title == "คอนโดทองหล่อ"
    assert "ห้องสวย" in result.description
    assert result.hashtags == ["#คอนโด", "#BTS"]
    assert result.seo_keywords == ["คอนโด ทองหล่อ", "BTS"]
    assert result.ai_model == "claude-3-5-sonnet-latest"
    # And the request was sent to messages endpoint
    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    assert "/v1/messages" in str(req.url)
    body = json.loads(req.content)
    assert body["model"] == "claude-3-5-sonnet-latest"
    assert body["max_tokens"] > 0
    assert len(body["messages"]) == 1
    assert body["messages"][0]["role"] == "user"
    # The prompt must include the property details
    assert "BTS ทองหล่อ" in body["messages"][0]["content"]


def test_generate_strips_json_code_fences() -> None:
    """Models sometimes wrap JSON in ```json ... ``` fences — strip them."""
    fenced = (
        "```json\n"
        + json.dumps(
            {
                "title": "t",
                "description": "d",
                "hashtags": ["#a"],
                "seo_keywords": ["k"],
            },
            ensure_ascii=False,
        )
        + "\n```"
    )
    handle, _ = _capture_handler([(200, _ok_response(fenced))])
    adapter = _adapter(handle)

    result = adapter.generate(_sample_request())
    assert result.title == "t"
    assert result.hashtags == ["#a"]


# ── Transient error → FallbackToNext ────────────────────────


def test_rate_limit_429_raises_fallback() -> None:
    handle, _ = _capture_handler([(429, {"type": "error", "error": {"message": "rate limited"}})])
    adapter = _adapter(handle)
    with pytest.raises(FallbackToNext):
        adapter.generate(_sample_request())


def test_internal_server_error_500_raises_fallback() -> None:
    handle, _ = _capture_handler([(500, {"type": "error", "error": {"message": "oops"}})])
    adapter = _adapter(handle)
    with pytest.raises(FallbackToNext):
        adapter.generate(_sample_request())


def test_overloaded_raises_fallback() -> None:
    handle, _ = _capture_handler([(529, {"type": "error", "error": {"message": "overloaded"}})])
    adapter = _adapter(handle)
    with pytest.raises(FallbackToNext):
        adapter.generate(_sample_request())


# ── Fatal 4xx → BadRequest ───────────────────────────────────


def test_bad_request_400_raises_bad_request() -> None:
    handle, _ = _capture_handler([(400, {"type": "error", "error": {"message": "bad input"}})])
    adapter = _adapter(handle)
    with pytest.raises(BadRequest):
        adapter.generate(_sample_request())


def test_unauthorized_401_raises_bad_request() -> None:
    handle, _ = _capture_handler([(401, {"type": "error", "error": {"message": "bad key"}})])
    adapter = _adapter(handle)
    with pytest.raises(BadRequest):
        adapter.generate(_sample_request())


# ── model_name is exposed ────────────────────────────────────


def test_model_name_uses_init_value() -> None:
    handle, _ = _capture_handler([(200, _ok_response('{"title":"","description":""}'))])
    adapter = AnthropicRealAdapter(
        api_key="sk-test",
        model="claude-3-5-sonnet-20241022",
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    assert adapter.model_name == "claude-3-5-sonnet-20241022"


# ── prompt template is versioned ─────────────────────────────


def test_prompt_template_is_versioned() -> None:
    """The prompt module exposes a versioned constant + render function."""
    from app.adapters.ai.prompts import LISTING_PROMPT_V1, render_listing_prompt

    # The constant is named with a version suffix for A/B tracking
    assert LISTING_PROMPT_V1.endswith("preamble.".rstrip(".")) or "{platform}" in LISTING_PROMPT_V1
    assert "{property_summary}" in LISTING_PROMPT_V1
    # The render function produces a complete prompt string
    prompt = render_listing_prompt(_sample_request())
    assert "ddproperty" in prompt
    assert "BTS ทองหล่อ" in prompt
    assert "คอนโด" in prompt
