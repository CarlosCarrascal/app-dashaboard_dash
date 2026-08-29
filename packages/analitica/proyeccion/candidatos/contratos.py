"""Constantes y contratos inmutables del preflight de candidatos."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

EXIT_OK = 0
EXIT_CONTRACT_REJECTED = 2
EXIT_QUALITY_REJECTED = 3
EXIT_EXECUTION_ERROR = 4

CLAVES_EVALUACION = (
    "campania",
    "lote_id",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
)
HORIZONTES_MICRO = (1, 2, 4, 6)
DATOS_SNAPSHOT_SCHEMA = "datos-proyeccion-parquet-v1"


@dataclass(frozen=True)
class UmbralesPreflight:
    wape_max: float = 1.0
    sesgo_abs_max: float = 0.25
    cobertura_volumen_min: float = 0.95
    cobertura_lotes_min: float = 0.90
    deterioro_macro_max: float = 0.10
    deterioro_horizonte_max: float = 0.20
    falsos_ceros_volumen_max: float = 0.02


@dataclass(frozen=True)
class ContratoBaselines:
    """Release aprobada que fija el universo y el cierre del preflight."""

    evaluation_contract_id: int
    campania: str
    cerrado_hasta: pd.Timestamp
    keyset_sha256: str
    closed_calendar_sha256: str
    run_ids: dict[str, int]
    source_hashes: dict[str, str]


__all__ = [
    "CLAVES_EVALUACION",
    "DATOS_SNAPSHOT_SCHEMA",
    "EXIT_OK",
    "EXIT_CONTRACT_REJECTED",
    "EXIT_QUALITY_REJECTED",
    "EXIT_EXECUTION_ERROR",
    "HORIZONTES_MICRO",
    "UmbralesPreflight",
    "ContratoBaselines",
]
