"""Rutas HTTP de la superficie administrativa del monolito."""

from typing import Annotated

from .schemas import EvaluationCounts
from .weekly_report import WeeklyReport, WeeklyReportQuery

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)

from ...api.dependencies import (
    get_admin_service,
    get_admin_user,
    get_evaluation_service,
    require_permission,
)
from ...core.errors import error_response, validation_error_response
from ..evaluaciones.repository import (
    EvaluationRepositoryError,
    EvaluatorNotFoundError,
    IdempotencyConflictError,
    LocationNotFoundError,
)
from ..evaluaciones.rules import EvaluationValidationError
from ..evaluaciones.schemas import ModuleKey
from ..evaluaciones.service import EvaluationService
from ..seguridad.schemas import AuthUser
from .repository import (
    AdminMutationConflictError,
    AdminMutationError,
    AdminMutationForbiddenError,
    AdminRepositoryError,
    EvaluationNotFoundError,
    ImportPreviewError,
    ImportPreviewNotFoundError,
    ImportStateError,
    QARejectNotFoundError,
)
from .schemas import (
    AdminEvaluationCorrection,
    AdminEvaluationDetail,
    AdminEvaluationPage,
    AdminEvaluationQuery,
    AdminEvaluationSummary,
    AdminLoadPage,
    AdminLoadQuery,
    AdminMasterPage,
    AdminMasterQuery,
    AdminMutation,
    AdminQABulkResolution,
    AdminQAPage,
    AdminQAQuery,
    AdminQAReview,
    AdminQASummary,
    EvaluationCorrectionRequest,
    ImportConfirmRequest,
    ImportPreview,
    ImportResult,
    MasterMutationRequest,
    MasterResource,
    QABulkDuplicateRequest,
    QAReviewRequest,
    UserMutationRequest,
)
from .service import AdminService
from .analytics import AnalyticsQuery, EvaluationTrend, EvaluationAnalytics, ObservationPage
from fastapi.responses import StreamingResponse

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
UNAVAILABLE = error_response(
    "PostgreSQL no está disponible o la consulta administrativa falló.",
    "No se pudo consultar la superficie administrativa",
)
AUTH_RESPONSES = {
    401: error_response(
        "Se requiere una sesión administrativa válida.",
        "Se requiere un token Bearer",
    ),
    403: error_response(
        "La sesión no tiene permiso para el panel administrativo.",
        "El usuario no tiene permiso para abrir el panel administrativo",
    ),
}
router = APIRouter(
    prefix="/admin",
    tags=["Administración"],
    dependencies=[Depends(get_admin_user)],
    responses=AUTH_RESPONSES,
)


def _unavailable(error: AdminRepositoryError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))


