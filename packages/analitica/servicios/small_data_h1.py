"""Fachada compatible del screening honesto de ML pequeño para H1.

La configuración, lectura, predicción, evaluación y salida viven en módulos
hermanos especializados. Este módulo conserva los nombres históricos,
incluidos los aliases privados usados por scripts y notebooks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass  # noqa: F401 - aliases históricos
from typing import Any  # noqa: F401 - alias histórico

import numpy as np  # noqa: F401 - alias histórico consumido por la fachada CLI
import pandas as pd  # noqa: F401 - alias histórico consumido por la fachada CLI
from sklearn.linear_model import HuberRegressor, Ridge  # noqa: F401
from sklearn.preprocessing import StandardScaler  # noqa: F401

from . import small_data_h1_configuracion as _configuracion
from . import small_data_h1_evaluacion as _evaluacion
from . import small_data_h1_lectura as _lectura
from . import small_data_h1_prediccion as _prediccion
from . import small_data_h1_salida as _salida

CAMPANIA_DEFAULT = _configuracion.CAMPANIA_DEFAULT
FEATURE_SETS = _configuracion.FEATURE_SETS
FUNDOS = _configuracion.FUNDOS
RUN_ID_DEFAULT = _configuracion.RUN_ID_DEFAULT
SEMANA_MAX_SELECCION = _configuracion.SEMANA_MAX_SELECCION
SEMANAS_HOLDOUT = _configuracion.SEMANAS_HOLDOUT
ULTIMO_CIERRE_DEFAULT = _configuracion.ULTIMO_CIERRE_DEFAULT
Configuracion = _configuracion.Configuracion
configuraciones = _configuracion.configuraciones

_cargar_universo_lote = _lectura._cargar_universo_lote
cargar_universo_lote = _lectura.cargar_universo_lote
normalizar_fundo = _lectura.normalizar_fundo

_ajustar_modelo = _prediccion._ajustar_modelo
aplicar_candidato_a_lotes = _prediccion.aplicar_candidato_a_lotes
construir_panel_fundo = _prediccion.construir_panel_fundo
predecir_rolling = _prediccion.predecir_rolling

_metricas = _evaluacion._metricas
_resumen_periodo = _evaluacion._resumen_periodo
_wins = _evaluacion._wins
seleccionar_configuracion = _evaluacion.seleccionar_configuracion

_json_default = _salida._json_default
ejecutar = _salida.ejecutar
