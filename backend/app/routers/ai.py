"""AI router — POST /api/generate-listing."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter

from app.adapters.ai.base import BadRequest
from app.deps import AIChainDep, CurrentUserIdDep
from app.domain.listing import (
    GeneratedContent,
    ListingRequest,
    Platform,
)
from app.services.listing_generator import ListingGeneratorService

router = APIRouter(prefix="/api", tags=["ai"])


@router.post("/generate-listing", response_model=list[GeneratedContent])
def generate_listing(
    payload: ListingRequest,
    chain: AIChainDep,
    _user_id: CurrentUserIdDep,
) -> list[GeneratedContent]:
    """Generate Thai listing content for the requested platforms.

    Default: all 4 platforms. Pass `platforms: [Platform.facebook]` to limit.
    Latency budget: ≤ 2 s p99 in mock mode (real adapters ship as stubs).
    """
    platforms = payload.platforms or list(Platform)
    unknown = [p for p in platforms if p not in set(Platform)]
    if unknown:
        raise BadRequest(f"Unknown platform(s): {unknown}")

    service = ListingGeneratorService(adapters=chain)
    return service.generate(payload, platforms=platforms)


_ = Annotated  # silence unused-import for type-checkers
