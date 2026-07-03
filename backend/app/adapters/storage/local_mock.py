"""In-memory + local-disk storage adapter.

Files live under `{var_dir}/uploads/`. Public URLs are built as
`{public_base_url}/static/{key}`. The FastAPI app serves those URLs
via the same `LocalStorageAdapter.get()` so storage stays the single
source of truth.
"""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from app.adapters.storage.base import StoredObject


class LocalStorageAdapter:
    """Filesystem-backed storage; works locally + in tests via TestClient."""

    def __init__(
        self,
        var_dir: str | Path,
        public_base_url: str,
        *,
        max_size_bytes: int = 10 * 1024 * 1024,  # 10 MiB cap
    ) -> None:
        self._root = Path(var_dir) / "uploads"
        self._root.mkdir(parents=True, exist_ok=True)
        self._public_base_url = public_base_url.rstrip("/")
        self._max_size = max_size_bytes

    @property
    def root(self) -> Path:
        return self._root

    @staticmethod
    def _ext(filename: str) -> str:
        from pathlib import PurePosixPath

        return PurePosixPath(filename).suffix.lower()

    def upload(
        self,
        content: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> StoredObject:
        if not content:
            raise ValueError("Upload body is empty")
        if len(content) > self._max_size:
            raise ValueError(f"Upload exceeds max size ({self._max_size} bytes)")

        ext = self._ext(filename)
        key = f"{uuid.uuid4().hex}{ext}"
        path = self._root / key
        path.write_bytes(content)

        return StoredObject(
            url=f"{self._public_base_url}/static/{key}",
            key=key,
            content_type=content_type,
            size=len(content),
        )

    def get(self, key: str) -> tuple[bytes, str] | None:
        # Path-traversal defence: reject anything containing separators/parent refs.
        if "/" in key or "\\" in key or key.startswith("."):
            return None
        path = self._root / key
        if not path.is_file():
            return None
        ct, _ = mimetypes.guess_type(path.name)
        if ct is None:
            ct = "application/octet-stream"
        return path.read_bytes(), ct

    def delete(self, key: str) -> bool:
        if "/" in key or "\\" in key or key.startswith("."):
            return False
        path = self._root / key
        if path.is_file():
            path.unlink()
            return True
        return False
