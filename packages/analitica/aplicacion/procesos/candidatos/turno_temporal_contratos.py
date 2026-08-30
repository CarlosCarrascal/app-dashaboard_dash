"""Contratos y primitivas compartidas del candidato de turno temporal."""

from __future__ import annotations

from dataclasses import dataclass

from ....dominio.compartido import lunes_semana

CLAVE_FORECAST = [
    "evaluation_contract_id",
    "campania",
    "modelo",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "lote_id",
]

CLAVE_UNIVERSO = [
    "evaluation_contract_id",
    "campania",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "lote_id",
]


@dataclass(frozen=True)
class ConfiguracionTurnoTemporal:
    """Configuración pequeña y acotada para screening rápido."""

    peso_calendario: float = 0.50
    dispersion_semanas: float = 0.85
    desplazamiento_max_semanas: int = 2
    semanas_minimas_desplazamiento: int = 6
    penalizacion_desplazamiento: float = 0.015

    def __post_init__(self) -> None:
        if not 0 <= self.peso_calendario <= 1:
            raise ValueError("peso_calendario debe estar entre cero y uno")
        if self.dispersion_semanas <= 0:
            raise ValueError("dispersion_semanas debe ser positiva")
        if self.desplazamiento_max_semanas < 0:
            raise ValueError("desplazamiento_max_semanas no puede ser negativo")
        if self.semanas_minimas_desplazamiento < 2:
            raise ValueError("se requieren al menos dos semanas para desplazar")


_semana_inicio = lunes_semana


__all__ = ["CLAVE_FORECAST", "CLAVE_UNIVERSO", "ConfiguracionTurnoTemporal"]
