"""Fachada compatible para los experimentos candidate-only de turno temporal.

La implementación interna vive en :mod:`analitica.proyeccion.candidatos`.
Este módulo conserva las rutas históricas y sus reexports públicos.
"""

from __future__ import annotations

from .candidatos import turno_temporal_contratos as _contratos
from .candidatos.turno_temporal_nowcast import construir_nowcast_separado
from .candidatos.turno_temporal_reingreso import (
    aplicar_turno_reingreso_candidate,
    estimar_desplazamiento_temporal_asof,
)
from .candidatos.turno_temporal_validacion import (
    auditar_universo_candidate,
    metricas_adversariales,
    normalizar_forecast_candidate,
)

CLAVE_FORECAST = _contratos.CLAVE_FORECAST
CLAVE_UNIVERSO = _contratos.CLAVE_UNIVERSO
ConfiguracionTurnoTemporal = _contratos.ConfiguracionTurnoTemporal
_semana_inicio = _contratos._semana_inicio

__all__ = [
    "CLAVE_FORECAST",
    "CLAVE_UNIVERSO",
    "ConfiguracionTurnoTemporal",
    "aplicar_turno_reingreso_candidate",
    "auditar_universo_candidate",
    "construir_nowcast_separado",
    "estimar_desplazamiento_temporal_asof",
    "metricas_adversariales",
    "normalizar_forecast_candidate",
]