@router.get(
    "/evaluaciones",
    response_model=AdminEvaluationPage,
    summary="Lista evaluaciones para administración",
    description=(
        "Consulta server-side las seis familias de evaluación y aplica filtros por ubicación, "
        "evaluador, módulo y fecha. La ruta es de lectura; la autorización RBAC se integra "
        "antes de publicar el panel fuera de la red interna."
    ),
    operation_id="listarEvaluacionesAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:leer"))],
    responses={503: UNAVAILABLE},
)
def listar_evaluaciones_admin(
    query: Annotated[AdminEvaluationQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminEvaluationPage:
    try:
        return service.list_evaluations(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get('/evaluaciones/conteos', response_model=EvaluationCounts,
    dependencies=[Depends(require_permission('admin:evaluaciones:leer'))])
def indicadores_evaluaciones(query: Annotated[AdminEvaluationQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)]) -> EvaluationCounts:
    try:
        return service.evaluation_counts(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get('/evaluaciones/informe-semanal/pptx',
    dependencies=[Depends(require_permission('admin:evaluaciones:leer'))])
def exportar_informe_semanal(query: Annotated[WeeklyReportQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)]):
    from .report_pptx import export_weekly_report
    if query.desde and query.hasta and query.desde > query.hasta:
        raise HTTPException(422, 'Intervalo de fechas inválido')
    try:
        report = service.weekly_report(query)
        if not report.points: raise HTTPException(422, 'No hay datos para exportar')
        return Response(export_weekly_report(report), media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
            headers={'Content-Disposition': f'attachment; filename="evaluaciones-{query.metric}-{report.hasta}.pptx"'})
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get('/evaluaciones/informe-semanal', response_model=WeeklyReport,
    dependencies=[Depends(require_permission('admin:evaluaciones:leer'))])
def informe_semanal(query: Annotated[WeeklyReportQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)]) -> WeeklyReport:
    if query.desde and query.hasta and query.desde > query.hasta:
        raise HTTPException(422, 'Intervalo de fechas inválido')
    try:
        return service.weekly_report(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get("/evaluaciones/analitica/tendencia", response_model=EvaluationTrend,
    dependencies=[Depends(require_permission("admin:evaluaciones:leer"))])
def tendencia_evaluaciones(query: Annotated[AnalyticsQuery, Query()], service: Annotated[AdminService, Depends(get_admin_service)]) -> EvaluationTrend:
    if not query.module_key or not query.desde or not query.hasta or not query.grano:
        raise HTTPException(422, "Selecciona familia, periodo y unidad de origen")
    if query.desde > query.hasta:
        raise HTTPException(422, "Intervalo de fechas inválido")
    if query.weight_min is not None and query.weight_max is not None and query.weight_min > query.weight_max:
        raise HTTPException(422, "Intervalo de peso inválido")
    try:
        return service.evaluation_trend(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get("/evaluaciones/analitica", response_model=EvaluationAnalytics,
    dependencies=[Depends(require_permission("admin:evaluaciones:leer"))])
def analizar_evaluaciones(query: Annotated[AnalyticsQuery, Query()], service: Annotated[AdminService, Depends(get_admin_service)]) -> EvaluationAnalytics:
    if query.module_key is None:
        raise HTTPException(422, "Selecciona una familia de evaluación")
    if query.weight_min is not None and query.weight_max is not None and query.weight_min > query.weight_max:
        raise HTTPException(422, "Intervalo de peso inválido")
    try:
        return service.evaluation_analytics(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get('/evaluaciones/exportar', response_class=StreamingResponse,
    dependencies=[Depends(require_permission('admin:evaluaciones:leer'))])
def exportar_evaluaciones(query: Annotated[AdminEvaluationQuery, Query()], service: Annotated[AdminService, Depends(get_admin_service)]):
    return StreamingResponse(service.export_evaluations(query), media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="evaluaciones.csv"'})


@router.get('/evaluaciones/ficha/{module_key}/{source_id}', response_model=AdminEvaluationDetail,
    dependencies=[Depends(require_permission('admin:evaluaciones:leer'))])
def ficha_evaluacion(module_key: ModuleKey, source_id: int,
    service: Annotated[AdminService, Depends(get_admin_service)], source_table: str = 'ev_evaluacion'):
    try:
        detail = service.get_evaluation(module_key, source_id, source_table)
        if detail is None:
            raise HTTPException(404, 'Evaluación no encontrada')
        data = dict(detail.detalle)
        samples = data.pop('mediciones' if module_key == 'ramas' else 'observaciones', [])
        data['total_observaciones'] = len(samples or [])
        return detail.model_copy(update={'detalle': data})
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get('/evaluaciones/observaciones/{module_key}/{source_id}', response_model=ObservationPage,
    dependencies=[Depends(require_permission('admin:evaluaciones:leer'))])
def observaciones_evaluacion(module_key: ModuleKey, source_id: int,
    service: Annotated[AdminService, Depends(get_admin_service)],
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    source_table: str = 'ev_evaluacion'):
    try:
        detail = service.get_evaluation(module_key, source_id, source_table)
        if detail is None:
            raise HTTPException(404, 'Evaluación no encontrada')
        samples = detail.detalle.get('mediciones' if module_key == 'ramas' else 'observaciones') or []
        return ObservationPage(items=samples[(page-1)*page_size:page*page_size],total=len(samples),page=page,page_size=page_size)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/evaluaciones/resumen",
    response_model=AdminEvaluationSummary,
    summary="Resume las evaluaciones filtradas",
    operation_id="resumirEvaluacionesAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:leer"))],
    responses={503: UNAVAILABLE},
)
def resumir_evaluaciones_admin(
    query: Annotated[AdminEvaluationQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminEvaluationSummary:
    try:
        return service.evaluation_summary(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/evaluaciones/registros",
    response_model=AdminEvaluationPage,
    summary="Lista registros administrativos con grano consistente",
    operation_id="listarRegistrosEvaluacionesAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:leer"))],
    responses={503: UNAVAILABLE},
)
def listar_registros_evaluaciones_admin(
    query: Annotated[AdminEvaluationQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminEvaluationPage:
    """Contrato estable del workspace; la ruta histórica se conserva durante la transición."""
    try:
        return service.list_evaluations(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/evaluaciones/indicadores",
    response_model=AdminEvaluationSummary,
    summary="Calcula indicadores con los mismos filtros y alcances de la grilla",
    operation_id="consultarIndicadoresEvaluacionesAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:leer"))],
    responses={503: UNAVAILABLE},
)
def consultar_indicadores_evaluaciones_admin(
    query: Annotated[AdminEvaluationQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminEvaluationSummary:
    try:
        return service.evaluation_summary(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/evaluaciones/registros/{record_id}",
    response_model=AdminEvaluationDetail,
    summary="Consulta un registro por su identificador administrativo",
    operation_id="consultarRegistroEvaluacionAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:leer"))],
    responses={
        404: error_response("La evaluación no existe.", "Evaluación no encontrada"),
        422: validation_error_response("El identificador no es válido.", "Identificador inválido"),
        503: UNAVAILABLE,
    },
)
def consultar_registro_evaluacion_admin(
    record_id: Annotated[str, Path(min_length=3, max_length=100)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminEvaluationDetail:
    try:
        source_table, raw_id = record_id.rsplit(":", 1)
        source_id = int(raw_id)
        if source_id <= 0:
            raise ValueError
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El identificador debe tener el formato tabla:id",
        ) from error
    module_by_source: dict[str, tuple[ModuleKey, ...]] = {
        "ev_estados": ("estadios",),
        "ev_flores": ("flores",),
        "ev_brotes": ("brotes",),
        "ev_evaluacion": ("estadios", "flores", "brotes", "ramas", "baya", "pesos"),
        "ev_baya_medicion": ("baya",),
        "ev_evaluacion_baya": ("baya", "pesos"),
        "ev_evaluacion_ramas": ("ramas",),
    }
    modules = module_by_source.get(source_table)
    if modules is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La tabla de origen no pertenece a Evaluaciones",
        )
    try:
        detail = next(
            (
                candidate
                for module_key in modules
                if (candidate := service.get_evaluation(module_key, source_id, source_table))
                is not None
            ),
            None,
        )
    except AdminRepositoryError as error:
        raise _unavailable(error) from error
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluación no encontrada",
        )
    return detail


