"""Rutas de salud de la API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ...api.dependencies import get_health_service
from ...core.errors import error_response
from .repository import HealthRepositoryError
from .service import HealthService

router = APIRouter(prefix="/health", tags=["Salud"])


@router.get(
    "/live",
    summary="Comprueba que el proceso está vivo",
    description="No consulta dependencias externas.",
    operation_id="comprobarProcesoVivo",
)
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Comprueba la conexión a PostgreSQL",
    description="Devuelve 200 solo si la API puede ejecutar una consulta mínima en PostgreSQL.",
    operation_id="comprobarPostgresDisponible",
    responses={
        503: error_response(
            "La API está viva, pero PostgreSQL no está disponible.",
            "No se pudo comprobar PostgreSQL",
        )
    },
)
def ready(
    service: Annotated[HealthService, Depends(get_health_service)],
) -> dict[str, str]:
    try:
        return service.ready()
    except HealthRepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error


__all__ = ["router"]
