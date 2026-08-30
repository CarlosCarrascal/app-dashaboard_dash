"""Persiste ``HibridoOcurrenciaOnline_v1`` sobre un universo común con R09.

El modelo de ocurrencia fue diseñado para el horizonte operativo corto. Esta
corrida no lo mezcla con todas las emisiones de una campaña: usa únicamente
filas de horizonte 1 que existen simultáneamente en R09 y MacroLegacy, tienen
cosecha real evaluable y comparten ``campania × lote_id × fecha_objetivo``.

Las corridas 71, 72 y 73 ya contienen la MacroLegacy validada para C2024,
C2025 y C2026. Reutilizarlas evita recalibrar nuevamente la macro y mantiene
el mismo snapshot 40. El nuevo run persiste R09, MacroLegacy y Ocurrencia en
un único universo para que el dashboard pueda comparar sin cambiar el
denominador.

Uso:
    python -m analitica.interfaces.scripts.persistir_ocurrencia_universo

Para validar sin escribir:
    python -m analitica.interfaces.scripts.persistir_ocurrencia_universo --dry-run
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from analitica import settings
from analitica.dominio.evaluacion.metricas import metricas_pareadas_modelos
from analitica.dominio.modelos.ocurrencia_v1 import (
    NOMBRE_MODELO,
    VERSION_MODELO,
    ejecutar_replay_hibrido_ocurrencia,
    metricas_semanales,
)
from analitica.infraestructura.persistencia import RepositorioAnalytics

MODELO_R09 = "R09_publicado"
MODELO_MACRO = "MacroLegacy_v1"
SNAPSHOT_ID = 40
RUNS_MACRO = (71, 72, 73)
CLAVES = ["campania", "lote_id", "fecha_objetivo"]


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="calcula y valida sin persistir")
    return parser.parse_args()


def _leer_universo() -> pd.DataFrame:
    """Lee R09 y Macro h1 de las corridas validadas y deja una intersección única."""

    dsn = settings.postgres_dsn()
    if not dsn:
        raise RuntimeError("No hay DSN de PostgreSQL configurado.")
    import psycopg

    consulta = """
        WITH candidatos AS (
            SELECT p.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY p.modelo, p.campania, p.lote_id, p.fecha_objetivo
                       ORDER BY p.fecha_emision DESC, p.prediction_id DESC
                   ) AS rn
            FROM analytics.prediction p
            WHERE p.run_id = ANY(%s)
              AND p.modelo = ANY(%s)
              AND p.horizonte_semanas = 1
              AND p.real_kg IS NOT NULL
        ), unicos AS (
            SELECT *
            FROM candidatos
            WHERE rn = 1
        ), comunes AS (
            SELECT campania, lote_id, fecha_objetivo
            FROM unicos
            GROUP BY campania, lote_id, fecha_objetivo
            HAVING COUNT(DISTINCT modelo) = 2
        )
        SELECT u.*
        FROM unicos u
        JOIN comunes c USING (campania, lote_id, fecha_objetivo)
        ORDER BY u.campania, u.fecha_objetivo, u.lote_id, u.modelo
    """
    with psycopg.connect(dsn) as conexion:
        tabla = pd.read_sql_query(
            consulta,
            conexion,
            params=(list(RUNS_MACRO), [MODELO_R09, MODELO_MACRO]),
        )
    if tabla.empty:
        raise ValueError("No existe intersección R09–MacroLegacy evaluable.")
    tabla["fecha_emision"] = pd.to_datetime(tabla["fecha_emision"], errors="raise")
    tabla["fecha_objetivo"] = pd.to_datetime(tabla["fecha_objetivo"], errors="raise")
    return tabla


def _por_modelo(tabla: pd.DataFrame, modelo: str) -> pd.DataFrame:
    salida = tabla[tabla.modelo.eq(modelo)].copy()
    if salida.empty:
        raise ValueError(f"No hay filas comunes para {modelo}.")
    return salida


def _preparar_panel_ocurrencia(macro: pd.DataFrame) -> pd.DataFrame:
    """Deja el contrato que requiere el modelo online y conserva el universo común."""

    salida = macro.copy()
    salida["p50_kg"] = pd.to_numeric(salida["p50_kg"], errors="coerce").fillna(0.0)
    salida["real_kg"] = pd.to_numeric(salida["real_kg"], errors="coerce").fillna(0.0)
    salida["version_fuente"] = "snapshot_40_universo_R09_Macro_h1"
    return salida


def _contrato_predicciones(tabla: pd.DataFrame, modelo: str, version: str) -> pd.DataFrame:
    salida = tabla.copy()
    salida["modelo"] = modelo
    salida["version_modelo"] = version
    salida["horizonte_semanas"] = (
        pd.to_numeric(salida.get("horizonte_semanas", 1), errors="coerce").fillna(1).astype(int)
    )
    # La base de datos usa las bandas gobernadas, no las etiquetas visibles
    # "1–2 semanas" del dashboard.
    salida["banda_horizonte"] = "operativo"
    salida["fecha_emision"] = pd.to_datetime(salida["fecha_emision"]).dt.normalize()
    salida["fecha_objetivo"] = pd.to_datetime(salida["fecha_objetivo"]).dt.normalize()
    salida["origen_emision"] = salida["fecha_emision"]
    salida["tipo_prediccion"] = "replay"
    salida["es_replay_ciego"] = True
    salida["es_curva_stitched"] = (
        salida.get("es_curva_stitched", pd.Series(False, index=salida.index))
        .fillna(False)
        .astype(bool)
    )
    salida["estado_evaluacion"] = np.where(salida["real_kg"].notna(), "evaluada", "pendiente")
    for columna in ("p10_kg", "p90_kg"):
        if columna not in salida:
            salida[columna] = np.nan
    return salida


def construir_corrida() -> tuple[pd.DataFrame, dict]:
    universo = _leer_universo()
    r09 = _por_modelo(universo, MODELO_R09)
    macro = _por_modelo(universo, MODELO_MACRO)
    panel = _preparar_panel_ocurrencia(macro)
    ocurrencia, resumen = ejecutar_replay_hibrido_ocurrencia(panel)
    if ocurrencia.empty:
        raise ValueError("OcurrenciaOnline no generó predicciones evaluables.")

    r09 = _contrato_predicciones(r09, MODELO_R09, "emision_publicada_no_algoritmo")
    macro = _contrato_predicciones(macro, MODELO_MACRO, "macro_legacy_postgres_auto_asof_v2")
    ocurrencia = _contrato_predicciones(ocurrencia, NOMBRE_MODELO, VERSION_MODELO)
    ocurrencia["version_fuente"] = "snapshot_40_universo_R09_Macro_h1"

    predicciones = pd.concat([r09, macro, ocurrencia], ignore_index=True, sort=False)
    clave = ["modelo", *CLAVES]
    if predicciones.duplicated(clave).any():
        duplicados = int(predicciones.duplicated(clave).sum())
        raise ValueError(f"La corrida contiene {duplicados} duplicados modelo-lote-semana.")

    comparaciones = metricas_pareadas_modelos(
        predicciones, modelo_base=MODELO_R09, modelo_candidato=NOMBRE_MODELO
    )
    metricas = []
    for modelo in (MODELO_R09, MODELO_MACRO, NOMBRE_MODELO):
        parte = predicciones[predicciones.modelo.eq(modelo)]
        semanal = parte.groupby("fecha_objetivo", as_index=False).agg(
            real_kg=("real_kg", "sum"), p50_kg=("p50_kg", "sum")
        )
        metricas.append(
            {
                "modelo": modelo,
                "banda_horizonte": "operativo",
                "n": len(semanal),
                **metricas_semanales(semanal),
            }
        )

    resumen_corrida = {
        "snapshot_id": SNAPSHOT_ID,
        "runs_origen": list(RUNS_MACRO),
        "modelos": [MODELO_R09, MODELO_MACRO, NOMBRE_MODELO],
        "campanias": sorted(predicciones.campania.astype(str).unique()),
        "filas_universo_lote_semana": int(universo.groupby(CLAVES).ngroups),
        "semanas_universo": int(universo.fecha_objetivo.nunique()),
        "filas": {
            modelo: int(predicciones[predicciones.modelo.eq(modelo)].shape[0])
            for modelo in predicciones.modelo.unique()
        },
        "ocurrencia_semanas": int(len(resumen)),
        "metricas": metricas,
        "comparaciones": comparaciones.to_dict("records"),
    }
    return predicciones, resumen_corrida


def persistir(dry_run: bool = False) -> dict:
    predicciones, resumen = construir_corrida()
    if dry_run:
        return resumen
    repo = RepositorioAnalytics(settings.postgres_dsn())
    run_id = repo.crear_run(
        SNAPSHOT_ID,
        "backtest",
        {
            "modelos": resumen["modelos"],
            "campanias": resumen["campanias"],
            "universo": "interseccion_R09_Macro_horizonte_1_real_evaluable",
            "horizonte_semanas": 1,
            "semanas_calentamiento": 5,
            "modelo_hibrido": NOMBRE_MODELO,
            "version_modelo": VERSION_MODELO,
            "runs_origen": list(RUNS_MACRO),
            "r09": "emision_publicada_referencia_no_algoritmo",
            "nota": (
                "corrida común para comparar OcurrenciaOnline contra R09 sin cambiar denominador"
            ),
        },
    )
    try:
        repo.guardar_predicciones(run_id, predicciones)
        repo.guardar_metricas(
            run_id,
            pd.DataFrame(resumen["metricas"]),
        )
        repo.guardar_metricas_comparacion(
            run_id,
            pd.DataFrame(resumen["comparaciones"]),
        )
        repo.finalizar_run(run_id, "succeeded")
    except Exception as exc:
        repo.finalizar_run(run_id, "failed", str(exc))
        raise
    resumen["run_id"] = run_id
    return resumen


__all__ = [
    "CLAVES",
    "MODELO_MACRO",
    "MODELO_R09",
    "RUNS_MACRO",
    "SNAPSHOT_ID",
    "construir_corrida",
    "persistir",
]
