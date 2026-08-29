"""Fachada compatible del modelo híbrido legacy.

La implementación vive en :mod:`analitica.proyeccion.hibrido.servicio` y en los
componentes especializados de la familia ``hibrido``. Esta ruta histórica se
conserva para consumidores existentes, incluidos imports privados usados por
replays y herramientas de calibración.
"""

from __future__ import annotations

# Esta fachada expone deliberadamente los imports históricos, incluso los privados.
# Se conserva la semántica previa de ``from ... import *`` (el módulo original no
# definía ``__all__``).
# ruff: noqa: F401
import numpy as np  # noqa: F401
import pandas as pd  # noqa: F401

from ..nucleo.bhattacharya import ParametrosBhattacharya
from .contratos import validar_predicciones_componentes
from .hibrido.macro import parametros_desde_bhattacharya, proyectar_macro
from .hibrido.priors import (
    ParametroLegacyAsOf,
    _arrays_calibracion,
    _campania_anterior,
    _campania_defecto,
    _fecha_poda,
    _identidad_lote,
    _legacy_input_cache,
    _metadatos_lotes,
    _normalizar_emisiones,
    _prior_grupal_historico,
    _prior_historico_lote,
    calibrar_parametros_legacy_asof,
)
from .hibrido.replay import (
    backtest_hibrido_v1,
    backtest_macro_legacy_v1,
    construir_curva_historica,
)
from .hibrido.replay import panel_corte_replay as _panel_corte_replay
from .hibrido.replay import panel_replay_cache as _panel_replay_cache
from .hibrido.residual import (
    EPSILON,
    FEATURES_PROHIBIDAS,
    FEATURES_RESIDUALES,
)
from .hibrido.residual import (
    CorreccionResidual as _CorreccionResidual,
)
from .hibrido.residual import (
    ajustar_residuales as _ajustar_residuales,
)
from .hibrido.residual import (
    features_presentes as _features_presentes,
)
from .hibrido.residual import (
    pipeline_residual as _pipeline_residual,
)
from .hibrido.servicio import (
    NOMBRE_MODELO,
    VERSION_MODELO,
    _legacy_panel,
    proyectar_hibrido_v1,
    proyectar_macro_legacy_v1,
)
