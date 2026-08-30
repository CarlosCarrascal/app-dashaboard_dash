"""API canónica de la familia híbrida.

La familia se divide por responsabilidad: ``macro`` contiene la curva base,
``priors`` la calibración as-of, ``residual`` la corrección, ``proyecciones``
la composición y ``replay`` la evaluación histórica.
"""

from .macro import (
    MacroParams,
    parametros_desde_bhattacharya,
    parametros_desde_fila,
    proyectar_macro,
)
from .priors import ParametroLegacyAsOf, calibrar_parametros_legacy_asof
from .proyecciones import (
    NOMBRE_MODELO,
    VERSION_MODELO,
    proyectar_hibrido_v1,
    proyectar_macro_legacy_v1,
)
from .replay import (
    backtest_hibrido_v1,
    backtest_macro_legacy_v1,
    construir_curva_historica,
)

__all__ = [
    "MacroParams",
    "NOMBRE_MODELO",
    "ParametroLegacyAsOf",
    "VERSION_MODELO",
    "backtest_hibrido_v1",
    "backtest_macro_legacy_v1",
    "calibrar_parametros_legacy_asof",
    "construir_curva_historica",
    "parametros_desde_bhattacharya",
    "parametros_desde_fila",
    "proyectar_hibrido_v1",
    "proyectar_macro",
    "proyectar_macro_legacy_v1",
]
