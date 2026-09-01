"""Composición de la aplicación FastAPI de captura interna de campo."""

from __future__ import annotations

from fastapi import FastAPI

from .api.v1.router import router as api_v1_router
from .core.logging import configure_logging
from .core.openapi import OPENAPI_TAGS, openapi_servers
from .core.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title="Aqu Anqa · API de campo",
        version="0.1.0",
        description=(
            "API interna para registrar evaluaciones de app-campo en PostgreSQL. "
            "El plan de distribución y el panel admin quedan fuera de esta primera versión."
        ),
        openapi_tags=OPENAPI_TAGS,
        servers=openapi_servers(settings),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    application.include_router(api_v1_router, prefix=settings.api_prefix)
    return application


app = create_app()


__all__ = ["app", "create_app"]
