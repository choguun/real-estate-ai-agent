"""AI adapters — Anthropic (primary) + Gemini (fallback)."""

from app.adapters.ai.anthropic_mock import AnthropicMockAdapter
from app.adapters.ai.anthropic_real import AnthropicRealAdapter
from app.adapters.ai.base import AiAdapter, BadRequest, FallbackToNext
from app.adapters.ai.gemini_mock import GeminiMockAdapter
from app.adapters.ai.gemini_real import GeminiRealAdapter

__all__ = [
    "AiAdapter",
    "AnthropicMockAdapter",
    "AnthropicRealAdapter",
    "GeminiMockAdapter",
    "GeminiRealAdapter",
    "FallbackToNext",
    "BadRequest",
]
