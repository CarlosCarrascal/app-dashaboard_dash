"""Contratos y configuración del scheduler de lotes activos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

RUN_ID = 78
CAMPANIAS = ("C2024", "C2025", "C2026")
FUNDOS = ("Arena", "Ayllu", "Kawsay", "Quri")
SEMANA_DESARROLLO_FINAL = 30
SEMANAS_HOLDOUT = (31, 32, 33)
CIERRE_C2026 = pd.Timestamp("2026-08-16")
RUTA_SALIDA = Path(".tmp/screening_active_lot_scheduler.json")


@dataclass(frozen=True)
class ConfiguracionScheduler:
    sigma_dias: float
    mezcla_actividad: float
    peso_lote: float
    piso_actividad: float
    fuerza_escala: float
    lookback_escala: int
    shrink_escala: float = 6.0
    escala_minima: float = 0.72
    escala_maxima: float = 1.35

    @property
    def id(self) -> str:
        return (
            f"sig{self.sigma_dias:g}-mix{self.mezcla_actividad:g}-"
            f"wl{self.peso_lote:g}-floor{self.piso_actividad:g}-"
            f"scale{self.fuerza_escala:g}-lb{self.lookback_escala}"
        )


def configuraciones() -> list[ConfiguracionScheduler]:
    base = [
        ConfiguracionScheduler(5.0, 0.0, 1.0, 0.08, 0.0, 4),
    ]
    base.extend(
        ConfiguracionScheduler(sigma, mezcla, peso_lote, 0.08, fuerza, lookback)
        for sigma in (3.5, 5.0, 7.0)
        for mezcla in (0.10, 0.25, 0.40)
        for peso_lote in (0.70, 1.00)
        for fuerza in (0.0, 0.25, 0.50)
        for lookback in (4, 8)
    )
    return base
