"""Typed exceptions raised by the real LINE adapter.

Mapped to HTTP responses in the router error handler.
"""

from __future__ import annotations


class LineAdapterError(Exception):
    """Base for all real LINE adapter failures."""


class LineAuthError(LineAdapterError):
    """Raised when LINE returns 401 (invalid/expired access token)."""


class LineRateLimitError(LineAdapterError):
    """Raised on 429 — caller may retry with backoff."""


class LineAPIError(LineAdapterError):
    """Generic 4xx/5xx from the LINE Messaging API."""