@router.get(
    "/evaluaciones/plantilla",
    summary="Descarga la plantilla Excel de evaluaciones",
    operation_id="descargarPlantillaEvaluacionesAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:leer"))],
    responses={400: validation_error_response("La plantilla no pudo generarse.", "error")},
)
def descargar_plantilla_evaluaciones_admin(
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> Response:
    return Response(
        content=service.template_xlsx(),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="plantilla_evaluaciones.xlsx"'},
    )


@router.post(
    "/evaluaciones/previsualizar",
    response_model=ImportPreview,
    summary="Previsualiza una carga Excel sin escribir datos",
    description=(
        "Valida hasta 5.000 filas contra el contrato canónico de captura. Devuelve errores por "
        "fila y guarda un manifiesto de preview; todavía no escribe las tablas ev_* ni ejecuta "
        "procedimientos ETL."
    ),
    operation_id="previsualizarEvaluacionesAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:cargar"))],
    responses={
        400: validation_error_response("El libro no cumple la plantilla.", "Faltan columnas"),
        413: error_response("El libro supera 10 MB.", "El archivo supera el límite de 10 MB"),
    },
)
async def previsualizar_evaluaciones_admin(
    archivo: Annotated[UploadFile, File(description="Libro .xlsx de evaluaciones")],
    user: Annotated[AuthUser, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> ImportPreview:
    filename = archivo.filename or "evaluaciones.xlsx"
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se admite el formato .xlsx en esta primera versión",
        )
    content = await archivo.read()
    try:
        return service.create_import_preview(content, filename, user.usuario_id)
    except ImportPreviewError as error:
        code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if "10 MB" in str(error)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(error)) from error
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.post(
    "/evaluaciones/cargar",
    response_model=ImportResult,
    summary="Confirma una carga masiva de evaluaciones",
    description=(
        "Confirma un preview por su UUID y SHA-256. El backend recupera las filas validadas, "
        "las guarda en una sola transacción y registra el resultado del manifiesto. Si una fila "
        "no puede persistirse, se revierte todo el lote. Repetir la confirmación es idempotente."
    ),
    operation_id="cargarEvaluacionesAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:cargar"))],
    responses={
        409: error_response(
            "Una fila usa un client_id con contenido diferente.",
            "client_id ya fue utilizado con otro módulo o contenido",
        ),
        422: error_response(
            "Una fila no cumple las reglas del dominio agrícola.",
            "el lote no existe o no es elegible para captura",
        ),
        503: UNAVAILABLE,
    },
)
def cargar_evaluaciones_admin(
    request: ImportConfirmRequest,
    user: Annotated[AuthUser, Depends(get_admin_user)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> ImportResult:
    try:
        manifest = admin_service.claim_import(
            request.preview_id, request.file_sha256, user.usuario_id
        )
    except ImportPreviewNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ImportStateError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except AdminRepositoryError as error:
        raise _unavailable(error) from error
    if manifest.result is not None:
        return manifest.result
    try:
        receipts = service.register_many(manifest.payloads)
    except (
        EvaluationValidationError,
        LocationNotFoundError,
        EvaluatorNotFoundError,
    ) as error:
        admin_service.fail_import(request.preview_id, user.usuario_id, str(error))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except IdempotencyConflictError as error:
        admin_service.fail_import(request.preview_id, user.usuario_id, str(error))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except EvaluationRepositoryError as error:
        admin_service.fail_import(request.preview_id, user.usuario_id, str(error))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    accepted = sum(receipt.status == "accepted" for receipt in receipts)
    duplicates = sum(receipt.status == "duplicate" for receipt in receipts)
    result = ImportResult(
        carga_id=request.preview_id,
        filename=manifest.filename,
        total_rows=len(receipts),
        accepted_rows=accepted,
        duplicate_rows=duplicates,
        receipts=receipts,
        message="Carga confirmada en PostgreSQL de forma atómica.",
    )
    try:
        admin_service.complete_import(request.preview_id, user.usuario_id, result)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error
    return result


@router.get(
    "/evaluaciones/{module_key}/{source_id}",
    response_model=AdminEvaluationDetail,
    summary="Consulta el detalle normalizado de una evaluación",
    operation_id="consultarDetalleEvaluacionAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:leer"))],
    responses={
        404: error_response("La evaluación no existe.", "Evaluación no encontrada"),
        503: UNAVAILABLE,
    },
)
def consultar_detalle_evaluacion_admin(
    module_key: ModuleKey,
    source_id: Annotated[int, Path(gt=0, description="ID de la tabla de origen")],
    service: Annotated[AdminService, Depends(get_admin_service)],
    source_table: str | None = Query(
        default=None,
        description=(
            "Tabla física; obligatorio para distinguir las dos fuentes de baya"
        ),
    ),
) -> AdminEvaluationDetail:
    try:
        detail = service.get_evaluation(module_key, source_id, source_table)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluación no encontrada",
        )
    return detail


