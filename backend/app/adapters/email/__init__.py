"""Email adapter package."""

from app.adapters.email.base import EmailAdapter
from app.adapters.email.factory import build_email_adapter, reset_cache
from app.adapters.email.mock import MockEmailAdapter
from app.adapters.email.real import ResendEmailAdapter

__all__ = [
    "EmailAdapter",
    "MockEmailAdapter",
    "ResendEmailAdapter",
    "build_email_adapter",
    "reset_cache",
]
