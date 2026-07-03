"""Liveness/readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Returns 200 + {"status":"ok"} if the service is up."""
    return {"status": "ok"}
