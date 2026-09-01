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
from .contexto_exportado import (
    construir_contexto_oleadas_asof,
    construir_contexto_por_lote_oleadas_asof,
)
from .contexto_oleadas import (
    FEATURES_CONTEXTO_POR_DEFECTO,
    PARAMETROS_CONTEXTO,
    ConfiguracionContextoOleadas,
    ModeloContextoOleadas,
    unir_contexto_asof,
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
from .oleadas_candidato import (
    PARAMETROS_MANUAL,
    proyectar_automatico_oleadas,
    proyectar_candidato_oleadas,
    proyectar_universo_automatico_oleadas,
)
from .snapshots import construir_snapshot_parametros
from .transiciones_inferidas import construir_transiciones_gaussianas_asof

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
    "PARAMETROS_MANUAL",
    "PARAMETROS_NOMBRADOS",
    "VERSION_MODELO",
    "ConfiguracionParametrosAsOf",
    "ConfiguracionContextoOleadas",
    "FEATURES_CONTEXTO_POR_DEFECTO",
    "ModeloContextoOleadas",
    "PARAMETROS_CONTEXTO",
    "construir_contexto_oleadas_asof",
    "construir_contexto_por_lote_oleadas_asof",
    "construir_transiciones_gaussianas_asof",
    "aprender_desplazamiento",
    "backtest_hibrido_parametros_asof",
    "construir_snapshot_parametros",
    "ejecutar_emision_parametros_asof",
    "normalizar_parametros_excel",
    "proyectar_automatico_oleadas",
    "proyectar_candidato_oleadas",
    "proyectar_universo_automatico_oleadas",
    "seleccionar_gdd_config",
    "seleccionar_peso_macro",
    "unir_contexto_asof",
]
