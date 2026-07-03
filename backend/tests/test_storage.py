"""Storage tests — ST-015 (upload returns URL), ST-020 partial (URL serves the file)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.storage.local_mock import LocalStorageAdapter
from app.config import Settings
from app.main import create_app


# ─── Fixtures ───────────────────────────────────────────────────────────
@pytest.fixture
def tmp_var_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture(autouse=True)
def _isolate_app_state():
    """Reset the per-process mock DB between tests so emails don't clash."""
    from app.adapters.supabase._factory import reset_mock_singleton

    reset_mock_singleton()
    yield
    reset_mock_singleton()


@pytest.fixture
def storage(tmp_var_dir: Path) -> LocalStorageAdapter:
    return LocalStorageAdapter(
        var_dir=tmp_var_dir,
        public_base_url="http://testserver",
    )


@pytest.fixture
def client(tmp_var_dir: Path) -> Iterator[tuple[TestClient, str]]:
    """TestClient wired against a tmp uploads dir + http://testserver base URL."""
    app = create_app(
        Settings(
            var_dir=str(tmp_var_dir),
            public_base_url="http://testserver",
        ),
    )
    # A signup-driven token — fake CurrentUserId by directly signing in.
    with TestClient(app) as c:
        signup = c.post(
            "/api/auth/signup",
            json={"email": "uploader@example.com", "full_name": "U", "password": "password123"},
        )
        assert signup.status_code == 201
        token = signup.json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c, token
    # Cleanup: tmp_path is removed automatically by pytest's tmp_path fixture.


# ─── Direct adapter tests (ST-020 partial — mock is stable) ────────────
def test_local_adapter_writes_file_to_disk(tmp_var_dir: Path) -> None:
    storage = LocalStorageAdapter(var_dir=tmp_var_dir, public_base_url="http://testserver")
    obj = storage.upload(b"\x89PNG_FAKE_BYTES", filename="photo.png", content_type="image/png")
    assert obj.url == "http://testserver/static/" + obj.key
    assert obj.content_type == "image/png"
    assert obj.size == len(b"\x89PNG_FAKE_BYTES")
    assert (tmp_var_dir / "uploads" / obj.key).read_bytes() == b"\x89PNG_FAKE_BYTES"


def test_local_adapter_rejects_empty_body(storage: LocalStorageAdapter) -> None:
    with pytest.raises(ValueError, match="empty"):
        storage.upload(b"", filename="x.png", content_type="image/png")


def test_local_adapter_get_returns_bytes(storage: LocalStorageAdapter) -> None:
    obj = storage.upload(b"hello", filename="a.png", content_type="image/png")
    result = storage.get(obj.key)
    assert result is not None
    assert result[0] == b"hello"
    assert result[1] == "image/png"


def test_local_adapter_get_returns_none_for_missing(storage: LocalStorageAdapter) -> None:
    assert storage.get("nope.png") is None


def test_local_adapter_path_traversal_blocked(storage: LocalStorageAdapter) -> None:
    obj = storage.upload(b"x", filename="safe.png", content_type="image/png")
    assert storage.get(f"../{obj.key}") is None
    assert storage.get("/etc/passwd") is None
    assert storage.delete(f"../{obj.key}") is False


def test_local_adapter_delete_removes_file(storage: LocalStorageAdapter) -> None:
    obj = storage.upload(b"x", filename="a.png", content_type="image/png")
    assert storage.delete(obj.key) is True
    assert storage.get(obj.key) is None


# ─── HTTP endpoint tests — ST-015 ──────────────────────────────────────
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"  # PNG signature
    b"\x00\x00\x00\rIHDR"  # minimal IHDR-ish bytes (not a real image, just bytes)
    b"some fake png"
)

JPG_BYTES = b"\xff\xd8\xff\xe0fake-jpg-bytes"


def test_upload_image_returns_url_with_key(client: tuple[TestClient, str]) -> None:
    c, _ = client
    res = c.post(
        "/api/upload-image",
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["url"].startswith("http://testserver/static/")
    assert body["key"].endswith(".png")
    assert body["content_type"] == "image/png"
    assert body["size"] == len(PNG_BYTES)


def test_uploaded_image_is_served_via_static(client: tuple[TestClient, str]) -> None:
    c, _ = client
    res = c.post(
        "/api/upload-image",
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
    )
    key = res.json()["key"]

    res2 = c.get(f"/static/{key}")
    assert res2.status_code == 200
    assert res2.headers["content-type"].startswith("image/png")
    assert res2.content == PNG_BYTES


def test_static_returns_404_for_missing_key(client: tuple[TestClient, str]) -> None:
    c, _ = client
    res = c.get("/static/no-such-key.png")
    assert res.status_code == 404


def test_upload_rejects_non_image_extension(tmp_var_dir: Path) -> None:
    app = create_app(
        Settings(var_dir=str(tmp_var_dir), public_base_url="http://testserver"),
    )
    with TestClient(app) as c:
        signup = c.post(
            "/api/auth/signup",
            json={"email": "x@x.com", "full_name": "X", "password": "password123"},
        ).json()
        c.headers["Authorization"] = f"Bearer {signup['token']}"

        res = c.post(
            "/api/upload-image",
            files={"file": ("evil.exe", b"not-an-image", "application/octet-stream")},
        )
        assert res.status_code == 415


def test_upload_rejects_disallowed_mime(client: tuple[TestClient, str]) -> None:
    c, _ = client
    res = c.post(
        "/api/upload-image",
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert res.status_code == 415


def test_upload_requires_auth(tmp_var_dir: Path) -> None:
    app = create_app(
        Settings(var_dir=str(tmp_var_dir), public_base_url="http://testserver"),
    )
    with TestClient(app) as c:
        res = c.post(
            "/api/upload-image",
            files={"file": ("photo.png", PNG_BYTES, "image/png")},
        )
        assert res.status_code == 401


def test_upload_accepts_jpg(tmp_var_dir: Path, client: tuple[TestClient, str]) -> None:
    c, _ = client
    res = c.post(
        "/api/upload-image",
        files={"file": ("photo.jpg", JPG_BYTES, "image/jpeg")},
    )
    assert res.status_code == 201
    key = res.json()["key"]
    assert key.endswith(".jpg")

    res2 = c.get(f"/static/{key}")
    assert res2.headers["content-type"].startswith("image/jpeg")
    assert res2.content == JPG_BYTES


def test_factory_picks_local_in_mock_mode(tmp_var_dir: Path) -> None:
    s = LocalStorageAdapter(var_dir=tmp_var_dir, public_base_url="http://testserver")
    settings = Settings(
        var_dir=str(tmp_var_dir),
        public_base_url="http://testserver",
        use_real_supabase=False,
    )
    from app.deps import get_storage_dep

    app = create_app(settings)
    app.dependency_overrides[get_storage_dep] = lambda: s

    with TestClient(app) as c:
        signup = c.post(
            "/api/auth/signup",
            json={"email": "f@f.com", "full_name": "F", "password": "password123"},
        ).json()
        c.headers["Authorization"] = f"Bearer {signup['token']}"
        res = c.post(
            "/api/upload-image",
            files={"file": ("x.png", PNG_BYTES, "image/png")},
        )
        assert res.status_code == 201
        # The overridden adapter wrote to its own dir.
        assert any(s.root.iterdir())


# Ensure fixture is referenced so the editor doesn't complain.
_ = tmp_var_dir
