"""T-102 — Real LINE adapter tests (httpx.MockTransport, no network).

Covers:
- send_reply hits the real Reply API with correct URL, headers, body
- Self-message filter short-circuits when line_user_id == bot_user_id
- Outbound transforms (strip_markdown + split_for_line) applied
- Reply-token cache wired: set → consume → drop
- 401/403 from LINE → typed LineAuthError
- get_bot_user_id fetches /v2/bot/info once + caches
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.adapters.line.base import LineAdapter
from app.adapters.line.errors import LineAuthError
from app.adapters.line.real import LineRealAdapter

CHANNEL_SECRET = "test-channel-secret"
CHANNEL_TOKEN = "test-channel-access-token"
API_BASE = "https://api.line.me"


def _make_handler(responses: list[tuple[int, Any]]):
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


# ── Protocol compliance ──────────────────────────────────────


def test_real_satisfies_protocol() -> None:
    """LineRealAdapter must implement the LineAdapter Protocol."""
    adapter = LineRealAdapter(
        channel_secret=CHANNEL_SECRET,
        channel_access_token=CHANNEL_TOKEN,
    )
    assert isinstance(adapter, LineAdapter)


# ── send_reply POST shape ───────────────────────────────────


def test_send_reply_posts_to_push_api_when_no_reply_token() -> None:
    handle, captured = _make_handler([(200, {"message": "ok"})])
    adapter = LineRealAdapter(
        channel_secret=CHANNEL_SECRET,
        channel_access_token=CHANNEL_TOKEN,
        api_base=API_BASE,
        transport=httpx.MockTransport(handle),
    )
    result = adapter.send_reply("U-buyer-1", "สวัสดีครับ")
    assert result["line_user_id"] == "U-buyer-1"
    assert result["via"] == "push"
    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    # No cached token → falls back to Push API
    assert str(req.url) == f"{API_BASE}/v2/bot/message/push"
    assert req.headers.get("Authorization") == f"Bearer {CHANNEL_TOKEN}"
    body = json.loads(req.content)
    assert body["to"] == "U-buyer-1"
    msgs = body["messages"]
    assert any("สวัสดี" in m.get("text", "") for m in msgs)


def test_send_reply_strips_markdown_before_send() -> None:
    handle, captured = _make_handler([(200, {"message": "ok"})])
    adapter = LineRealAdapter(
        channel_secret=CHANNEL_SECRET,
        channel_access_token=CHANNEL_TOKEN,
        api_base=API_BASE,
        transport=httpx.MockTransport(handle),
    )
    adapter.send_reply("U-buyer", "**hello** *world*")
    body = json.loads(captured[0].content)
    msgs = body["messages"]
    sent = " ".join(m.get("text", "") for m in msgs)
    assert "**hello**" not in sent
    assert "*world*" not in sent
    assert "hello" in sent
    assert "world" in sent


def test_send_reply_chunks_long_text_into_5_bubbles() -> None:
    handle, captured = _make_handler([(200, {"message": "ok"})])
    adapter = LineRealAdapter(
        channel_secret=CHANNEL_SECRET,
        channel_access_token=CHANNEL_TOKEN,
        api_base=API_BASE,
        transport=httpx.MockTransport(handle),
    )
    # 10 paragraphs of 1000 chars each = 10k chars total
    long_text = "\n\n".join(["A" * 1000 for _ in range(10)])
    adapter.send_reply("U-buyer", long_text)
    body = json.loads(captured[0].content)
    msgs = body["messages"]
    # LINE cap is 5 bubbles per call
    assert len(msgs) <= 5
    for m in msgs:
        assert len(m["text"]) <= 5000


# ── self-message echo filter ─────────────────────────────────


def test_send_reply_short_circuits_self_message() -> None:
    handle, captured = _make_handler([])  # no responses — should NOT hit network
    adapter = LineRealAdapter(
        channel_secret=CHANNEL_SECRET,
        channel_access_token=CHANNEL_TOKEN,
        api_base=API_BASE,
        transport=httpx.MockTransport(handle),
        bot_user_id="U-bot-self",
    )
    result = adapter.send_reply("U-bot-self", "echo!")
    assert result.get("skipped") == "self-message"
    assert len(captured) == 0  # no network call


# ── reply-token cache wired through send_reply ──────────────


def test_send_reply_uses_cached_reply_token() -> None:
    handle, captured = _make_handler([(200, {"message": "ok"})])
    adapter = LineRealAdapter(
        channel_secret=CHANNEL_SECRET,
        channel_access_token=CHANNEL_TOKEN,
        api_base=API_BASE,
        transport=httpx.MockTransport(handle),
    )
    adapter.set_reply_token("U-buyer-1", "rt-cached-123")
    adapter.send_reply("U-buyer-1", "hi")
    body = json.loads(captured[0].content)
    assert body["replyToken"] == "rt-cached-123"
    # Token consumed after use
    assert adapter.consume_reply_token("U-buyer-1")[0] is None


# ── error mapping ───────────────────────────────────────────


def test_401_from_line_raises_line_auth_error() -> None:
    handle, _ = _make_handler([(401, {"message": "invalid access token"})])
    adapter = LineRealAdapter(
        channel_secret=CHANNEL_SECRET,
        channel_access_token="BAD",
        api_base=API_BASE,
        transport=httpx.MockTransport(handle),
    )
    with pytest.raises(LineAuthError):
        adapter.send_reply("U-buyer", "hi")


# ── get_bot_user_id fetches /v2/bot/info once + caches ──────


def test_get_bot_user_id_fetches_and_caches() -> None:
    handle, captured = _make_handler(
        [(200, {"userId": "U-bot-abc", "basicId": "...", "displayName": "Bot"})]
    )
    adapter = LineRealAdapter(
        channel_secret=CHANNEL_SECRET,
        channel_access_token=CHANNEL_TOKEN,
        api_base=API_BASE,
        transport=httpx.MockTransport(handle),
    )
    # First call hits the API
    bot_id = adapter.get_bot_user_id()
    assert bot_id == "U-bot-abc"
    assert len(captured) == 1
    assert str(captured[0].url) == f"{API_BASE}/v2/bot/info"
    assert captured[0].headers.get("Authorization") == f"Bearer {CHANNEL_TOKEN}"
    # Second call uses the cache — no additional network call
    bot_id_2 = adapter.get_bot_user_id()
    assert bot_id_2 == "U-bot-abc"
    assert len(captured) == 1


def test_get_bot_user_id_uses_init_value_without_network() -> None:
    handle, captured = _make_handler([])
    adapter = LineRealAdapter(
        channel_secret=CHANNEL_SECRET,
        channel_access_token=CHANNEL_TOKEN,
        api_base=API_BASE,
        transport=httpx.MockTransport(handle),
        bot_user_id="U-preconfigured",
    )
    assert adapter.get_bot_user_id() == "U-preconfigured"
    assert len(captured) == 0
