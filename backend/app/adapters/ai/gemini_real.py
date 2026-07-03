"""Real Google Gemini adapter — stub for MVP."""

from __future__ import annotations

from app.adapters.ai.base import FallbackToNext
from app.domain.listing import GeneratedContent, ListingRequest


class GeminiRealAdapter:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.0-flash-exp",
    ) -> None:
        self._api_key = api_key
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, request: ListingRequest) -> GeneratedContent:
        raise FallbackToNext(
            "GeminiRealAdapter is not wired in MVP. "
            "Set use_real_ai=false (default) to use mocks."
        )
