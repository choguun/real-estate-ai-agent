"""AI adapter factory + chain.

Returns a list of adapters in priority order:
1. Anthropic (primary) — real or mock depending on `use_real_ai`.
2. Gemini (fallback)   — always wired (real client is a stub for MVP).

The ListingGeneratorService walks this list until one succeeds.

`use_mocks=True` is the master switch — even if `use_real_ai` is also set,
the mock chain wins. Document in `docs/adapters.md`.
"""

from __future__ import annotations

from app.adapters.ai.anthropic_mock import AnthropicMockAdapter
from app.adapters.ai.anthropic_real import AnthropicRealAdapter
from app.adapters.ai.base import AiAdapter
from app.adapters.ai.gemini_mock import GeminiMockAdapter
from app.adapters.ai.gemini_real import GeminiRealAdapter
from app.config import Settings, get_settings


def build_ai_chain(settings: Settings | None = None) -> list[AiAdapter]:
    settings = settings or get_settings()

    # Master switch: mocks win even when real is requested.
    if settings.use_mocks:
        return [AnthropicMockAdapter(), GeminiMockAdapter()]

    primary = (
        AnthropicRealAdapter(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
        if settings.use_real_ai
        else AnthropicMockAdapter()
    )
    fallback = (
        GeminiRealAdapter(api_key=settings.gemini_api_key, model=settings.gemini_model)
        if settings.use_real_ai
        else GeminiMockAdapter()
    )
    return [primary, fallback]
