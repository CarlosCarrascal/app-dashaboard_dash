"""Ejecuta y persiste el replay experimental de ocurrencia sobre el último backtest."""

from __future__ import annotations

import argparse
import json

import pandas as pd
import psycopg

from analitica import settings
from analitica.proyeccion.hibrido_ocurrencia import (
    NOMBRE_MODELO,
    ejecutar_replay_hibrido_ocurrencia,
    metricas_semanales,
)
from analitica.proyeccion.persistencia import RepositorioAnalytics


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    dsn = settings.postgres_dsn()
    with psycopg.connect(dsn) as con:
        origen = pd.read_sql_query(
            """
            WITH ultima AS (
                SELECT run_id, snapshot_id
                FROM analytics.forecast_run
                WHERE tipo='backtest' AND estado IN ('succeeded','published')
                ORDER BY fin DESC NULLS LAST, run_id DESC LIMIT 1
            ), limite AS (
                SELECT date_trunc('week', MAX(fecha))::date - 7 AS ultima_semana_cerrada
                FROM stg.v_h01_cosecha
            )
            SELECT p.* FROM analytics.prediction p
            JOIN ultima u USING (run_id) CROSS JOIN limite l
            WHERE p.modelo='MacroLegacy_v1' AND p.horizonte_semanas=1
              AND p.real_kg IS NOT NULL AND p.fecha_objetivo <= l.ultima_semana_cerrada
            ORDER BY p.fecha_objetivo,p.lote_id
            """,
            con,
        )
        contexto = pd.read_sql_query(
            """SELECT run_id,snapshot_id FROM analytics.forecast_run
                WHERE tipo='backtest' AND estado IN ('succeeded','published')
                ORDER BY fin DESC NULLS LAST,run_id DESC LIMIT 1""",
            con,
        ).iloc[0]
        referencias = pd.read_sql_query(
            """
            SELECT p.* FROM analytics.prediction p
            WHERE p.run_id=%s AND p.modelo IN ('MacroLegacy_v1','R09_publicado')
              AND p.horizonte_semanas=1 AND p.real_kg IS NOT NULL
            """,
            con,
            params=(int(contexto.run_id),),
        )

    detalle, resumen = ejecutar_replay_hibrido_ocurrencia(origen)
    if detalle.empty:
        raise RuntimeError("No existen semanas suficientes para ejecutar el replay")
    detalle["version_fuente"] = f"run_{int(contexto.run_id)}"

    columnas_persistencia = [
        "modelo",
        "version_modelo",
        "campania",
        "empresa",
        "fundo",
        "modulo",
        "lote",
        "lote_id",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
        "banda_horizonte",
        "version_fuente",
        "p10_kg",
        "p50_kg",
        "p90_kg",
        "real_kg",
        "plantas",
        "frutos_por_planta",
        "peso_baya_g",
        "confianza",
        "origen_emision",
        "tipo_prediccion",
        "es_replay_ciego",
        "es_curva_stitched",
        "estado_evaluacion",
        "componentes",
    ]
    for columna in columnas_persistencia:
        if columna not in detalle:
            detalle[columna] = None
        if columna not in referencias:
            referencias[columna] = None
    detalle_persistir = detalle[columnas_persistencia].copy()
    referencias_persistir = referencias[columnas_persistencia].copy()

    # El último run debe contener también las referencias para que el dashboard compare
    # exactamente el mismo origen sin buscar modelos en corridas diferentes.
    persistir = pd.concat([referencias_persistir, detalle_persistir], ignore_index=True, sort=False)
    repo = RepositorioAnalytics(dsn)
    run_id = repo.crear_run(
        int(contexto.snapshot_id),
        "backtest",
        {
            "modelo": NOMBRE_MODELO,
            "run_origen": int(contexto.run_id),
            "evaluacion": "rolling_origin",
            "semanas_calentamiento": 5,
            "peso_legacy": 0.5,
            "uso": "challenger_experimental_no_oficial",
        },
    )
    try:
        repo.guardar_predicciones(run_id, persistir)
        fechas_evaluadas = set(pd.to_datetime(resumen.fecha_objetivo))
        comparacion = []
        for modelo in ("MacroLegacy_v1", "R09_publicado"):
            candidata = referencias[
                referencias.modelo.eq(modelo)
                & pd.to_datetime(referencias.fecha_objetivo).isin(fechas_evaluadas)
            ]
            pred_semanal = candidata.groupby("fecha_objetivo", as_index=False).agg(
                p50_kg=("p50_kg", "sum")
            )
            pred_semanal["fecha_objetivo"] = pd.to_datetime(pred_semanal.fecha_objetivo)
            # El real común incluye todos los lotes cosechados. Un lote no publicado
            # por R09 equivale a predicción cero, no a retirar su cosecha del denominador.
            semanal = resumen[["fecha_objetivo", "real_kg"]].merge(
                pred_semanal, on="fecha_objetivo", how="left"
            )
            semanal["p50_kg"] = semanal.p50_kg.fillna(0.0)
            comparacion.append({"modelo": modelo, **metricas_semanales(semanal)})
        comparacion.append({"modelo": NOMBRE_MODELO, **metricas_semanales(resumen)})
        tabla_metricas = pd.DataFrame(comparacion).assign(
            banda_horizonte="1-2", n=lambda t: t.n_semanas
        )
        repo.guardar_metricas(
            run_id,
            tabla_metricas,
        )
        repo.finalizar_run(run_id, "succeeded")
    except Exception as exc:
        repo.finalizar_run(run_id, "failed", str(exc))
        raise
    print(json.dumps({"run_id": run_id, "comparacion": comparacion}, indent=2))


if __name__ == "__main__":
    main()
