"""Rutas HTTP de identidad temporal del evaluador."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ...api.dependencies import get_identity_service
from ...core.errors import error_response
from .repository import IdentityRepositoryError
from .schemas import EvaluadorCatalogo, EvaluadorIdentificacion, EvaluadorSesion
from .service import IdentityService

router = APIRouter(prefix="/sesion", tags=["Sesión interna"])
UNAVAILABLE = error_response(
    "PostgreSQL no está disponible o el maestro no pudo consultarse.",
    "No se pudo consultar el maestro de evaluadores",
)


@router.post(
    "/evaluador",
    response_model=EvaluadorSesion,
    summary="Resuelve un evaluador activo por DNI",
    description=(
        "Busca el DNI en core.m_evaluador. Es una identificación interna temporal; "
        "todavía no crea tokens ni sustituye la autenticación futura del panel."
    ),
    operation_id="resolverEvaluador",
    responses={
        404: error_response(
            "El DNI no pertenece a un evaluador activo.",
            "El DNI no corresponde a un evaluador activo del maestro",
        ),
        503: UNAVAILABLE,
    },
)
def resolver_evaluador(
    payload: EvaluadorIdentificacion,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> EvaluadorSesion:
    try:
        evaluador = service.resolve_by_dni(payload.dni)
    except IdentityRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if evaluador is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El DNI no corresponde a un evaluador activo del maestro",
        )
    return evaluador


@router.get(
    "/evaluadores",
    response_model=list[EvaluadorCatalogo],
    summary="Lista evaluadores activos del maestro",
    description="Devuelve únicamente evaluadores activos y habilitados en el maestro.",
    operation_id="listarEvaluadores",
    responses={503: UNAVAILABLE},
)
def listar_evaluadores(
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> list[EvaluadorCatalogo]:
    try:
        return service.list_evaluadores()
    except IdentityRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


__all__ = ["router"]
