"""AI adapter factory + chain.

Returns a list of adapters in priority order:
1. Anthropic (primary) — real or mock depending on `use_real_ai`.
2. Gemini (fallback)   — always wired (real client is a stub for MVP).

The ListingGeneratorService walks this list until one succeeds.
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
    chain: list[AiAdapter] = []

    if settings.use_real_ai:
        chain.append(
            AnthropicRealAdapter(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
        )
    else:
        chain.append(AnthropicMockAdapter())

    chain.append(
        GeminiRealAdapter(api_key=settings.gemini_api_key, model=settings.gemini_model)
        if settings.use_real_ai
        else GeminiMockAdapter()
    )
    return chain
