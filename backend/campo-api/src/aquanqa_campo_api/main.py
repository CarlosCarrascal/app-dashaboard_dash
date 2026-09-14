"""Composición de la aplicación FastAPI de captura interna de campo."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.v1.router import router as api_v1_router
from .api.analytics_compression import AnalyticsCompressionMiddleware
from .core.logging import configure_logging
from .core.openapi import OPENAPI_TAGS, openapi_servers
from .core.settings import Settings, get_settings
from .infrastructure.postgres.connection import PostgresConnectionFactory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    connections = PostgresConnectionFactory(
        settings.database_url,
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        timeout=settings.database_pool_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        connections.open()
        try:
            yield
        finally:
            connections.close()

    application = FastAPI(
        title="Aqu Anqa · API de campo",
        version="0.1.0",
        description=(
            "API interna para registrar evaluaciones de app-campo en PostgreSQL. "
            "Incluye autenticación administrativa y lectura paginada para el panel Angular."
        ),
        openapi_tags=OPENAPI_TAGS,
        servers=openapi_servers(settings),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.state.postgres_connections = connections
    application.state.settings = settings
    application.add_middleware(AnalyticsCompressionMiddleware, api_prefix=settings.api_prefix)
    application.include_router(api_v1_router, prefix=settings.api_prefix)
    return application


app = create_app()


__all__ = ["app", "create_app"]
