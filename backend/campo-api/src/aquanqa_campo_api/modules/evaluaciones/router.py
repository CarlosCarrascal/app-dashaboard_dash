"""Rutas HTTP de evaluaciones."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status

from ...api.dependencies import get_evaluation_service
from ...core.errors import error_response, validation_error_response
from .repository import (
    EvaluationRepositoryError,
    EvaluatorNotFoundError,
    IdempotencyConflictError,
    LocationNotFoundError,
)
from .rules import EvaluationValidationError
from .schemas import (
    EvaluationCreate,
    EvaluationHistoryPage,
    EvaluationHistoryQuery,
    EvaluationReceipt,
)
from .service import EvaluationService

router = APIRouter(prefix="/evaluaciones", tags=["Evaluaciones"])
EVALUATION_EXAMPLE = {
    "captura_estadios": {
        "summary": "Evaluación de estadios creada por Flutter",
        "value": {
            "id": "11111111-1111-4111-8111-111111111111",
            "module_key": "estadios",
            "fecha": "2026-08-31",
            "lote_id": 12,
            "cortina": 1,
            "hilera": 2,
            "planta": 3,
            "evaluador_dni": "10616663",
            "valores": {"m1_e1": 1, "m1_e2": 2, "m1_e3": 3, "m1_e4": 4, "m1_e5": 5},
        },
    }
}


@router.post(
    "",
    response_model=EvaluationReceipt,
    status_code=status.HTTP_201_CREATED,
    summary="Registra una evaluación y actualiza core",
    description=(
        "Operación idempotente por client_id. El primer envío devuelve 201; un reenvío "
        "idéntico devuelve 200 y status=duplicate; reutilizar el UUID con otro contenido "
        "devuelve 409."
    ),
    operation_id="registrarEvaluacion",
    responses={
        409: error_response(
            "El client_id ya fue usado con contenido diferente.",
            "client_id ya fue utilizado con otro módulo o contenido",
        ),
        422: validation_error_response(
            "La captura o sus referencias de maestro no son válidas.",
            "lote_id no existe o no es elegible para captura",
        ),
        503: error_response(
            "PostgreSQL no está disponible o la transacción falló.",
            "No se pudo guardar la evaluación en PostgreSQL",
        ),
    },
)
def registrar_evaluacion(
    payload: Annotated[EvaluationCreate, Body(openapi_examples=EVALUATION_EXAMPLE)],
    response: Response,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationReceipt:
    try:
        receipt = service.register(payload)
    except (EvaluationValidationError, LocationNotFoundError, EvaluatorNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except IdempotencyConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except EvaluationRepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    if receipt.status == "duplicate":
        response.status_code = status.HTTP_200_OK
    return receipt


@router.get(
    "/historial",
    response_model=EvaluationHistoryPage,
    summary="Lista el historial completo de un evaluador",
    description=(
        "Consulta las evaluaciones históricas y móviles guardadas en las tablas core, "
        "sin duplicar reintentos de la app. Mientras no exista SSO, Flutter envía la "
        "identidad de su sesión; al incorporar JWT se obtendrá del token."
    ),
    operation_id="listarHistorialEvaluaciones",
    responses={
        422: validation_error_response(
            "Faltan filtros de identidad o son inválidos.",
            "se requiere evaluador_id o evaluador_dni",
        ),
        503: error_response(
            "PostgreSQL no está disponible.", "No se pudo consultar el historial"
        ),
    },
)
def listar_historial(
    query: Annotated[EvaluationHistoryQuery, Query()],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationHistoryPage:
    try:
        return service.list_history(query)
    except EvaluatorNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except EvaluationRepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error


@router.get(
    "/{client_id}",
    response_model=EvaluationReceipt,
    summary="Consulta el resultado de una captura local",
    description="Permite a Flutter reconciliar una captura después de un timeout o reintento.",
    operation_id="consultarEvaluacion",
    responses={
        404: error_response(
            "No existe una captura aceptada con ese UUID.",
            "No existe una captura con ese client_id",
        ),
        503: error_response(
            "PostgreSQL no está disponible.", "No se pudo consultar la evaluación"
        ),
    },
)
def consultar_evaluacion(
    client_id: UUID,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationReceipt:
    try:
        receipt = service.find_by_client_id(client_id)
    except EvaluationRepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    if receipt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe una captura con ese client_id",
        )
    return receipt


__all__ = ["router"]
