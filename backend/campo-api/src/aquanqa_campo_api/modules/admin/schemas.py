"""Contratos HTTP de la superficie administrativa."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..evaluaciones.schemas import EvaluationCreate, EvaluationReceipt, ModuleKey
from ..seguridad.schemas import AccessScope

QAReviewState = Literal["pendiente", "aceptado", "descartado", "corregir"]
LoadState = Literal["pending_confirmation", "processing", "accepted", "failed"]

MasterResource = Literal[
    "empresas",
    "fundos",
    "modulos",
    "lotes",
    "evaluadores",
    "campanias",
    "variedades",
    "turnos",
    "muestreo",
]
EvaluationSourceTable = Literal[
    "ev_evaluacion",
    "ev_estados",
    "ev_flores",
    "ev_brotes",
    "ev_baya_medicion",
    "ev_evaluacion_baya",
    "ev_evaluacion_ramas",
]
EvaluationSort = Literal[
    "captured_at", "fecha", "module_key", "empresa", "fundo", "modulo", "lote", "evaluador"
]


class AdminEvaluationQuery(BaseModel):
    """Filtros server-side para la grilla de evaluaciones."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    search: str | None = Field(default=None, max_length=120)
    module_key: ModuleKey | None = None
    empresa_id: int | None = Field(default=None, gt=0)
    fundo_id: int | None = Field(default=None, gt=0)
    modulo_id: int | None = Field(default=None, gt=0)
    lote_id: int | None = Field(default=None, gt=0)
    evaluador_id: int | None = Field(default=None, gt=0)
    desde: date | None = None
    hasta: date | None = None
    grano: str | None = Field(default=None, max_length=80)
    piso: str | None = Field(default=None, max_length=80)
    estado: str | None = Field(default=None, max_length=30)
    sort_by: EvaluationSort = "captured_at"
    sort_dir: Literal["asc", "desc"] = "desc"

    @field_validator("search")
    @classmethod
    def normalize_search(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None

    @model_validator(mode="after")
    def validate_date_range(self) -> AdminEvaluationQuery:
        if self.desde and self.hasta and self.desde > self.hasta:
            raise ValueError("desde no puede ser posterior a hasta")
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class AdminMasterQuery(BaseModel):
    """Paginación y filtros comunes para los maestros."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)
    search: str | None = Field(default=None, max_length=120)
    activo: bool | None = None
    empresa_id: int | None = Field(default=None, gt=0)
    fundo_id: int | None = Field(default=None, gt=0)
    modulo_id: int | None = Field(default=None, gt=0)

    @field_validator("search")
    @classmethod
    def normalize_search(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class AdminLoadQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
    search: str | None = Field(default=None, max_length=120)
    estado: LoadState | None = None

    @field_validator("search")
    @classmethod
    def normalize_search(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class AdminQAQuery(BaseModel):
    """Filtros para incidencias de cuarentena."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    search: str | None = Field(default=None, max_length=120)
    motivo: str | None = Field(default=None, max_length=120)
    tabla_origen: str | None = Field(default=None, max_length=120)
    hallazgo: str | None = Field(default=None, max_length=80)
    excede_umbral: bool | None = None
    estado_revision: QAReviewState | None = None

    @field_validator("search", "motivo", "tabla_origen", "hallazgo")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PageInfo(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class AdminEvaluationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_table: str
    source_id: int
    module_key: ModuleKey
    tipo: str | None = None
    origen: str | None = None
    fecha: date
    captured_at: datetime | None = None
    lote_id: int | None = None
    empresa: str = ""
    fundo: str = ""
    modulo: str = ""
    lote: str = ""
    variedad: str = ""
    evaluador_id: int | None = None
    evaluador: str = ""
    evaluador_dni: str = ""
    detalle: dict[str, Any] = Field(default_factory=dict)


class AdminEvaluationPage(BaseModel):
    items: list[AdminEvaluationItem]
    meta: PageInfo


class AdminEvaluationIndicatorValues(BaseModel):
    """Indicadores tipados; cada familia completa únicamente sus magnitudes aplicables."""

    e1: int | None = None
    e2: int | None = None
    e3: int | None = None
    e4: int | None = None
    e5: int | None = None
    flores: int | None = None
    cuajos: int | None = None
    yemas_abiertas: int | None = None
    yemas_por_abrir: int | None = None
    yemas_muertas: int | None = None
    brotes_tiernos: int | None = None
    brotes: int | None = None
    piso_1: int | None = None
    piso_2: int | None = None
    piso_3: int | None = None
    ramas_menor_5mm: int | None = None
    ramas_mayor_5mm: int | None = None
    diametro_promedio_mm: float | None = None
    peso_promedio_g: float | None = None
    sospechosas: int | None = None


class AdminEvaluationFamilySummary(BaseModel):
    module_key: ModuleKey
    total: int
    muestras: int = 0
    lotes: int = 0
    evaluadores: int = 0
    desde: date | None = None
    hasta: date | None = None
    ultima_captura: datetime | None = None
    indicadores: AdminEvaluationIndicatorValues = Field(
        default_factory=AdminEvaluationIndicatorValues
    )


class AdminEvaluationSummary(BaseModel):
    total: int
    por_modulo: list[AdminEvaluationFamilySummary]
    evaluadores: int
    lotes: int
    desde: date | None = None
    hasta: date | None = None
    ultima_captura: datetime | None = None


class AdminEvaluationDetail(AdminEvaluationItem):
    """Detalle normalizado; mantiene el mismo contrato que una fila de grilla."""


class EvaluationCorrectionRequest(BaseModel):
    """Valores completos de una corrección individual, no un parche SQL arbitrario."""

    model_config = ConfigDict(extra="forbid")

    source_table: EvaluationSourceTable
    fecha: date
    lote_id: int = Field(gt=0)
    cortina: int | None = Field(default=None, gt=0, le=32767)
    hilera: int | None = Field(default=None, gt=0, le=32767)
    planta: int | None = Field(default=None, gt=0, le=32767)
    nro_muestra: int | None = Field(default=None, gt=0, le=32767)
    evaluador_id: int | None = Field(default=None, gt=0)
    item: str | None = Field(default=None, max_length=120)
    piso: str | None = Field(default=None, max_length=40)
    hora: str | None = Field(default=None, max_length=16)
    valores: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: UUID
    comentario: str | None = Field(default=None, max_length=2000)

    @field_validator("item", "piso", "hora", "comentario")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None

    @model_validator(mode="after")
    def validate_identity(self) -> EvaluationCorrectionRequest:
        if self.source_table == "ev_baya_medicion":
            if self.cortina is None or self.hilera is None or self.nro_muestra is None:
                raise ValueError(
                    "Una medición de baya requiere cortina, hilera y nro_muestra"
                )
        elif any(value is None for value in (self.cortina, self.hilera, self.planta)):
            raise ValueError("La corrección requiere cortina, hilera y planta")
        return self


class AdminMutation(BaseModel):
    """Resultado auditable de una mutación administrativa."""

    cambio_id: int
    recurso: str
    recurso_id: int
    accion: Literal["crear", "actualizar", "desactivar", "corregir"]
    antes: dict[str, Any] | None = None
    despues: dict[str, Any]
    idempotency_key: UUID
    mensaje: str


class AdminEvaluationCorrection(BaseModel):
    mutation: AdminMutation
    evaluacion: AdminEvaluationDetail


class MasterMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valores: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: UUID
    comentario: str | None = Field(default=None, max_length=2000)

    @field_validator("comentario")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


UserRole = Literal["admin", "agronomo", "evaluador", "lectura"]


class UserMutationRequest(BaseModel):
    """Datos editables de una identidad; la contraseña nunca viaja como hash al cliente."""

    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, min_length=3, max_length=255)
    nombre: str | None = Field(default=None, max_length=160)
    rol: UserRole | None = None
    evaluador_id: int | None = Field(default=None, gt=0)
    activo: bool | None = None
    password: str | None = Field(default=None, min_length=1, max_length=256)
    alcances: list[AccessScope] | None = Field(default=None, max_length=100)
    idempotency_key: UUID
    comentario: str | None = Field(default=None, max_length=2000)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        value = value.strip().casefold() if value else None
        return value or None

    @field_validator("nombre", "comentario")
    @classmethod
    def normalize_user_text(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


class AdminMasterPage(BaseModel):
    items: list[dict[str, Any]]
    meta: PageInfo


class AdminLoadItem(BaseModel):
    carga_id: UUID
    archivo_nombre: str
    archivo_sha256: str
    usuario_id: int
    usuario: str
    estado: LoadState
    filas_total: int
    filas_validas: int
    filas_invalidas: int
    filas_aceptadas: int
    filas_duplicadas: int
    error: str | None = None
    creado_en: datetime
    iniciado_en: datetime | None = None
    finalizado_en: datetime | None = None


class AdminLoadPage(BaseModel):
    items: list[AdminLoadItem]
    meta: PageInfo


class AdminQASummaryItem(BaseModel):
    motivo: str
    hallazgo: str | None = None
    filas: int
    tope: int | None = None
    excede_umbral: bool = False
    tablas: str = ""
    explicacion: str | None = None


class AdminQASummary(BaseModel):
    total_rechazos: int
    motivos: list[AdminQASummaryItem]
    alertas: int


class AdminQARejectItem(BaseModel):
    rechazo_id: int
    tabla_origen: str
    tabla_destino: str | None = None
    motivo: str
    hallazgo: str | None = None
    detalle: str | None = None
    fila: dict[str, Any]
    cargado_en: datetime
    source_snapshot_id: int | None = None
    migracion_run_id: int | None = None
    bloque_ejecucion_id: int | None = None
    excede_umbral: bool = False
    estado_revision: QAReviewState = "pendiente"
    comentario_revision: str | None = None
    revisado_en: datetime | None = None
    revisado_por: int | None = None


class QAReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: Literal["aceptado", "descartado", "corregir"]
    idempotency_key: UUID
    comentario: str | None = Field(default=None, max_length=2000)

    @field_validator("comentario")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


class AdminQAReview(BaseModel):
    rechazo_id: int
    estado_revision: QAReviewState
    idempotency_key: UUID
    comentario_revision: str | None = None
    revisado_en: datetime
    revisado_por: int


class QABulkDuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rechazo_ids: list[int] = Field(min_length=1, max_length=500)
    idempotency_key: UUID
    comentario: str | None = Field(default=None, max_length=2000)

    @field_validator("rechazo_ids")
    @classmethod
    def validate_unique_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value) or len(set(value)) != len(value):
            raise ValueError("rechazo_ids debe contener identificadores positivos y distintos")
        return value


class AdminQABulkResolution(BaseModel):
    procesados: int
    idempotency_key: UUID
    accion: Literal["confirmar_duplicados"] = "confirmar_duplicados"


class ImportConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_id: UUID
    file_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("file_sha256")
    @classmethod
    def normalize_hash(cls, value: str) -> str:
        value = value.strip().lower()
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("file_sha256 debe ser un SHA-256 hexadecimal")
        return value


class ImportResult(BaseModel):
    carga_id: UUID
    filename: str
    total_rows: int
    accepted_rows: int
    duplicate_rows: int
    receipts: list[EvaluationReceipt]
    atomic: bool = True
    message: str


class ImportManifest(BaseModel):
    carga_id: UUID
    filename: str
    file_sha256: str
    estado: Literal["pending_confirmation", "processing", "accepted", "failed"]
    payloads: list[EvaluationCreate] = Field(default_factory=list)
    total_rows: int
    valid_rows: int
    invalid_rows: int
    result: ImportResult | None = None
    error: str | None = None


class AdminQAPage(BaseModel):
    items: list[AdminQARejectItem]
    meta: PageInfo


class ImportPreviewRow(BaseModel):
    row: int
    valid: bool
    error: str | None = None
    payload: dict[str, Any] | None = None


class ImportPreview(BaseModel):
    preview_id: UUID
    file_sha256: str
    filename: str
    sheet: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[ImportPreviewRow]
    message: str
    state: Literal["pending_confirmation"] = "pending_confirmation"


__all__ = [
    "AdminEvaluationDetail",
    "AdminEvaluationCorrection",
    "AdminEvaluationItem",
    "AdminEvaluationPage",
    "AdminEvaluationQuery",
    "AdminEvaluationSummary",
    "AdminMasterPage",
    "AdminMutation",
    "AdminMasterQuery",
    "AdminLoadItem",
    "AdminLoadPage",
    "AdminLoadQuery",
    "AdminQAQuery",
    "AdminQAPage",
    "AdminQARejectItem",
    "AdminQASummary",
    "AdminQASummaryItem",
    "AdminQAReview",
    "AdminQABulkResolution",
    "ImportConfirmRequest",
    "ImportManifest",
    "ImportResult",
    "ImportPreview",
    "ImportPreviewRow",
    "MasterResource",
    "MasterMutationRequest",
    "UserMutationRequest",
    "UserRole",
    "EvaluationCorrectionRequest",
    "EvaluationSourceTable",
    "PageInfo",
    "QAReviewRequest",
    "QABulkDuplicateRequest",
    "QAReviewState",
    "LoadState",
]
