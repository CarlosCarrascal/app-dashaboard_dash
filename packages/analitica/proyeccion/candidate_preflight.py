"""Fachada compatible para el preflight reproducible de challengers.

La implementación vive en ``proyeccion.candidatos`` y se mantiene este módulo
porque es la ruta histórica usada por scripts, tests y consumidores externos.
Las reexportaciones conservan nombres, firmas, errores y contratos de salida.
"""

from __future__ import annotations

from . import candidatos as _candidatos
from .candidatos import cache as _cache
from .candidatos import fuentes as _fuentes
from .candidatos import preflight as _preflight

CLAVES_EVALUACION = _candidatos.CLAVES_EVALUACION
DATOS_SNAPSHOT_SCHEMA = _candidatos.DATOS_SNAPSHOT_SCHEMA
EXIT_CONTRACT_REJECTED = _candidatos.EXIT_CONTRACT_REJECTED
EXIT_EXECUTION_ERROR = _candidatos.EXIT_EXECUTION_ERROR
EXIT_OK = _candidatos.EXIT_OK
EXIT_QUALITY_REJECTED = _candidatos.EXIT_QUALITY_REJECTED
HORIZONTES_MICRO = _candidatos.HORIZONTES_MICRO
CacheCandidate = _candidatos.CacheCandidate
ContratoBaselines = _candidatos.ContratoBaselines
UmbralesPreflight = _candidatos.UmbralesPreflight
cargar_baselines_por_run = _candidatos.cargar_baselines_por_run
cargar_contrato_baselines = _candidatos.cargar_contrato_baselines
cargar_o_construir_snapshot_datos = _candidatos.cargar_o_construir_snapshot_datos
clonar_datos_proyeccion = _candidatos.clonar_datos_proyeccion
clave_cache_candidate = _candidatos.clave_cache_candidate
escribir_json_reproducible = _candidatos.escribir_json_reproducible
evaluar_preflight = _candidatos.evaluar_preflight
json_reproducible = _candidatos.json_reproducible
obtener_o_construir_cache = _candidatos.obtener_o_construir_cache
seleccionar_emisiones_micro_desde_fuente = _candidatos.seleccionar_emisiones_micro_desde_fuente
sha256_dataframe = _candidatos.sha256_dataframe

# Atributos privados/auxiliares conservados por compatibilidad con consumidores
# internos que históricamente inspeccionaban la fachada.
_limpio_json = _cache._limpio_json
conexion_postgres = _fuentes.conexion_postgres
_metricas_modelo = _preflight._metricas_modelo
_normalizar_predicciones = _preflight._normalizar_predicciones
_semana_inicio = _preflight._semana_inicio

__all__ = [
    "EXIT_OK",
    "EXIT_CONTRACT_REJECTED",
    "EXIT_QUALITY_REJECTED",
    "EXIT_EXECUTION_ERROR",
    "HORIZONTES_MICRO",
    "UmbralesPreflight",
    "ContratoBaselines",
    "CacheCandidate",
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
