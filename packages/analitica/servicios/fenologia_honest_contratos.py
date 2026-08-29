"""Contratos y configuración del screening honesto de clima y fenología."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

CAMPANIA = "C2026"
RUN_ID = 73
SEMANA_INICIAL = 13
SEMANA_DESARROLLO_FINAL = 30
SEMANAS_HOLDOUT = (31, 32, 33)
HORIZONTES = tuple(range(1, 7))
CIERRE_CERTIFICADO = pd.Timestamp("2026-08-16")
TBASES = (0.0, 4.4, 7.0, 8.0)
VENTANAS = (7, 14, 21, 28)
FUNDOS = ("Arena", "Ayllu", "Kawsay", "Quri")
RUNS_EXTERNOS = {"C2024": 71, "C2025": 72}

MAPEO_FUNDO = {
    "aqu anqa 1": "Arena",
    "aqu anqa 2": "Quri",
    "aqu anqa 3": "Kawsay",
    "aqu anqa 4": "Ayllu",
    "aqu anqa 5": "Kawsay",
}

SQL_MACRO = """
    SELECT campania, fecha_emision, fecha_objetivo, horizonte_semanas,
           lote_id, fundo, modulo, p50_kg, real_kg
    FROM analytics.prediction
    WHERE run_id=%s AND campania=%s AND modelo='MacroLegacy_v1'
      AND horizonte_semanas BETWEEN 1 AND 6
      AND fecha_emision < fecha_objetivo
    ORDER BY fecha_emision, lote_id, horizonte_semanas
"""

SQL_CLIMA = """
    SELECT fecha_hora, temp, temp_alta, temp_baja, humedad, et_mm
    FROM stg.v_h05_clima
    WHERE fecha_hora IS NOT NULL
    ORDER BY fecha_hora
"""

SQL_ESTADOS = """
    SELECT lote_id, fecha, e1, e2, e3, e4, e5
    FROM stg.v_e03_estados
    WHERE lote_id IS NOT NULL AND fecha IS NOT NULL
    ORDER BY fecha, lote_id
"""

SQL_FLORES = """
    SELECT lote_id, fecha, planta, n_flores, cuajo
    FROM stg.v_e02_flores
    WHERE lote_id IS NOT NULL AND fecha IS NOT NULL
    ORDER BY fecha, lote_id
"""


@dataclass(frozen=True)
class Configuracion:
    familia: str
    variable_clima: str | None = None
    tbase: float | None = None
    ventana_dias: int | None = None
    coef_clima: float = 0.0
    variable_fenologia: str | None = None
    coef_fenologia: float = 0.0
    desplazamiento_max: float = 1.0

    @property
    def id(self) -> str:
        partes = [self.familia]
        if self.variable_clima:
            partes.extend(
                [
                    self.variable_clima,
                    f"b{self.tbase:g}" if self.tbase is not None else "bNA",
                    f"w{self.ventana_dias}",
                    f"c{self.coef_clima:+g}",
                ]
            )
        if self.variable_fenologia:
            partes.extend([self.variable_fenologia, f"f{self.coef_fenologia:+g}"])
        return "-".join(partes).replace(".", "_")
