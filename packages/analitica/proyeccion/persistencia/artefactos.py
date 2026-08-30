"""Persistencia de resultados de calidad y artefactos auditables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..compartido import limpiar_valor as _limpio
from ..compartido import serializar_json as _json


class ArtefactosMixin:
    """Operaciones de calidad y archivos asociados a una corrida."""

    def guardar_calidad(self, snapshot_id: int, run_id: int, calidad: pd.DataFrame):
        if calidad.empty:
            return
        filas = [
            (
                snapshot_id,
                run_id,
                f.regla,
                f.estado,
                int(f.observados),
                int(f.afectados),
                _json(
                    {
                        "detalle": _limpio(getattr(f, "detalle", "")),
                        "max_diferencia_kg": _limpio(getattr(f, "max_diferencia_kg", None)),
                    }
                ),
            )
            for f in calidad.itertuples(index=False)
        ]
        with self.conexion() as con, con.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO analytics.quality_result
                    (snapshot_id, run_id, regla, estado, observados, afectados, detalle)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
                filas,
            )

    def guardar_artifacto(self, run_id: int, tipo: str, ruta: Path, sha256: str):
        with self.conexion() as con, con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics.artifact (run_id, tipo, uri, sha256, bytes)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
            """,
                (run_id, tipo, str(ruta.resolve()), sha256, ruta.stat().st_size),
            )
