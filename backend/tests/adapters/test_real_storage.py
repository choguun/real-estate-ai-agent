"""T-104 — Real Supabase Storage adapter tests (httpx.MockTransport).

The merged cycle-1 storage Protocol is:
  - upload(content, *, filename, content_type) -> StoredObject
  - get(key) -> tuple[bytes, str] | None
  - delete(key) -> bool

The real adapter hits Supabase Storage REST:
  - POST /storage/v1/object/{bucket}/{key}        — upload (raw body)
  - GET  /storage/v1/object/{bucket}/{key}        — download
  - DELETE /storage/v1/object/{bucket}/{key}      — remove

Public URLs are returned as
``{SUPABASE_URL}/storage/v1/object/public/{bucket}/{key}`` for public
buckets, or as signed URLs via ``POST /storage/v1/object/sign/{bucket}/{key}``
when the bucket is private (default).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.adapters.storage.base import StorageAdapter, StoredObject
from app.adapters.storage.errors import StorageUploadError
from app.adapters.storage.supabase_real import SupabaseStorageAdapter

SUPABASE_URL = "https://abc.supabase.co"
SERVICE_KEY = "eyJ-test-service-key"
BUCKET = "uploads"


def _capture_handler(responses: list[tuple[int, Any]]):
    captured: list[httpx.Request] = []
    queue = list(responses)

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if not queue:
            return httpx.Response(500, json={"error": "no canned response"})
        status, body = queue.pop(0)
        if isinstance(body, dict | list):
            return httpx.Response(status, json=body)
        return httpx.Response(status, text=str(body))

    return handle, captured


def _adapter(handler, *, bucket: str = BUCKET, private: bool = False) -> SupabaseStorageAdapter:
    return SupabaseStorageAdapter(
        base_url=SUPABASE_URL,
        api_key=SERVICE_KEY,
        bucket=bucket,
        private=private,
        transport=httpx.MockTransport(handler),
    )


# ── Protocol compliance ──────────────────────────────────────


def test_real_satisfies_protocol() -> None:
    """SupabaseStorageAdapter must implement the StorageAdapter Protocol."""
    assert isinstance(
        SupabaseStorageAdapter(base_url=SUPABASE_URL, api_key=SERVICE_KEY, bucket=BUCKET),
        StorageAdapter,
    )


# ── upload (public bucket) ──────────────────────────────────


def test_upload_posts_raw_bytes_to_object_path() -> None:
    handle, captured = _capture_handler([(200, {"Key": "abc/cover.png"})])
    adapter = _adapter(handle)

    obj = adapter.upload(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        filename="cover.png",
        content_type="image/png",
    )

    assert isinstance(obj, StoredObject)
    assert obj.content_type == "image/png"
    assert obj.size == len(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    assert obj.key.endswith(".png")
    # URL points to the public Supabase Storage path
    assert obj.url == f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{obj.key}"
    # And the upload hit the right endpoint with raw body
    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    assert str(req.url).startswith(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/")
    assert req.headers.get("Authorization") == f"Bearer {SERVICE_KEY}"
    assert req.headers.get("Content-Type") == "image/png"
    assert req.content == b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


# ── upload (private bucket → signed URL) ─────────────────────


def test_upload_to_private_bucket_returns_signed_url() -> None:
    handle, captured = _capture_handler(
        [
            (200, {"Key": "abc/secret.png"}),  # upload
            (200, {"signedURL": "/storage/v1/object/sign/abc/secret.png?token=xyz"}),
        ]
    )
    adapter = _adapter(handle, private=True)

    obj = adapter.upload(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        filename="secret.png",
        content_type="image/png",
    )

    # Two requests fired: upload + sign
    assert len(captured) == 2
    assert captured[0].method == "POST"
    assert str(captured[0].url).startswith(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/")
    # Second: signed-URL request (POST /storage/v1/object/sign/...)
    assert captured[1].method == "POST"
    assert str(captured[1].url).endswith(f"/storage/v1/object/sign/{BUCKET}/{obj.key}")
    assert obj.url.endswith("?token=xyz")


# ── rejects empty / wrong content type ──────────────────────


def test_upload_rejects_empty_bytes() -> None:
    handle, _ = _capture_handler([])
    adapter = _adapter(handle)
    with pytest.raises(ValueError, match="empty"):
        adapter.upload(b"", filename="x.png", content_type="image/png")


def test_upload_rejects_unsupported_content_type() -> None:
    handle, _ = _capture_handler([])
    adapter = _adapter(handle)
    with pytest.raises(ValueError, match="Unsupported"):
        adapter.upload(b"data", filename="malware.exe", content_type="application/x-msdownload")


def test_upload_rejects_oversized_payload() -> None:
    handle, _ = _capture_handler([])
    adapter = _adapter(handle)
    big = b"x" * (11 * 1024 * 1024)  # 11 MiB > 10 MiB cap
    with pytest.raises(ValueError, match="exceeds max size"):  # empty test overrides below
        adapter.upload(big, filename="huge.png", content_type="image/png")


# ── error mapping ───────────────────────────────────────────


def test_400_from_supabase_raises_storage_upload_error() -> None:
    handle, _ = _capture_handler([(400, {"message": "InvalidKey"})])
    adapter = _adapter(handle)
    with pytest.raises(StorageUploadError):
        adapter.upload(b"data", filename="x.png", content_type="image/png")


def test_401_raises_storage_upload_error() -> None:
    handle, _ = _capture_handler([(401, {"message": "InvalidToken"})])
    adapter = _adapter(handle)
    with pytest.raises(StorageUploadError):
        adapter.upload(b"data", filename="x.png", content_type="image/png")


# ── get / delete ────────────────────────────────────────────


def test_get_returns_bytes_and_content_type() -> None:
    handle, captured = _capture_handler([(200, b"image-bytes-here")])

    def alt_handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200, content=b"image-bytes-here", headers={"content-type": "image/png"}
        )

    adapter2 = SupabaseStorageAdapter(
        base_url=SUPABASE_URL,
        api_key=SERVICE_KEY,
        bucket=BUCKET,
        transport=httpx.MockTransport(alt_handle),
    )
    result = adapter2.get("cover.png")
    assert result is not None
    data, ct = result
    assert data == b"image-bytes-here"
    assert ct == "image/png"


def test_get_returns_none_on_404() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    adapter = _adapter(handle)
    assert adapter.get("missing.png") is None


def test_delete_returns_true_on_2xx() -> None:
    handle, captured = _capture_handler([(200, {"message": "ok"})])
    adapter = _adapter(handle)
    assert adapter.delete("cover.png") is True
    assert captured[0].method == "DELETE"


def test_delete_returns_false_on_404() -> None:
    handle, _ = _capture_handler([(404, "Not Found")])
    adapter = _adapter(handle)
    assert adapter.delete("missing.png") is False


# ── 5xx → typed error (P1-W2) ───────────────────────────────


def test_get_5xx_raises_storage_download_error() -> None:
    """P1-W2: 5xx must raise typed error (not silently None)."""
    from app.adapters.storage.errors import StorageDownloadError

    handle, _ = _capture_handler([(503, "Service Unavailable")])
    adapter = _adapter(handle)
    with pytest.raises(StorageDownloadError, match="503"):
        adapter.get("cover.png")
