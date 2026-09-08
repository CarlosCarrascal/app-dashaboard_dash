"""Contratos de entrada y salida de evaluaciones."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

ModuleKey = Literal["estadios", "flores", "baya", "pesos", "brotes", "ramas"]
ReceiptStatus = Literal["accepted", "duplicate"]


def _entero(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("debe ser un entero")
    if isinstance(value, str) and not value.strip():
        return None
    try:
        numero = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError("debe ser un entero") from None
    if not numero.is_finite() or numero != numero.to_integral_value():
        raise ValueError("debe ser un entero")
    return int(numero)


def _texto(value: Any) -> str | None:
    if value is None:
        return None
    resultado = str(value).strip()
    return resultado or None


class EvaluationCreate(BaseModel):
    """Entrada canónica y compatible para una evaluación de campo."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "client_id": "11111111-1111-4111-8111-111111111111",
                "module_key": "estadios",
                "fecha": "2026-08-31",
                "lote_id": 12,
                "cortina": 1,
                "hilera": 2,
                "planta": 3,
                "evaluador_dni": "10616663",
                "valores": {"m1_e1": 1, "m1_e2": 2, "m1_e3": 3},
            }
        },
    )

    client_id: UUID = Field(validation_alias=AliasChoices("client_id", "id"))
    module_key: ModuleKey
    fecha: date = Field(validation_alias=AliasChoices("fecha", "fecha_evaluacion"))
    captured_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("captured_at", "created_at"),
    )
    lote_id: int | None = None
    fundo: str | None = None
    modulo: str | None = None
    lote: str | None = None
    cortina: int | None
    hilera: int | None
    planta: int | None
    evaluador: str | None = None
    evaluador_id: int | None = None
    evaluador_dni: str | None = Field(
        default=None,
        validation_alias=AliasChoices("evaluador_dni", "dni"),
    )
    item: str | None = None
    piso: str | None = None
    hora: time | None = None
    valores: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("valores", "data"),
    )

    @field_validator("fecha", mode="before")
    @classmethod
    def _fecha_desde_iso(cls, value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            texto = value.strip()
            try:
                return datetime.fromisoformat(texto.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    return date.fromisoformat(texto)
                except ValueError:
                    pass
        raise ValueError("fecha debe ser una fecha ISO 8601 válida")

    @field_validator("lote_id", "cortina", "hilera", "planta", "evaluador_id", mode="before")
    @classmethod
    def _enteros_desde_flutter(cls, value: Any) -> int | None:
        return _entero(value)

    @field_validator("fundo", "modulo", "lote", "evaluador", "evaluador_dni", "item", "piso")
    @classmethod
    def _normalizar_textos(cls, value: Any) -> str | None:
        return _texto(value)

    @field_validator("valores", mode="before")
    @classmethod
    def _mapa_de_valores(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("valores/data debe ser un objeto JSON")
        return value

    @model_validator(mode="after")
    def _validar_identidad_minima(self) -> EvaluationCreate:
        for nombre in ("cortina", "hilera", "planta"):
            if getattr(self, nombre) is None or getattr(self, nombre) <= 0:
                raise ValueError(f"{nombre} debe ser un entero positivo")
            if getattr(self, nombre) > 32767:
                raise ValueError(f"{nombre} supera el máximo permitido por PostgreSQL")
        if self.lote_id is not None and self.lote_id <= 0:
            raise ValueError("lote_id debe ser positivo")
        if self.lote_id is None and not (self.fundo and self.modulo and self.lote):
            raise ValueError("se requiere lote_id o el conjunto fundo, modulo y lote")
        if self.evaluador_id is not None and self.evaluador_id <= 0:
            raise ValueError("evaluador_id debe ser positivo")
        if self.evaluador_id is None and not self.evaluador_dni:
            raise ValueError("se requiere evaluador_id o evaluador_dni")
        return self


class EvaluationPatch(EvaluationCreate):
    """Contrato completo para editar una evaluación móvil ya aceptada."""

    updated_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("updated_at", "actualizado_en"),
        description=(
            "Instante local de modificación. El backend conserva la captura original y "
            "registra su propio actualizado_en."
        ),
    )


class EvaluationReceipt(BaseModel):
    client_id: UUID
    evaluation_id: int
    module_key: ModuleKey
    status: ReceiptStatus
    received_at: datetime


class EvaluationHistoryQuery(BaseModel):
    """Filtros temporales; la identidad vendrá del token cuando exista SSO."""

    model_config = ConfigDict(extra="forbid")

    evaluador_id: int | None = Field(default=None, gt=0)
    evaluador_dni: str | None = Field(default=None, min_length=1, max_length=32)
    module_key: ModuleKey | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    @field_validator("evaluador_dni")
    @classmethod
    def _normalizar_dni(cls, value: str | None) -> str | None:
        return _texto(value)

    @model_validator(mode="after")
    def _requiere_identidad(self) -> EvaluationHistoryQuery:
        if self.evaluador_id is None and self.evaluador_dni is None:
            raise ValueError("se requiere evaluador_id o evaluador_dni")
        return self


class EvaluationHistoryItem(BaseModel):
    id: UUID
    module_key: ModuleKey
    fecha: date
    captured_at: datetime
    evaluador: str = ""
    evaluador_id: int | None = None
    evaluador_dni: str = ""
    lote_id: int | None = None
    fundo: str = ""
    modulo: str = ""
    lote: str = ""
    cortina: int
    hilera: int
    planta: int
    valores: dict[str, Any] = Field(default_factory=dict)


class EvaluationHistoryPage(BaseModel):
    items: list[EvaluationHistoryItem]
    has_more: bool
    next_offset: int | None = None


__all__ = [
    "EvaluationCreate",
    "EvaluationPatch",
    "EvaluationHistoryItem",
    "EvaluationHistoryPage",
    "EvaluationHistoryQuery",
    "EvaluationReceipt",
    "ModuleKey",
]
