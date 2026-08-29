"""Componentes internos para el preflight de candidatos.

La superficie histórica continúa en :mod:`analitica.proyeccion.candidate_preflight`.
Este paquete solo separa responsabilidades; no publica ni persiste candidatos.
"""

from .cache import (
    CacheCandidate,
    clave_cache_candidate,
    escribir_json_reproducible,
    json_reproducible,
    obtener_o_construir_cache,
    sha256_dataframe,
)
from .contratos import (
    CLAVES_EVALUACION,
    DATOS_SNAPSHOT_SCHEMA,
    EXIT_CONTRACT_REJECTED,
    EXIT_EXECUTION_ERROR,
    EXIT_OK,
    EXIT_QUALITY_REJECTED,
    HORIZONTES_MICRO,
    ContratoBaselines,
    UmbralesPreflight,
)
from .fuentes import (
    cargar_baselines_por_run,
    cargar_contrato_baselines,
    seleccionar_emisiones_micro_desde_fuente,
)
from .preflight import evaluar_preflight
from .snapshot import cargar_o_construir_snapshot_datos, clonar_datos_proyeccion

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
    "CacheCandidate",
    "cargar_o_construir_snapshot_datos",
    "clonar_datos_proyeccion",
    "clave_cache_candidate",
    "cargar_baselines_por_run",
    "cargar_contrato_baselines",
    "evaluar_preflight",
    "escribir_json_reproducible",
    "json_reproducible",
    "obtener_o_construir_cache",
    "seleccionar_emisiones_micro_desde_fuente",
    "sha256_dataframe",
]
