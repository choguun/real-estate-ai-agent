"""Typed exceptions raised by the real storage adapter."""

from __future__ import annotations


class StorageAdapterError(Exception):
    """Base for all real storage adapter failures."""


class StorageUploadError(StorageAdapterError):
    """Raised when an upload fails (4xx/5xx from Supabase Storage)."""


class StorageDownloadError(StorageAdapterError):
    """Raised when a download fails."""


class StorageDeleteError(StorageAdapterError):
    """Raised when a delete fails for reasons other than 404."""
