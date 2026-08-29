"""Fachada interna que reúne contratos, corrección y evaluación por horizonte."""

from .contratos import ConfiguracionCorreccionHorizonte
from .correccion import aplicar_correccion_horizonte, normalizar_panel
from .evaluacion import (
    agregar_semanal,
    configuraciones_loop,
    ejecutar_loop_horizonte,
    ejecutar_loop_por_horizonte,
    evaluar_mismo_universo,
    metricas_horizonte,
    seleccionar_vintage_coherente,
)

__all__ = [
    "ConfiguracionCorreccionHorizonte",
    "agregar_semanal",
    "aplicar_correccion_horizonte",
    "configuraciones_loop",
    "ejecutar_loop_horizonte",
    "ejecutar_loop_por_horizonte",
    "evaluar_mismo_universo",
    "metricas_horizonte",
    "normalizar_panel",
    "seleccionar_vintage_coherente",
]
