"""Fachada compatible del loop candidate-only de forecast por horizontes.

La configuración, lectura, predicción, evaluación y salida viven en módulos
hermanos especializados. Este módulo conserva las rutas históricas y sus
aliases públicos/privados.
"""

from __future__ import annotations

from typing import Any  # noqa: F401 - alias histórico

import pandas as pd  # noqa: F401 - alias histórico consumido por la fachada CLI
import psycopg  # noqa: F401 - alias histórico consumido por la fachada CLI

from analitica.settings import postgres_dsn  # noqa: F401 - alias histórico

from . import loop_forecast_horizontes_configuracion as _configuracion
from . import loop_forecast_horizontes_evaluacion as _evaluacion
from . import loop_forecast_horizontes_lectura as _lectura
from . import loop_forecast_horizontes_prediccion as _prediccion
from . import loop_forecast_horizontes_salida as _salida

RUN_MACRO_MULTI = _configuracion.RUN_MACRO_MULTI
RUN_H1_APROBADO = _configuracion.RUN_H1_APROBADO
RUN_R09_MULTI = _configuracion.RUN_R09_MULTI
RUN_NOWCAST = _configuracion.RUN_NOWCAST
CIERRES = _configuracion.CIERRES
HORIZONTES = _configuracion.HORIZONTES
HORIZONTES_LARGOS = _configuracion.HORIZONTES_LARGOS
ConfiguracionCorreccionHorizonte = _prediccion.ConfiguracionCorreccionHorizonte
aplicar_correccion_horizonte = _prediccion.aplicar_correccion_horizonte
configuraciones_loop = _configuracion.configuraciones_loop
ejecutar_loop_por_horizonte = _prediccion.ejecutar_loop_por_horizonte
seleccionar_vintage_coherente = _evaluacion.seleccionar_vintage_coherente

_leer_predicciones = _lectura._leer_predicciones
_normalizar_fundo = _lectura._normalizar_fundo
_consolidar_fundos = _lectura._consolidar_fundos
_panel_base = _lectura._panel_base
_leer_nowcast = _lectura._leer_nowcast

_semanal = _evaluacion._semanal
_metricas = _evaluacion._metricas
_metricas_por_horizonte = _evaluacion._metricas_por_horizonte
_comparar_r09 = _evaluacion._comparar_r09
_resumen_nowcast_vs_v2 = _evaluacion._resumen_nowcast_vs_v2

_aplicar_mejores = _prediccion._aplicar_mejores
ejecutar = _salida.ejecutar

__all__ = [
    "CIERRES",
    "HORIZONTES",
    "HORIZONTES_LARGOS",
    "RUN_H1_APROBADO",
    "RUN_MACRO_MULTI",
    "RUN_NOWCAST",
    "RUN_R09_MULTI",
    "ConfiguracionCorreccionHorizonte",
    "aplicar_correccion_horizonte",
    "configuraciones_loop",
    "ejecutar",
    "ejecutar_loop_por_horizonte",
    "pd",
    "postgres_dsn",
    "psycopg",
    "seleccionar_vintage_coherente",
]
