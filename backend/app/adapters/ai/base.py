"""AI adapter Protocol — every generator (mock + Anthropic + Gemini) implements this.

Two exception types let the orchestrator distinguish recoverable from
fatal failures:
- `FallbackToNext` — transient (rate limit, timeout, 5xx). Service tries the
  next adapter in the chain.
- `BadRequest` — 4xx errors (other than 429). Service surfaces to caller.

Adapters never raise anything else.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.listing import GeneratedContent, ListingRequest


class FallbackToNext(Exception):
    """Signal a transient failure. The orchestrator should try the next adapter."""


class BadRequest(Exception):
    """4xx-style error. The orchestrator should surface to the caller."""


@runtime_checkable
class AiAdapter(Protocol):
    """The single interface for generating listing content."""

    @property
    def model_name(self) -> str:
        """For audit (`generated_listings.ai_model`)."""
        ...

    def generate(self, request: ListingRequest) -> GeneratedContent:
        """Produce a single platform's content."""
        ...
