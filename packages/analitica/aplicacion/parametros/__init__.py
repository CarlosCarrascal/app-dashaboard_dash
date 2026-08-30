"""Componentes de parámetros de la proyección."""

import sys
import types

from . import mezcla as _mezcla
from .candidate_param_delta import (
    PARAMETRO_CAIDA,
    PARAMETRO_FINICIO,
    PARAMETROS_B,
    PARAMETROS_DIAS,
    PARAMETROS_LOG,
    CandidateParamDelta,
    ConfiguracionParamDelta,
    ModeloDeltaParametros,
)
from .contratos import (
    CLAVES,
    NOMBRE_MODELO,
    PARAMETROS_NOMBRADOS,
    VERSION_MODELO,
    ConfiguracionParametrosAsOf,
)
from .desplazamientos import aprender_desplazamiento, seleccionar_gdd_config
from .ejecucion import backtest_hibrido_parametros_asof, ejecutar_emision_parametros_asof
from .mezcla import seleccionar_peso_macro
from .normalizacion import normalizar_parametros_excel
from .snapshots import construir_snapshot_parametros

_seleccion_compat = types.ModuleType(f"{__name__}.seleccion", _mezcla.__doc__)
_seleccion_compat.__package__ = __name__
_seleccion_compat.__file__ = _mezcla.__file__
_seleccion_compat.seleccionar_peso_macro = seleccionar_peso_macro
_seleccion_compat.__all__ = ["seleccionar_peso_macro"]
sys.modules[_seleccion_compat.__name__] = _seleccion_compat
seleccion = _seleccion_compat

__all__ = [
    "CandidateParamDelta",
    "ConfiguracionParamDelta",
    "ModeloDeltaParametros",
    "PARAMETROS_B",
    "PARAMETROS_DIAS",
    "PARAMETROS_LOG",
    "PARAMETRO_CAIDA",
    "PARAMETRO_FINICIO",
    "CLAVES",
    "NOMBRE_MODELO",
    "PARAMETROS_NOMBRADOS",
    "VERSION_MODELO",
    "ConfiguracionParametrosAsOf",
    "aprender_desplazamiento",
    "backtest_hibrido_parametros_asof",
    "construir_snapshot_parametros",
    "ejecutar_emision_parametros_asof",
    "normalizar_parametros_excel",
    "seleccionar_gdd_config",
    "seleccionar_peso_macro",
]
