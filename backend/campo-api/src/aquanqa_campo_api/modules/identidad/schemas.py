"""Contratos de identidad temporal del evaluador."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvaluadorIdentificacion(BaseModel):
    """Identificador que usa la app interna para resolver al evaluador real."""

    model_config = ConfigDict(json_schema_extra={"example": {"dni": "10616663"}})
    dni: str = Field(min_length=8, max_length=8)

    @field_validator("dni")
    @classmethod
    def _dni_normalizado(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit():
            raise ValueError("dni debe contener 8 dígitos")
        return value


class EvaluadorCatalogo(BaseModel):
    """Ficha visible del maestro de evaluadores, sin exponer datos técnicos."""

    model_config = ConfigDict(from_attributes=True)
    evaluador_id: int
    dni: str
    nombre: str
    codigo: str | None = None
    zona: str | None = None
    activo: bool = True


class EvaluadorSesion(EvaluadorCatalogo):
    """Identidad resuelta para una sesión interna de captura."""

    rol: Literal["evaluador"] = "evaluador"


__all__ = ["EvaluadorCatalogo", "EvaluadorIdentificacion", "EvaluadorSesion"]
