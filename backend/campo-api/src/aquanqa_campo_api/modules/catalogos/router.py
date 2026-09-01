"""Rutas HTTP de catálogos de ubicación."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...api.dependencies import get_catalog_service
from ...core.errors import error_response
from .repository import CatalogRepositoryError
from .schemas import FundoCatalogo, LoteCatalogo, ModuloCatalogo
from .service import CatalogService

router = APIRouter(prefix="/catalogos", tags=["Catálogos"])
UNAVAILABLE = error_response(
    "PostgreSQL no está disponible o el catálogo no pudo consultarse.",
    "No se pudo leer el catálogo de PostgreSQL",
)


def _unavailable(error: CatalogRepositoryError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))


@router.get(
    "/fundos",
    response_model=list[FundoCatalogo],
    summary="Lista fundos elegibles",
    description="Devuelve los fundos activos que la app puede presentar al evaluador.",
    operation_id="listarFundos",
    responses={503: UNAVAILABLE},
)
def listar_fundos(
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> list[FundoCatalogo]:
    try:
        return service.list_fundos()
    except CatalogRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/modulos",
    response_model=list[ModuloCatalogo],
    summary="Lista módulos por fundo",
    description="Filtra los módulos elegibles por el fundo seleccionado.",
    operation_id="listarModulos",
    responses={503: UNAVAILABLE},
)
def listar_modulos(
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    fundo_id: Annotated[int | None, Query(ge=1, description="ID interno del fundo")] = None,
) -> list[ModuloCatalogo]:
    try:
        return service.list_modulos(fundo_id=fundo_id)
    except CatalogRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/lotes",
    response_model=list[LoteCatalogo],
    summary="Lista lotes por módulo",
    description="Filtra lotes activos, reales y elegibles por el módulo seleccionado.",
    operation_id="listarLotes",
    responses={503: UNAVAILABLE},
)
def listar_lotes(
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    modulo_id: Annotated[int | None, Query(ge=1, description="ID interno del módulo")] = None,
) -> list[LoteCatalogo]:
    try:
        return service.list_lotes(modulo_id=modulo_id)
    except CatalogRepositoryError as error:
        raise _unavailable(error) from error


__all__ = ["router"]
