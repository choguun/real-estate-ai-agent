"""Typed exceptions raised by the real Supabase adapter.

The router error handler in ``app/main.py`` maps these to HTTP responses
(403 / 404 / 500). Importing them from the adapter keeps the contract
explicit and testable.
"""

from __future__ import annotations


class SupabaseAdapterError(Exception):
    """Base for all real-adapter failures."""


class PermissionError(SupabaseAdapterError):
    """Raised when Supabase returns 401 or 403.

    Maps to HTTP 403 in the router error handler.
    """


class NotFoundError(SupabaseAdapterError):
    """Raised for explicit 404 lookups (currently unused — query()
    returns None for missing rows; kept for future use)."""
