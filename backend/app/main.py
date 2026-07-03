"""FastAPI application factory.

Single source of truth for app construction. Mock-first: every adapter is
selected at startup by `get_settings()` flags. To swap mock → real
services, change env vars — no code edits required.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.routers.ai import router as ai_router
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.health import router as health_router
from app.routers.leads import router as leads_router
from app.routers.line_webhook import router as line_webhook_router
from app.routers.listings import router as listings_router
from app.routers.messages import router as messages_router
from app.routers.properties import router as properties_router
from app.routers.storage import router as storage_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "Starting %s v%s [%s] mocks=%s",
        settings.app_name,
        settings.app_version,
        settings.env,
        settings.use_mocks,
    )
    yield
    logger.info("Shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Tests pass a custom Settings for isolation."""
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", tags=["meta"])
    def root() -> dict[str, str]:
        return {"service": settings.app_name, "version": settings.app_version}

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(properties_router)
    app.include_router(storage_router)
    app.include_router(ai_router)
    app.include_router(listings_router)
    app.include_router(line_webhook_router)
    app.include_router(leads_router)
    app.include_router(messages_router)
    app.include_router(dashboard_router)
    return app


app = create_app()
