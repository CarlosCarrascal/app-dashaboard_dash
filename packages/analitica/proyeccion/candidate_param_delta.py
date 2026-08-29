"""Fachada compatible para el candidato de deltas de parámetros.

La implementación vive en :mod:`analitica.proyeccion.parametros`; este módulo
conserva la ruta histórica para no romper integraciones existentes.
"""

from .parametros.candidate_param_delta import (
    PARAMETRO_CAIDA,  # noqa: F401
    PARAMETRO_FINICIO,  # noqa: F401
    PARAMETROS_B,
    PARAMETROS_DIAS,
    PARAMETROS_LOG,
    CandidateParamDelta,
    ConfiguracionParamDelta,
    ModeloDeltaParametros,
)  # noqa: F401

__all__ = [
    "CandidateParamDelta",
    "ConfiguracionParamDelta",
    "ModeloDeltaParametros",
    "PARAMETROS_B",
    "PARAMETROS_DIAS",
    "PARAMETROS_LOG",
]
