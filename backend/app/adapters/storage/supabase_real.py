"""Real Supabase Storage adapter.

Wires to Supabase Storage REST:
  POST   /storage/v1/object/{bucket}/{key}        — upload (raw body)
  GET    /storage/v1/object/{bucket}/{key}        — download
  DELETE /storage/v1/object/{bucket}/{key}        — remove
  POST   /storage/v1/object/sign/{bucket}/{key}   — signed URL (private)

Public buckets return a stable public URL; private buckets return a
short-lived signed URL via the sign endpoint.

The 10 MiB cap + image/* MIME allow-list from the mock are preserved
client-side so we don't waste bandwidth on rejected uploads.
"""

from __future__ import annotations

import re
import uuid
from pathlib import PurePosixPath
from typing import Any

import httpx

from app.adapters.storage.base import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_TYPES,
    StoredObject,
)
from app.adapters.storage.errors import StorageUploadError

_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
_SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]+$")


class SupabaseStorageAdapter:
    """Real Supabase Storage client implementing ``StorageAdapter``."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        bucket: str = "uploads",
        private: bool = False,
        transport: httpx.MockTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._bucket = bucket
        self._private = private
        if transport is not None:
            self._client = httpx.Client(transport=transport, timeout=timeout)
            self._owns_client = True
        else:
            self._client = httpx.Client(timeout=timeout)
            self._owns_client = True

    # ── upload ─────────────────────────────────────────────────
    def upload(
        self,
        content: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> StoredObject:
        if not content:
            raise ValueError("Upload body is empty")
        if len(content) > _MAX_BYTES:
            raise ValueError(f"Upload exceeds max size ({_MAX_BYTES} bytes)")
        if not _validate_upload(filename, content_type):
            raise ValueError(f"Unsupported content-type: {content_type!r} for {filename!r}")

        ext = PurePosixPath(filename).suffix.lower() or ".bin"
        key = f"{uuid.uuid4().hex}{ext}"

        response = self._client.post(
            f"{self._base_url}/storage/v1/object/{self._bucket}/{key}",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": content_type,
            },
            content=content,
        )
        if response.status_code in (400, 401, 403):
            raise StorageUploadError(
                f"Supabase Storage upload failed ({response.status_code}): {response.text}"
            )
        if not response.is_success:
            raise StorageUploadError(
                f"Supabase Storage upload failed ({response.status_code}): {response.text}"
            )

        # Resolve the public URL
        if self._private:
            url = self._sign_url(key)
        else:
            url = f"{self._base_url}/storage/v1/object/public/{self._bucket}/{key}"

        return StoredObject(
            url=url,
            key=key,
            content_type=content_type,
            size=len(content),
        )

    def _sign_url(self, key: str) -> str:
        """Ask Supabase for a short-lived signed URL on a private bucket."""
        response = self._client.post(
            f"{self._base_url}/storage/v1/object/sign/{self._bucket}/{key}",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={},
        )
        if not response.is_success:
            raise StorageUploadError(
                f"Supabase Storage sign URL failed ({response.status_code}): {response.text}"
            )
        signed_path_raw: Any = response.json().get("signedURL", "")
        signed_path: str = str(signed_path_raw)
        if not signed_path:
            raise StorageUploadError("Supabase Storage sign URL returned empty path")
        # signed_path is a path like /storage/v1/object/sign/.../?token=... —
        # if it's already a full URL the response included the host, otherwise
        # the caller needs to prefix with the API base.
        if signed_path.startswith("http"):
            return signed_path
        return f"{self._base_url}{signed_path}"

    # ── get / delete ─────────────────────────────────────────
    def get(self, key: str) -> tuple[bytes, str] | None:
        if not _SAFE_KEY.match(key) or "/" in key or "\\" in key:
            return None
        response = self._client.get(
            f"{self._base_url}/storage/v1/object/{self._bucket}/{key}",
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        if response.status_code == 404:
            return None
        if not response.is_success:
            return None
        ct = response.headers.get("content-type") or "application/octet-stream"
        return response.content, ct

    def delete(self, key: str) -> bool:
        if not _SAFE_KEY.match(key) or "/" in key or "\\" in key:
            return False
        response = self._client.delete(
            f"{self._base_url}/storage/v1/object/{self._bucket}/{key}",
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        if response.status_code == 404:
            return False
        return response.is_success

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _validate_upload(filename: str, content_type: str | None) -> bool:
    """Same allow-list as the local mock: image extensions + MIME types."""
    ext = PurePosixPath(filename).suffix.lower()
    if not ext or ext not in ALLOWED_IMAGE_EXTENSIONS:
        return False
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:  # noqa: SIM103
        return False
    return True
