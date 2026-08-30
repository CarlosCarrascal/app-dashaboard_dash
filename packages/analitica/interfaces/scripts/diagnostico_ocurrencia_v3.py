from __future__ import annotations

import argparse
import json

import pandas as pd
import psycopg

from analitica import settings
from analitica.dominio.evaluacion.metricas import metricas_pronostico
from analitica.dominio.modelos.ocurrencia_v3 import ejecutar_replay_hibrido_ocurrencia_v3


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    with psycopg.connect(settings.postgres_dsn()) as conexion:
        runs = pd.read_sql_query(
            "SELECT run_id, estado, inicio, tipo "
            "FROM analytics.forecast_run ORDER BY run_id DESC LIMIT 8",
            conexion,
        )
        run_id = int(runs.loc[runs.estado.eq("succeeded"), "run_id"].iloc[0])
        base = pd.read_sql_query(
            """
            SELECT * FROM analytics.prediction
            WHERE run_id = %s AND campania = 'C2026' AND modelo = 'MacroLegacy_v1'
              AND horizonte_semanas = 1
            """,
            conexion,
            params=(run_id,),
        )
    base["fecha_objetivo"] = pd.to_datetime(base["fecha_objetivo"])
    base["fecha_emision"] = pd.to_datetime(base["fecha_emision"])
    detalle, _ = ejecutar_replay_hibrido_ocurrencia_v3(base)
    semanal = detalle.groupby("fecha_objetivo", as_index=False).agg(
        real_kg=("real_kg", "sum"),
        p50_kg=("p50_kg", "sum"),
        peso_ocurrencia=("peso_ocurrencia_v3", "mean"),
        macro=("macro_kg_v3", "sum"),
        hurdle=("hurdle_kg_v3", "sum"),
    )
    semanal["modelo"] = "HibridoOcurrenciaOnline_v3"
    semanal["banda_horizonte"] = "operativo"
    semanal["serie_id"] = "C2026"
    semanal["p10_kg"] = float("nan")
    semanal["p90_kg"] = float("nan")
    metrica = metricas_pronostico(semanal).iloc[0].to_dict()
    print(
        json.dumps(
            {"run_id": run_id, "metricas": metrica, "semanal": semanal.to_dict("records")},
            default=str,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
