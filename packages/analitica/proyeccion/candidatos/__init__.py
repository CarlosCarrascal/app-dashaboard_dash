"""Componentes internos para el preflight de candidatos.

Este paquete separa contratos, fuentes, validación, snapshots y caché; no publica
ni persiste candidatos por sí mismo.
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
from .turno_temporal_contratos import ConfiguracionTurnoTemporal
from .turno_temporal_nowcast import construir_nowcast_separado
from .turno_temporal_reingreso import (
    aplicar_turno_reingreso_candidate,
    estimar_desplazamiento_temporal_asof,
)
from .turno_temporal_validacion import (
    auditar_universo_candidate,
    metricas_adversariales,
    normalizar_forecast_candidate,
)

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
    "ConfiguracionTurnoTemporal",
    "aplicar_turno_reingreso_candidate",
    "auditar_universo_candidate",
    "construir_nowcast_separado",
    "estimar_desplazamiento_temporal_asof",
    "metricas_adversariales",
    "normalizar_forecast_candidate",
]
