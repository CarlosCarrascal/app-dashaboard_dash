"""Metadatos estables de OpenAPI para Swagger UI y ReDoc."""

from __future__ import annotations

from .settings import Settings

OPENAPI_TAGS = [
    {
        "name": "Salud",
        "description": "Disponibilidad del proceso y de su conexión a PostgreSQL.",
    },
    {
        "name": "Sesión interna",
        "description": (
            "Resolución temporal del evaluador contra el maestro. No es autenticación "
            "definitiva y no emite JWT; será sustituida al integrar el panel administrativo."
        ),
    },
    {
        "name": "Catálogos",
        "description": "Fundos, módulos y lotes elegibles para la captura de campo.",
    },
    {
        "name": "Evaluaciones",
        "description": (
            "Registro idempotente y consulta de evaluaciones capturadas por la app Flutter."
        ),
    },
]


def openapi_servers(settings: Settings) -> list[dict[str, str]]:
    if settings.public_api_url:
        return [
            {
                "url": settings.public_api_url.rstrip("/"),
                "description": f"Entorno {settings.environment}",
            }
        ]
    return [{"url": "/", "description": f"Servidor actual ({settings.environment})"}]


__all__ = ["OPENAPI_TAGS", "openapi_servers"]
