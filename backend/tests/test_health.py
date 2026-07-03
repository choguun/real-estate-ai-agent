"""Health endpoint tests — ST-001."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_returns_app_metadata(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Real Estate AI Agent"
    assert body["version"] == "0.1.0"


def test_health_does_not_require_auth(client: TestClient) -> None:
    # No Authorization header sent; health must still respond 200.
    response = client.get("/health")
    assert response.status_code == 200
