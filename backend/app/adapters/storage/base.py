"""Storage adapter Protocol — every blob store (mock + Supabase Storage) implements this.

Operations are file-level (bytes ↔ blob). The mock writes to local disk
under `var/uploads/`; the real implementation will hit Supabase Storage.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class StoredObject(BaseModel):
    """Result of a successful upload."""

    model_config = ConfigDict(extra="ignore")

    url: str
    key: str
    content_type: str
    size: int


ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def is_allowed_image(filename: str, content_type: str | None) -> bool:
    """Allow-list for image uploads. Reject anything else before it hits disk."""
    from pathlib import PurePosixPath

    ext = PurePosixPath(filename).suffix.lower()
    if ext and ext not in ALLOWED_IMAGE_EXTENSIONS:
        return False
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        return False
    return ext != ""  # require an extension


@runtime_checkable
class StorageAdapter(Protocol):
    """The single interface the rest of the app uses for blobs."""

    def upload(
        self,
        content: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> StoredObject:
        """Persist bytes, return a record with the public URL + key."""
        ...

    def get(self, key: str) -> tuple[bytes, str] | None:
        """Fetch bytes + content-type. None if no such key."""
        ...

    def delete(self, key: str) -> bool:
        """Remove by key. Idempotent — returns True if anything was removed."""
        ...
