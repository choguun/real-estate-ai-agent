"""Real Anthropic Claude adapter — stub for MVP."""

from __future__ import annotations

from app.adapters.ai.base import BadRequest, FallbackToNext
from app.domain.listing import GeneratedContent, ListingRequest


class AnthropicRealAdapter:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-3-5-sonnet-latest",
        client: object | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client  # lazy import `anthropic.Anthropic` in wiring task

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, request: ListingRequest) -> GeneratedContent:
        raise FallbackToNext(
            "AnthropicRealAdapter is not wired in MVP. "
            "Set use_real_ai=false (default) to use mocks."
        )


# Suppress lint — used only for isinstance in tests
_ = BadRequest
