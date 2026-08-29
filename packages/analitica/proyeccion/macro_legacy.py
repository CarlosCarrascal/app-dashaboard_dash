"""Fachada compatible de la macro ``forecast`` de Excel.

La implementación pura vive en :mod:`analitica.proyeccion.hibrido.macro`. Se mantienen
estos nombres en su ruta histórica porque los usan el híbrido, el torneo, los scripts y
los consumidores externos.
"""

from .hibrido.macro import (
    MacroParams,
    _fraccion_ola,
    parametros_desde_bhattacharya,
    parametros_desde_fila,
    proyectar_macro,
)

__all__ = [
    "MacroParams",
    "_fraccion_ola",
    "parametros_desde_bhattacharya",
    "parametros_desde_fila",
    "proyectar_macro",
]
