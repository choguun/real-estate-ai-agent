"""Real Anthropic Claude adapter.

Calls Claude via the official ``anthropic`` SDK. Maps SDK errors to
``FallbackToNext`` (transient) or ``BadRequest`` (fatal) so the
chain orchestrator can fall back to Gemini on rate limits and surface
real 4xx errors.

Tested via ``http_client=httpx.Client(transport=httpx.MockTransport(...))``
to keep CI offline.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic
import httpx

from app.adapters.ai.base import BadRequest, FallbackToNext
from app.adapters.ai.prompts import render_listing_prompt
from app.domain.listing import GeneratedContent, ListingRequest, Platform

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-3-5-sonnet-latest"
MAX_TOKENS = 1024


# Transient SDK errors that should trigger fallback to the next adapter.
_TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    anthropic.RateLimitError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
    anthropic.OverloadedError,
)


class AnthropicRealAdapter:
    """Real Anthropic adapter — implements ``AiAdapter`` Protocol."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        client: anthropic.Anthropic | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        if client is not None:
            self._client = client
        else:
            kwargs: dict[str, Any] = {"api_key": api_key}
            if http_client is not None:
                kwargs["http_client"] = http_client
            self._client = anthropic.Anthropic(**kwargs)

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, request: ListingRequest) -> GeneratedContent:
        prompt = render_listing_prompt(request)
        platforms: list[Platform] = request.platforms or [Platform.general]
        platform: Platform | None = platforms[0]
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        except _TRANSIENT_ERRORS as exc:
            logger.warning("Anthropic transient error, falling back: %s", exc)
            raise FallbackToNext(f"transient anthropic error: {exc}") from exc
        except anthropic.APIStatusError as exc:
            # 4xx other than rate-limit → fatal
            raise BadRequest(f"anthropic api error ({exc.status_code}): {exc.message}") from exc

        text = _extract_text(response)
        parsed = _parse_json(text)
        platform_value: Platform = platform if platform else Platform.general

        return GeneratedContent(
            platform=platform_value,
            title=str(parsed.get("title", "")).strip()[:240] or "Untitled",
            description=str(parsed.get("description", "")).strip()[:20_000],
            hashtags=[str(h).strip() for h in parsed.get("hashtags", []) if h],
            seo_keywords=[str(k).strip() for k in parsed.get("seo_keywords", []) if k],
            ai_model=self._model,
            prompt_used=prompt,
        )


def _extract_text(response: Any) -> str:
    """Pull the model's text out of the SDK response object."""
    content = getattr(response, "content", None) or []
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _parse_json(text: str) -> dict[str, Any]:
    """Best-effort JSON parse — strip fences, fallback to empty dict."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip ```json ... ``` fences the model sometimes wraps output in.
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Anthropic returned non-JSON; using empty fields")
        return {}
    if not isinstance(result, dict):
        return {}
    return result
