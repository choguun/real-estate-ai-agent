"""Deterministic Thai-template mock for Claude 3.5 Sonnet.

Produces Thai listings per (property_type, platform) using a small
template library. Templates include unit-relevant terms (ตร.ม., ห้องนอน)
so tests can assert substring presence.

Latency: instant (no sleep). Real Anthropic adapter ships as a stub.
"""

from __future__ import annotations

import textwrap

from app.domain.listing import GeneratedContent, ListingRequest, Platform, PropertySummary

MODEL_NAME = "claude-3-5-sonnet-mock"


class AnthropicMockAdapter:
    """Mock Claude — Thai templates, deterministic output."""

    @property
    def model_name(self) -> str:
        return MODEL_NAME

    def generate(self, request: ListingRequest) -> GeneratedContent:
        p = request.property
        ptype = (p.property_type or "general").lower()
        platform = _resolve_platform(request)

        if platform == Platform.ddproperty:
            return _ddproperty(request, ptype)
        if platform == Platform.livinginsider:
            return _livinginsider(request, ptype)
        if platform == Platform.facebook:
            return _facebook(request, ptype)
        return _general(request, ptype)


# ─── Helpers ────────────────────────────────────────────────────────────
def _resolve_platform(req: ListingRequest) -> Platform:
    """Pick a platform from the request — used when fanning out per platform."""
    if req.platforms:
        return req.platforms[0]
    return Platform.general


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}"


def _type_th(value: str | None) -> str:
    return {
        "condo": "คอนโด",
        "house": "บ้านเดี่ยว",
        "townhouse": "ทาวน์เฮาส์",
        "land": "ที่ดิน",
        "commercial": "อาคารพาณิชย์",
    }.get((value or "").lower(), value or "ทรัพย์สิน")


def _loc(p: PropertySummary) -> str:
    parts = [p.district, p.province]
    return ", ".join(x for x in parts if x) or "ทำเลดี"


# ─── Templates ──────────────────────────────────────────────────────────
def _ddproperty(req: ListingRequest, ptype: str) -> GeneratedContent:
    p = req.property
    t = _type_th(p.property_type)
    loc = _loc(p)
    near = f" ใกล้ {p.near_bts_mrt}" if p.near_bts_mrt else ""

    bed_bath = (
        f"{p.bedrooms or '?'} ห้องนอน {p.bathrooms or '?'} ห้องน้ำ"
        if p.bedrooms or p.bathrooms
        else ""
    )
    size = f" {p.size_sqm:g} ตร.ม." if p.size_sqm else ""

    title_bits = [t]
    if p.bedrooms:
        title_bits.append(f"{p.bedrooms} ห้องนอน")
    if p.size_sqm:
        title_bits.append(f"{p.size_sqm:g} ตร.ม.")
    if p.district:
        title_bits.append(p.district)
    title = " ".join(title_bits)

    description = textwrap.dedent(
        f"""
        ขาย{t} {bed_bath}{size} {loc}{near}

        รายละเอียด:
        - ประเภท: {t}
        - ขนาด: {p.size_sqm or '—'} ตร.ม.
        - ห้องนอน: {p.bedrooms or '—'}
        - ห้องน้ำ: {p.bathrooms or '—'}
        - ชั้น: {p.floor or '—'}
        - ทำเล: {loc}
        - ราคา: {_money(p.price)} บาท
        - โควต้าต่างชาติ: {'มี' if p.foreign_quota else 'ไม่มี'}

        สนใจติดต่อ ดูสถานที่จริงได้ตามสะดวก
        """
    ).strip()

    return GeneratedContent(
        platform=Platform.ddproperty,
        title=title,
        description=description,
        hashtags=[],
        seo_keywords=_seo_keywords(p),
        ai_model=MODEL_NAME,
        prompt_used=f"ddproperty:{ptype}",
    )


def _livinginsider(req: ListingRequest, ptype: str) -> GeneratedContent:
    p = req.property
    t = _type_th(p.property_type)
    loc = _loc(p)

    title = f"{t} {p.bedrooms or '?'} ห้องนอน {p.size_sqm or '?'} ตร.ม. {p.district or ''}".strip()

    parts = [f"✨ {t} พร้อมอยู่ ทำเล {loc}"]
    if p.near_bts_mrt:
        parts.append(f"🚆 ใกล้ {p.near_bts_mrt}")
    if p.size_sqm:
        parts.append(f"📐 พื้นที่ {p.size_sqm:g} ตร.ม.")
    if p.bedrooms and p.bathrooms:
        parts.append(f"🛏 {p.bedrooms} ห้องนอน · 🚿 {p.bathrooms} ห้องน้ำ")
    if p.price:
        parts.append(f"💰 ราคา {_money(p.price)} บาท")
    if p.foreign_quota:
        parts.append("🌏 โควต้าต่างชาติ")

    description = "\n".join(parts)

    return GeneratedContent(
        platform=Platform.livinginsider,
        title=title,
        description=description,
        hashtags=[],
        seo_keywords=_seo_keywords(p),
        ai_model=MODEL_NAME,
        prompt_used=f"livinginsider:{ptype}",
    )


