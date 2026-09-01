"""Contratos de catálogos de ubicación."""

from pydantic import BaseModel, ConfigDict


class FundoCatalogo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    empresa_id: int
    empresa: str
    fundo_id: int
    codigo: str
    alias_operativo: str | None = None


class ModuloCatalogo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    empresa_id: int
    empresa: str
    fundo_id: int
    fundo_codigo: str
    modulo_id: int
    codigo: str


class LoteCatalogo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    empresa_id: int
    empresa: str
    fundo_id: int
    fundo_codigo: str
    modulo_id: int
    modulo_codigo: str
    lote_id: int
    codigo: str
    turno_id: int
    turno: str
    variedad_id: int
    variedad: str
    n_plantas: int


__all__ = ["FundoCatalogo", "LoteCatalogo", "ModuloCatalogo"]
