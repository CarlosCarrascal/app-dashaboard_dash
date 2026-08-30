"""Fachada compatible del screening cross-campaign h1."""

from __future__ import annotations

from . import (
    cross_campaign_evaluacion as _evaluacion,
)
from . import (
    cross_campaign_features as _features,
)
from . import (
    cross_campaign_lectura as _lectura,
)
from . import (
    cross_campaign_persistencia as _persistencia,
)
from . import (
    cross_campaign_prediccion as _prediccion,
)

_bootstrap_por_fundo = _evaluacion._bootstrap_por_fundo
_keyset_sha256 = _evaluacion._keyset_sha256
_metricas = _evaluacion._metricas
_por_fundo = _evaluacion._por_fundo
_resumen_periodo = _evaluacion._resumen_periodo
bootstrap_pareado = _evaluacion.bootstrap_pareado
ejecutar = _evaluacion.ejecutar
mascara_seleccion = _evaluacion.mascara_seleccion
seleccionar_configuracion = _evaluacion.seleccionar_configuracion

construir_features_asof = _features.construir_features_asof

_VERSION_RE = _lectura._VERSION_RE
_columna_campania = _lectura._columna_campania
_conexion_access = _lectura._conexion_access
_fecha_emision_r09 = _lectura._fecha_emision_r09
_mapear_fundo_h01 = _lectura._mapear_fundo_h01
CAMPAIGNAS = _lectura.CAMPAIGNAS
CIERRE_CERTIFICADO_C2026 = _lectura.CIERRE_CERTIFICADO_C2026
FUNDOS = _lectura.FUNDOS
MACRO_RUN_ID = _lectura.MACRO_RUN_ID
REAL_ACCESS_DEFAULT = _lectura.REAL_ACCESS_DEFAULT
R09_ACCESS_DEFAULT = _lectura.R09_ACCESS_DEFAULT
SEMANA_DESARROLLO_C2026 = _lectura.SEMANA_DESARROLLO_C2026
SEMANAS_HOLDOUT_C2026 = _lectura.SEMANAS_HOLDOUT_C2026
construir_panel = _lectura.construir_panel
leer_macro_h1 = _lectura.leer_macro_h1
leer_reales_access = _lectura.leer_reales_access
leer_r09_access = _lectura.leer_r09_access
normalizar_fundo = _lectura.normalizar_fundo
preparar_r09_crudo = _lectura.preparar_r09_crudo

_json_default = _persistencia._json_default
escribir_json = _persistencia.escribir_json
sha256_archivo = _persistencia.sha256_archivo

_columnas_modelo = _prediccion._columnas_modelo
_matriz = _prediccion._matriz
_predecir_bayes = _prediccion._predecir_bayes
FEATURE_SETS = _prediccion.FEATURE_SETS
Configuracion = _prediccion.Configuracion
configuraciones = _prediccion.configuraciones
mascara_entrenamiento = _prediccion.mascara_entrenamiento
predecir_rolling = _prediccion.predecir_rolling

__all__ = [
    "CAMPAIGNAS",
    "CIERRE_CERTIFICADO_C2026",
    "FEATURE_SETS",
    "FUNDOS",
    "MACRO_RUN_ID",
    "REAL_ACCESS_DEFAULT",
    "R09_ACCESS_DEFAULT",
    "SEMANA_DESARROLLO_C2026",
    "SEMANAS_HOLDOUT_C2026",
    "Configuracion",
    "bootstrap_pareado",
    "construir_features_asof",
    "construir_panel",
    "configuraciones",
    "ejecutar",
    "escribir_json",
    "leer_macro_h1",
    "leer_reales_access",
    "leer_r09_access",
    "mascara_entrenamiento",
    "mascara_seleccion",
    "normalizar_fundo",
    "predecir_rolling",
    "preparar_r09_crudo",
    "seleccionar_configuracion",
    "sha256_archivo",
]
