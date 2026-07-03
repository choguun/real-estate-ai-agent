"""Versioned prompt templates for the AI adapters.

Single source of truth for the prompt sent to the real AI. Versioned
so we can A/B without code rewrites. Mock adapters don't use these
(deterministic templates instead); the real adapters build the
final prompt from one of these.
"""

from __future__ import annotations

from textwrap import dedent

from app.domain.listing import ListingRequest, Platform

LISTING_PROMPT_V1: str = dedent(
    """
    You are a Thai real-estate copywriter. Write a {platform} listing
    for the following property in Thai language.

    Property:
    {property_summary}

    Required output (valid JSON, no prose):
    {{
      "title": "concise headline ≤ 80 chars",
      "description": "3-5 sentences, Thai, marketing tone",
      "hashtags": ["#tag1", "#tag2", ...],  // 3-7 hashtags
      "seo_keywords": ["kw1", "kw2", ...]   // 3-7 SEO keywords
    }}

    Use the Thai property terms: คอนโด, บ้านเดี่ยว, ทาวน์เฮาส์,
    ที่ดิน, อาคารพาณิชย์. Use ตร.ม. for size, ห้องนอน / ห้องน้ำ
    for bedrooms / bathrooms. Include BTS/MRT station name in SEO
    keywords if near_bts_mrt is set.

    Output JSON only — no markdown, no preamble.
    """
).strip()


def render_listing_prompt(request: ListingRequest) -> str:
    """Build the prompt text for a given listing request."""
    p = request.property
    summary_lines = [
        f"title: {p.title}" if p.title else None,
        f"type: {p.property_type}" if p.property_type else None,
        f"price: {p.price:,.0f} THB" if p.price else None,
        f"size: {p.size_sqm} ตร.ม." if p.size_sqm else None,
        f"bedrooms: {p.bedrooms}" if p.bedrooms else None,
        f"bathrooms: {p.bathrooms}" if p.bathrooms else None,
        f"floor: {p.floor}" if p.floor else None,
        f"address: {p.address}" if p.address else None,
        f"district: {p.district}" if p.district else None,
        f"province: {p.province}" if p.province else None,
        f"near_bts_mrt: {p.near_bts_mrt}" if p.near_bts_mrt else None,
        f"foreign_quota: {p.foreign_quota}" if p.foreign_quota is not None else None,
    ]
    summary = "\n".join(line for line in summary_lines if line)
    platforms = request.platforms or list(Platform)
    # Per call the orchestrator iterates platforms; the prompt is
    # rendered once per call with the specific platform name.
    return LISTING_PROMPT_V1.format(
        platform=platforms[0].value if platforms else "general",
        property_summary=summary,
    )
