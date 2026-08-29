# Estos imports conservan nombres históricos disponibles en este módulo; las
# implementaciones viven en ``proyecciones`` y ``replay``.
# ruff: noqa: F401

"""Implementación del modelo híbrido legacy.

Este módulo contiene la lógica de negocio de la familia híbrida: construcción
de la curva macro as-of, corrección residual y proyección de las dos variantes
legacy. La ruta histórica queda como una fachada que reexporta estos símbolos;
las dependencias internas apuntan aquí y no vuelven a la fachada.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ...nucleo.bhattacharya import ParametrosBhattacharya
from ..contratos import validar_predicciones_componentes
from . import residual as _residual
from .macro import parametros_desde_bhattacharya, proyectar_macro
from .priors import ParametroLegacyAsOf
from .proyecciones import (
    NOMBRE_MODELO,
    VERSION_MODELO,
    _legacy_panel,
    proyectar_hibrido_v1,
    proyectar_macro_legacy_v1,
)
from .replay import (
    backtest_hibrido_v1,
    backtest_macro_legacy_v1,
    construir_curva_historica,
    panel_corte_replay,
    panel_replay_cache,
)

_CorreccionResidual = _residual.CorreccionResidual
EPSILON = _residual.EPSILON
FEATURES_PROHIBIDAS = _residual.FEATURES_PROHIBIDAS
FEATURES_RESIDUALES = _residual.FEATURES_RESIDUALES
_ajustar_residuales = _residual.ajustar_residuales
_features_presentes = _residual.features_presentes
_pipeline_residual = _residual.pipeline_residual

__all__ = [
    "backtest_hibrido_v1",
    "backtest_macro_legacy_v1",
    "construir_curva_historica",
    "panel_corte_replay",
    "panel_replay_cache",
    "proyectar_hibrido_v1",
    "proyectar_macro_legacy_v1",
]
