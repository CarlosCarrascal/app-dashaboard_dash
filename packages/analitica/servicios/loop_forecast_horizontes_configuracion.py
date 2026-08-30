"""Configuración del loop candidate-only por horizontes."""

from __future__ import annotations

import pandas as pd

from analitica.proyeccion.horizonte import (
    ConfiguracionCorreccionHorizonte,
    configuraciones_loop,
)

RUN_MACRO_MULTI = {"C2024": 71, "C2025": 72, "C2026": 73}
RUN_H1_APROBADO = {"C2024": 76, "C2025": 78, "C2026": 76}
RUN_R09_MULTI = {"C2024": 71, "C2025": 72, "C2026": 73}
RUN_NOWCAST = {"C2026": 84}
CIERRES = {
    "C2024": pd.Timestamp("2025-04-20"),
    "C2025": pd.Timestamp("2026-03-01"),
    "C2026": pd.Timestamp("2026-08-16"),
}
HORIZONTES = (1, 2, 3, 4, 5, 6)
HORIZONTES_LARGOS = (2, 3, 4, 5, 6)

__all__ = [
    "CIERRES",
    "HORIZONTES",
    "HORIZONTES_LARGOS",
    "RUN_H1_APROBADO",
    "RUN_MACRO_MULTI",
    "RUN_NOWCAST",
    "RUN_R09_MULTI",
    "ConfiguracionCorreccionHorizonte",
    "configuraciones_loop",
]
