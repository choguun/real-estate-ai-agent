"""Listing generator service — orchestrates the AI chain across 4 platforms."""

from __future__ import annotations

import logging

from app.adapters.ai.base import AiAdapter, BadRequest
from app.domain.listing import GeneratedContent, ListingRequest, Platform

logger = logging.getLogger(__name__)


class ListingGeneratorService:
    def __init__(self, adapters: list[AiAdapter]) -> None:
        if not adapters:
            raise ValueError("At least one AI adapter is required")
        self._adapters = list(adapters)

    def generate(
        self, request: ListingRequest, *, platforms: list[Platform] | None = None
    ) -> list[GeneratedContent]:
        """Generate one variant per platform. Surfaces on 4xx; falls back on transient errors."""
        target_platforms = platforms or list(Platform)
        results: list[GeneratedContent] = []
        for platform in target_platforms:
            req = ListingRequest(
                property=request.property,
                platforms=[platform],
                image_urls=request.image_urls,
            )
            results.append(self._generate_one(req))
        return results

    def _generate_one(self, request: ListingRequest) -> GeneratedContent:
        last_exc: Exception | None = None
        for adapter in self._adapters:
            try:
                return adapter.generate(request)
            except BadRequest:
                # Permanent error — surface immediately.
                raise
            except Exception as exc:  # includes FallbackToNext + any unexpected
                logger.warning(
                    "ai adapter %s failed, trying next",
                    type(adapter).__name__,
                    exc_info=exc,
                )
                last_exc = exc
                continue
        raise RuntimeError(f"All AI adapters failed: {last_exc!r}")
