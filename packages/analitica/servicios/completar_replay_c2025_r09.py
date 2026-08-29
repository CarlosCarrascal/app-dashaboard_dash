"""Servicio reusable para completar el replay de C2025 con la referencia R09.

No recalcula el modelo: copia únicamente la emisión publicada que existía en la
corrida 76 y la incorpora a la corrida 77, que ya contiene el replay completo de
C2025. Esto evita volver a gastar horas de calibración para corregir una selección de
filas de referencia.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analitica import settings
from analitica.proyeccion.gobernanza import RepositorioAnalytics
from analitica.proyeccion.metricas import metricas_cobertura_operacional, metricas_pronostico

RUN_COMPLETO = 77
RUN_ORIGEN = 76
SNAPSHOT_ID = 40
MODELO_R09 = "R09_publicado"


def _leer() -> pd.DataFrame:
    import psycopg

    with psycopg.connect(settings.postgres_dsn()) as conexion:
        completo = pd.read_sql_query(
            "SELECT * FROM analytics.prediction WHERE run_id = %s",
            conexion,
            params=(RUN_COMPLETO,),
        )
        r09 = pd.read_sql_query(
            """
            SELECT * FROM analytics.prediction
            WHERE run_id = %s AND modelo = %s AND campania = 'C2025'
            """,
            conexion,
            params=(RUN_ORIGEN, MODELO_R09),
        )
    return pd.concat([completo, r09], ignore_index=True, sort=False)


def _metricas(tabla: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for (campania, modelo), parte in tabla.groupby(["campania", "modelo"], sort=True):
        semanal = parte.groupby("fecha_objetivo", as_index=False).agg(
            real_kg=("real_kg", "sum"), p50_kg=("p50_kg", "sum")
        )
        semanal["modelo"] = modelo
        semanal["banda_horizonte"] = "operativo"
        semanal["serie_id"] = str(campania)
        semanal["p10_kg"] = np.nan
        semanal["p90_kg"] = np.nan
        diagnostico = metricas_pronostico(semanal)
        if diagnostico.empty:
            continue
        fila = diagnostico.iloc[0].to_dict()
        fila.update({"campania": str(campania), **metricas_cobertura_operacional(parte)})
        filas.append(fila)
    return pd.DataFrame(filas)


def ejecutar() -> dict[str, object]:
    """Consolida R09, persiste el replay y devuelve el resumen histórico."""

    predicciones = _leer()
    claves = ["modelo", "campania", "lote_id", "fecha_objetivo"]
    if predicciones.duplicated(claves).any():
        raise ValueError("La consolidación de R09 produjo duplicados")
    metricas = _metricas(predicciones)
    repo = RepositorioAnalytics(settings.postgres_dsn())
    run_id = repo.crear_run(
        SNAPSHOT_ID,
        "backtest",
        {
            "base_validada": RUN_COMPLETO,
            "r09_origen": RUN_ORIGEN,
            "modelo_hibrido": "HibridoOcurrenciaOnline_v2",
            "universo": "C2025_completa_mas_R09_publicado_disponible",
            "r09": "referencia_publicada_no_algoritmo",
        },
    )
    try:
        repo.guardar_predicciones(run_id, predicciones)
        repo.guardar_metricas(run_id, metricas)
        repo.finalizar_run(run_id, "succeeded")
    except Exception as exc:
        repo.finalizar_run(run_id, "failed", str(exc))
        raise
    return {
        "run_id": run_id,
        "filas": len(predicciones),
        "r09_c2025_filas": int(
            (predicciones.modelo.eq(MODELO_R09) & predicciones.campania.eq("C2025")).sum()
        ),
        "c2025_semanas_por_modelo": predicciones[predicciones.campania.eq("C2025")]
        .groupby("modelo")
        .fecha_objetivo.nunique()
        .to_dict(),
        "metricas_c2025": metricas[metricas.campania.eq("C2025")].to_dict("records"),
    }


# Los nombres sin guion bajo son la superficie reusable; los privados conservan
# los aliases que exponía el script histórico.
leer = _leer
metricas = _metricas


__all__ = [
    "MODELO_R09",
    "RUN_COMPLETO",
    "RUN_ORIGEN",
    "SNAPSHOT_ID",
    "ejecutar",
    "leer",
    "metricas",
]