def _facebook(req: ListingRequest, ptype: str) -> GeneratedContent:
    p = req.property
    t = _type_th(p.property_type)

    title = f"🔥 ขาย{t} {p.district or ''}".strip()

    parts = [f"🚨 ขายด่วน! {t}"]
    if p.district:
        parts.append(f"📍 {p.district}, {p.province or 'Bangkok'}")
    if p.near_bts_mrt:
        parts.append(f"🚆 ใกล้ {p.near_bts_mrt}")
    if p.size_sqm:
        parts.append(f"📐 {p.size_sqm:g} ตร.ม.")
    if p.bedrooms and p.bathrooms:
        parts.append(f"🛏 {p.bedrooms} ห้องนอน / 🚿 {p.bathrooms} ห้องน้ำ")
    if p.price:
        parts.append(f"💰 ฿{_money(p.price)}")
    if p.foreign_quota:
        parts.append("🌏 โควต้าต่างชาติ")
    parts.append("สนใจทักแชทมาได้เลยค่ะ 💬")

    description = "\n".join(parts)
    hashtags = _hashtags(p)

    return GeneratedContent(
        platform=Platform.facebook,
        title=title,
        description=description,
        hashtags=hashtags,
        seo_keywords=[],
        ai_model=MODEL_NAME,
        prompt_used=f"facebook:{ptype}",
    )


def _general(req: ListingRequest, ptype: str) -> GeneratedContent:
    p = req.property
    en_type = {
        "condo": "Condo",
        "house": "House",
        "townhouse": "Townhouse",
        "land": "Land",
        "commercial": "Commercial",
    }.get((p.property_type or "").lower(), "Property")

    loc = _loc(p)

    title = f"{en_type} for sale — {p.district or 'Bangkok'}"
    parts: list[str] = []
    parts.append(f"{en_type} in {loc}.")
    if p.size_sqm:
        parts.append(f"Size: {p.size_sqm:g} sqm")
    if p.bedrooms is not None and p.bathrooms is not None:
        parts.append(f"{p.bedrooms} bed / {p.bathrooms} bath")
    if p.floor is not None:
        parts.append(f"Floor {p.floor}")
    if p.near_bts_mrt:
        parts.append(f"Near {p.near_bts_mrt}")
    if p.price:
        parts.append(f"Price: ฿{_money(p.price)}")
    if p.foreign_quota:
        parts.append("Foreign quota available")
    description = "\n".join(f"• {x}" for x in parts)

    return GeneratedContent(
        platform=Platform.general,
        title=title,
        description=description,
        hashtags=[],
        seo_keywords=_seo_keywords(p),
        ai_model=MODEL_NAME,
        prompt_used=f"general:{ptype}",
    )


def _seo_keywords(p: PropertySummary) -> list[str]:
    out: list[str] = []
    if p.property_type:
        out.append(_type_th(p.property_type))
    if p.district:
        out.append(p.district)
    if p.province:
        out.append(p.province)
    if p.near_bts_mrt:
        parts = p.near_bts_mrt.split()
        out.append(parts[1] if len(parts) > 1 else p.near_bts_mrt)
    if p.foreign_quota:
        out.append("โควต้าต่างชาติ")
    return out


def _hashtags(p: PropertySummary) -> list[str]:
    out: list[str] = []
    pt = (p.property_type or "").lower()
    out.append(
        {
            "condo": "#คอนโด",
            "house": "#บ้านเดี่ยว",
            "townhouse": "#ทาวน์เฮาส์",
            "land": "#ที่ดิน",
            "commercial": "#อาคารพาณิชย์",
        }.get(pt, "#อสังหา")
    )
    if p.district:
        out.append(f"#{p.district.replace(' ', '')}")
    out.append("#ขาย")
    out.append("#Bangkok")
    out.append("#ลงทุน")
    out.append("#อสังหาริมทรัพย์")
    return out
