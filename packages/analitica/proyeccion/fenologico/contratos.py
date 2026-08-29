"""Contratos de datos y escenarios del modelo fenológico."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

__all__ = ["EscenarioFenologico", "ResultadoFenologico"]


@dataclass
class ResultadoFenologico:
    """Resultado estable de una proyección o replay fenológico."""

    predicciones: pd.DataFrame
    evidencia_features: pd.DataFrame = field(default_factory=pd.DataFrame)
    advertencias: list[str] = field(default_factory=list)
    auditoria: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass(frozen=True)
class EscenarioFenologico:
    """Cambios para el simulador; los efectos son asociaciones locales del modelo."""

    nombre: str = "base"
    plantas_pct: float = 0.0
    cuajado_pct: float = 0.0
    caida_frutos_pct: float = 0.0
    riego_pct: float = 0.0
    temp_delta_c: float = 0.0
    dpv_delta_kpa: float = 0.0
    poda_delta_dias: int = 0
    desplazamiento_semanas: int = 0

    def __post_init__(self) -> None:
        if self.plantas_pct <= -100 or not np.isfinite(self.plantas_pct):
            raise ValueError("plantas_pct debe ser finito y mayor que -100")
        if self.cuajado_pct <= -100 or not np.isfinite(self.cuajado_pct):
            raise ValueError("cuajado_pct debe ser finito y mayor que -100")
        if not 0 <= self.caida_frutos_pct <= 100:
            raise ValueError("caida_frutos_pct debe estar entre 0 y 100")
        if not -52 <= self.desplazamiento_semanas <= 52:
            raise ValueError("desplazamiento_semanas debe estar entre -52 y 52")
