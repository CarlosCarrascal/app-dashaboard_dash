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
            "administrativa y no emite JWT; la captura móvil mantiene su propio flujo."
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
    {
        "name": "Administración",
        "description": (
            "Lectura paginada de evaluaciones, maestros y cuarentena, más previsualización "
            "de plantillas Excel. Todas las rutas exigen identidad y permisos RBAC; la "
            "previsualización no escribe datos productivos."
        ),
    },
    {
        "name": "Autenticación",
        "description": "Login, renovación y consulta de la sesión administrativa Angular.",
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
