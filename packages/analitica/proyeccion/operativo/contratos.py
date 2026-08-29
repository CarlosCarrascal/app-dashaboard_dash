"""Contratos y constantes compartidos por la operación de libros."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MODELO_OPERATIVO_ACTUAL = "ModeloOperativoActual_v1"
CLAVES_CORRIDA = ["Modulo", "Turno", "Lote", "Paña", "Fechaini", "FeCos"]
CAMPOS_NUMERICOS = ["Frtutos", "Peso", "Rend", "Kg", "Frutototal"]


@dataclass
class ResultadoValidacionOperativa:
    """Resultado serializable de la comparación entre libro, Panel y BDProy."""

    archivo: str
    sha256: str
    modelo: str = MODELO_OPERATIVO_ACTUAL
    estado: str = "no_evaluable"
    filas_fuente: int = 0
    filas_motor: int = 0
    max_diferencia: dict[str, float] = field(default_factory=dict)
    diferencias_filas: int = 0
    advertencias: list[str] = field(default_factory=list)
    metadatos: dict[str, Any] = field(default_factory=dict)

    @property
    def valido(self) -> bool:
        return self.estado == "validado"


__all__ = [
    "CAMPOS_NUMERICOS",
    "CLAVES_CORRIDA",
    "MODELO_OPERATIVO_ACTUAL",
    "ResultadoValidacionOperativa",
]
