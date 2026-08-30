"""Servicio reutilizable para buscar candidatos de replay.

La lectura conserva el universo histórico de releases aprobadas y el corte
as-of del script original. El servicio no escribe en PostgreSQL: prepara el
panel y ejecuta el loop de selección para que la misma lógica pueda ser usada
por otras interfaces además de la fachada CLI.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import psycopg

from analitica.aplicacion.procesos.candidatos import escribir_json_reproducible
from analitica.aplicacion.procesos.seleccion_candidatos import preparar_panel, successive_halving
from analitica.settings import postgres_dsn


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--salida", type=Path)
    return parser.parse_args()


def _leer() -> pd.DataFrame:
    dsn = postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL no está configurado")
    consulta = """
        SELECT r.evaluation_contract_id, p.campania, p.fecha_emision,
               date_trunc('week', p.fecha_objetivo)::date AS fecha_objetivo,
               p.lote_id, p.modelo, p.p50_kg, p.real_kg
        FROM analytics.model_series_release r
        JOIN analytics.prediction p
          ON p.run_id = r.run_id
         AND p.campania = r.campania
         AND p.modelo = r.modelo
         AND COALESCE(p.version_modelo, 'sin_version') = r.version_modelo
        WHERE r.estado = 'approved' AND r.activo AND r.uso = 'historico'
          AND r.modelo IN ('MacroLegacy_v1', 'HibridoOcurrenciaOnline_v2')
          AND r.campania IN ('C2025', 'C2026')
          AND p.horizonte_semanas = 1
          AND p.real_kg IS NOT NULL
          AND COALESCE(p.origen_emision, p.fecha_emision)
              < date_trunc('week', p.fecha_objetivo)::date
        ORDER BY p.campania, p.fecha_objetivo, p.lote_id, p.modelo
    """
    with psycopg.connect(dsn) as conexion, conexion.cursor() as cursor:
        cursor.execute(consulta)
        columnas = [descripcion.name for descripcion in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=columnas)


def ejecutar() -> dict[str, object]:
    """Lee el panel elegible y ejecuta la selección histórica de candidatos."""

    return successive_halving(preparar_panel(_leer()))


__all__ = [
    "argparse",
    "ejecutar",
    "escribir_json_reproducible",
    "pd",
    "Path",
    "postgres_dsn",
    "psycopg",
    "preparar_panel",
    "successive_halving",
]
