"""LINE adapter factory."""

from __future__ import annotations

from app.adapters.line.base import LineAdapter
from app.adapters.line.mock import LineMockAdapter
from app.adapters.line.real import LineRealAdapter
from app.config import Settings, get_settings


def get_line_adapter(settings: Settings | None = None) -> LineAdapter:
    """Pick LINE adapter. `use_mocks=True` is the master switch and
    forces the mock regardless of `use_real_line`.
    """
    settings = settings or get_settings()
    if settings.use_mocks:
        return LineMockAdapter(channel_secret=settings.line_channel_secret)
    if settings.use_real_line:
        return LineRealAdapter(
            channel_secret=settings.line_channel_secret,
            channel_access_token=settings.line_channel_access_token,
        )
    return LineMockAdapter(channel_secret=settings.line_channel_secret)