@router.patch(
    "/evaluaciones/{module_key}/{source_id}",
    response_model=AdminEvaluationCorrection,
    summary="Corrige una evaluación individual",
    description=(
        "Valida el payload con las reglas del módulo y aplica una mutación allowlisted en una "
        "transacción PostgreSQL. Conserva antes/después, actor, comentario e idempotency_key."
    ),
    operation_id="corregirEvaluacionAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:corregir"))],
    responses={
        404: error_response(
            "La evaluación no existe.", "La evaluación no existe o está fuera de alcance"
        ),
        409: error_response(
            "La operación entra en conflicto.",
            "idempotency_key ya fue utilizado para otro cambio",
        ),
        422: validation_error_response(
            "Los valores no cumplen las reglas del módulo.",
            "La corrección requiere valores",
        ),
        503: UNAVAILABLE,
    },
)
def corregir_evaluacion_admin(
    module_key: ModuleKey,
    source_id: Annotated[int, Path(gt=0)],
    request: EvaluationCorrectionRequest,
    user: Annotated[AuthUser, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminEvaluationCorrection:
    try:
        return service.correct_evaluation(module_key, source_id, request, user.usuario_id)
    except EvaluationNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except AdminMutationForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except AdminMutationConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (AdminMutationError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/maestros/{resource}",
    response_model=AdminMasterPage,
    summary="Lista un maestro administrativo",
    description=(
        "Expone maestros paginados de ubicación, evaluadores, campañas y configuración de "
        "muestreo. La respuesta nunca incluye credenciales."
    ),
    operation_id="listarMaestroAdmin",
    dependencies=[Depends(require_permission("admin:maestros:leer"))],
    responses={503: UNAVAILABLE},
)
def listar_maestro_admin(
    resource: MasterResource,
    query: Annotated[AdminMasterQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminMasterPage:
    try:
        return service.list_master(resource, query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.post(
    "/maestros/{resource}",
    response_model=AdminMutation,
    summary="Crea un registro de maestro",
    operation_id="crearRegistroMaestroAdmin",
    dependencies=[Depends(require_permission("admin:maestros:gestionar"))],
    responses={
        409: error_response("El registro entra en conflicto.", "llave duplicada"),
        422: validation_error_response("El maestro no cumple las reglas.", "nombre es obligatorio"),
        503: UNAVAILABLE,
    },
)
def crear_maestro_admin(
    resource: MasterResource,
    request: MasterMutationRequest,
    user: Annotated[AuthUser, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminMutation:
    try:
        return service.mutate_master(resource, None, request, user.usuario_id)
    except AdminMutationForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except AdminMutationConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (AdminMutationError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.patch(
    "/maestros/{resource}/{resource_id}",
    response_model=AdminMutation,
    summary="Actualiza o desactiva un registro de maestro",
    operation_id="actualizarRegistroMaestroAdmin",
    dependencies=[Depends(require_permission("admin:maestros:gestionar"))],
    responses={
        409: error_response("El registro entra en conflicto.", "llave duplicada"),
        422: validation_error_response("El maestro no cumple las reglas.", "El registro no existe"),
        503: UNAVAILABLE,
    },
)
def actualizar_maestro_admin(
    resource: MasterResource,
    resource_id: Annotated[int, Path(gt=0)],
    request: MasterMutationRequest,
    user: Annotated[AuthUser, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminMutation:
    try:
        return service.mutate_master(resource, resource_id, request, user.usuario_id)
    except AdminMutationForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except AdminMutationConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (AdminMutationError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/roles",
    response_model=AdminMasterPage,
    summary="Lista roles administrativos",
    operation_id="listarRolesAdmin",
    dependencies=[Depends(require_permission("admin:usuarios:gestionar"))],
    responses={503: UNAVAILABLE},
)
def listar_roles_admin(
    query: Annotated[AdminMasterQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminMasterPage:
    try:
        return service.list_roles(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/usuarios",
    response_model=AdminMasterPage,
    summary="Lista usuarios del panel sin exponer hashes",
    operation_id="listarUsuariosAdmin",
    dependencies=[Depends(require_permission("admin:usuarios:gestionar"))],
    responses={503: UNAVAILABLE},
)
def listar_usuarios_admin(
    query: Annotated[AdminMasterQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminMasterPage:
    try:
        return service.list_users(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.post(
    "/usuarios",
    response_model=AdminMutation,
    summary="Crea un usuario del panel",
    description=(
        "Crea una identidad administrativa con un rol existente. La contraseña se transforma "
        "a hash dentro del backend y nunca se incluye en la respuesta ni en la auditoría."
    ),
    operation_id="crearUsuarioAdmin",
    dependencies=[Depends(require_permission("admin:usuarios:gestionar"))],
    responses={
        409: error_response(
            "El usuario ya existe o la operación entra en conflicto.", "llave duplicada"
        ),
        422: validation_error_response(
            "El usuario no cumple las reglas.",
            "Un usuario nuevo requiere email, nombre y rol",
        ),
        503: UNAVAILABLE,
    },
)
def crear_usuario_admin(
    request: UserMutationRequest,
    user: Annotated[AuthUser, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminMutation:
    try:
        return service.mutate_user(None, request, user.usuario_id)
    except AdminMutationForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except AdminMutationConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (AdminMutationError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.patch(
    "/usuarios/{usuario_id}",
    response_model=AdminMutation,
    summary="Actualiza o desactiva un usuario del panel",
    operation_id="actualizarUsuarioAdmin",
    dependencies=[Depends(require_permission("admin:usuarios:gestionar"))],
    responses={
        409: error_response(
            "El usuario ya existe o la operación entra en conflicto.", "llave duplicada"
        ),
        422: validation_error_response(
            "El usuario no cumple las reglas.",
            "La mutación del usuario requiere al menos un campo",
        ),
        503: UNAVAILABLE,
    },
)
def actualizar_usuario_admin(
    usuario_id: Annotated[int, Path(gt=0)],
    request: UserMutationRequest,
    user: Annotated[AuthUser, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminMutation:
    try:
        return service.mutate_user(usuario_id, request, user.usuario_id)
    except AdminMutationForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except AdminMutationConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (AdminMutationError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/cargas",
    response_model=AdminLoadPage,
    summary="Lista el historial de cargas masivas",
    description=(
        "Consulta el manifiesto de cada carga Excel con su hash, usuario, estado y resultado. "
        "Los usuarios no administradores solo ven las cargas que ellos mismos iniciaron."
    ),
    operation_id="listarCargasAdmin",
    dependencies=[Depends(require_permission("admin:evaluaciones:cargar"))],
    responses={503: UNAVAILABLE},
)
def listar_cargas_admin(
    query: Annotated[AdminLoadQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminLoadPage:
    try:
        return service.list_imports(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/qa/resumen",
    response_model=AdminQASummary,
    summary="Resume cuarentena y alertas de calidad",
    operation_id="resumirCalidadAdmin",
    dependencies=[Depends(require_permission("admin:qa:leer"))],
    responses={503: UNAVAILABLE},
)
def resumir_calidad_admin(
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminQASummary:
    try:
        return service.qa_summary()
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.get(
    "/qa/rechazos",
    response_model=AdminQAPage,
    summary="Lista filas de cuarentena",
    operation_id="listarRechazosCalidadAdmin",
    dependencies=[Depends(require_permission("admin:qa:leer"))],
    responses={503: UNAVAILABLE},
)
def listar_rechazos_calidad_admin(
    query: Annotated[AdminQAQuery, Query()],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminQAPage:
    try:
        return service.list_qa(query)
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.post(
    "/qa/duplicados/confirmar",
    response_model=AdminQABulkResolution,
    summary="Confirma duplicados exactos de Evaluaciones",
    description=(
        "Confirma hasta 500 duplicados exactos sin reinsertarlos. La función PostgreSQL exige "
        "simultáneamente permisos de gestión QA y corrección de evaluaciones; cada evidencia "
        "recibe un evento append-only con la misma clave idempotente."
    ),
    operation_id="confirmarDuplicadosCalidadAdmin",
    dependencies=[
        Depends(require_permission("admin:qa:gestionar")),
        Depends(require_permission("admin:evaluaciones:corregir")),
    ],
    responses={
        403: error_response("Faltan permisos de corrección.", "Permisos insuficientes"),
        422: validation_error_response(
            "La selección contiene incidencias incompatibles.",
            "Sólo se permiten duplicados exactos de Evaluaciones",
        ),
        503: UNAVAILABLE,
    },
)
def confirmar_duplicados_calidad_admin(
    request: QABulkDuplicateRequest,
    user: Annotated[AuthUser, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminQABulkResolution:
    try:
        return service.confirm_qa_duplicates(request, user.usuario_id)
    except AdminMutationForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except AdminMutationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


@router.patch(
    "/qa/rechazos/{rechazo_id}/revision",
    response_model=AdminQAReview,
    summary="Registra una decisión sobre un rechazo",
    description=(
        "Agrega un evento de revisión a la cuarentena. La fila original de qua.rechazos no se "
        "modifica y el historial conserva usuario, estado, comentario y fecha."
    ),
    operation_id="revisarRechazoCalidadAdmin",
    dependencies=[Depends(require_permission("admin:qa:gestionar"))],
    responses={
        404: error_response("La incidencia no existe.", "La incidencia de calidad no existe"),
        503: UNAVAILABLE,
    },
)
def revisar_rechazo_calidad_admin(
    rechazo_id: Annotated[int, Path(gt=0)],
    request: QAReviewRequest,
    user: Annotated[AuthUser, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminQAReview:
    try:
        return service.review_qa(rechazo_id, request, user.usuario_id)
    except QARejectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except AdminMutationForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except AdminMutationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except AdminRepositoryError as error:
        raise _unavailable(error) from error


__all__ = ["router"]
