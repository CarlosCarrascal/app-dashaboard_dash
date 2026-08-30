"""Servicio reusable para persistir una corrida de replay con R09 reconstruida.

La corrida anterior conserva una selección histórica incompleta de R09. Este servicio no
la modifica: clona los modelos evaluados de la última corrida completa y reemplaza solo
la referencia R09 por la selección vintage obtenida desde ``stg.v_r09_forecast``.

Las filas reales sin emisión R09 se conservan como ``SIN_EMISION_R09`` con p50=0 y
``emitio_prediccion=false``. Eso permite medir por separado cobertura y precisión sin
inventar un pronóstico.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from analitica import settings
from analitica.proyeccion.metricas import (
    metricas_cobertura_operacional,
    metricas_pronostico,
)
from analitica.proyeccion.persistencia import RepositorioAnalytics

MODELO_R09 = "R09_publicado"
CONFIG_FUENTE = "stg.v_r09_forecast"


def _parsear_argumentos(descripcion: str) -> None:
    argparse.ArgumentParser(description=descripcion).parse_args()


def _leer_base(conexion) -> tuple[int, int, pd.DataFrame]:
    base = pd.read_sql_query(
        """
        SELECT run_id, snapshot_id
        FROM analytics.forecast_run
        WHERE tipo = 'backtest'
          AND estado IN ('succeeded', 'published')
          AND configuracion->>'modelo_hibrido' = 'HibridoOcurrenciaOnline_v2'
          AND COALESCE(configuracion->>'r09_vintage_source', '') <> %s
        ORDER BY fin DESC NULLS LAST, run_id DESC
        LIMIT 1
        """,
        conexion,
        params=(CONFIG_FUENTE,),
    )
    if base.empty:
        raise RuntimeError("No existe una corrida base completa con HibridoOcurrenciaOnline_v2")
    run_id = int(base.iloc[0].run_id)
    snapshot_id = int(base.iloc[0].snapshot_id)
    predicciones = pd.read_sql_query(
        """
        SELECT modelo, version_modelo, campania, empresa, fundo, modulo, lote, lote_id,
               fecha_emision, fecha_objetivo, horizonte_semanas, banda_horizonte,
               version_fuente, p10_kg, p50_kg, p90_kg, real_kg, plantas,
               frutos_por_planta, peso_baya_g, confianza, componentes, origen_emision,
               tipo_prediccion, es_replay_ciego, es_curva_stitched, estado_evaluacion
        FROM analytics.prediction
        WHERE run_id = %s AND modelo <> %s
        """,
        conexion,
        params=(run_id, MODELO_R09),
    )
    if predicciones.empty:
        raise RuntimeError(f"La corrida base {run_id} no contiene modelos para clonar")
    return run_id, snapshot_id, predicciones


def _leer_r09_emitido(conexion) -> pd.DataFrame:
    """Obtiene una emisión estándar por lote-semana, sin variantes ni duplicados."""

    return pd.read_sql_query(
        """
        WITH versiones AS (
            SELECT r.*,
                   (regexp_match(r.version, '^[Ss]0*([0-9]+)$'))[1]::integer
                       AS numero_version,
                   date_trunc('week', r.fecha_cos)::date AS semana_objetivo
            FROM stg.v_r09_forecast r
            WHERE r.version ~* '^S0*[0-9]+$'
              AND r.lote_id IS NOT NULL
              AND r.semana IS NOT NULL
              AND r.fecha_cos IS NOT NULL
              AND r.kg IS NOT NULL
        ), reales AS (
            SELECT h.campania, h.lote_id,
                   date_trunc('week', h.fecha)::date AS semana_objetivo,
                   SUM(h.kg)::double precision AS real_kg
            FROM stg.v_h01_cosecha h
            WHERE h.lote_id IS NOT NULL AND h.fecha IS NOT NULL
            GROUP BY h.campania, h.lote_id, date_trunc('week', h.fecha)::date
        ), candidatos AS (
            SELECT 'R09_publicado'::text AS modelo,
                   'R09_publicado_vintage_v1'::text AS version_modelo,
                   r.version AS version_fuente,
                   r.campania,
                   d.empresa, d.fundo, d.modulo, d.lote, r.lote_id,
                   (r.semana_objetivo
                    - ((r.semana - r.numero_version) * INTERVAL '7 days'))::date
                       AS fecha_emision,
                   r.semana_objetivo AS fecha_objetivo,
                   GREATEST(0, r.semana - r.numero_version) AS horizonte_semanas,
                   CASE
                       WHEN r.semana - r.numero_version <= 2 THEN 'operativo'
                       WHEN r.semana - r.numero_version <= 6 THEN 'planificacion'
                       ELSE 'escenario'
                   END AS banda_horizonte,
                   r.kg::double precision AS p50_kg,
                   reales.real_kg,
                   (r.semana_objetivo
                    - ((r.semana - r.numero_version) * INTERVAL '7 days'))::date
                       AS origen_emision
            FROM versiones r
            JOIN reales
              ON reales.campania = r.campania
             AND reales.lote_id = r.lote_id
             AND reales.semana_objetivo = r.semana_objetivo
            LEFT JOIN dim.lote d ON d.lote_id = r.lote_id
            WHERE r.numero_version <= r.semana
        )
        SELECT DISTINCT ON (modelo, campania, lote_id, fecha_objetivo)
               modelo, version_modelo, version_fuente, campania,
               empresa, fundo, modulo, lote, lote_id,
               fecha_emision, fecha_objetivo, horizonte_semanas,
               banda_horizonte, p50_kg, real_kg, origen_emision
        FROM candidatos
        ORDER BY modelo, campania, lote_id, fecha_objetivo,
                 horizonte_semanas ASC, fecha_emision DESC
        """,
        conexion,
    )


def _leer_real_universo(conexion) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT h.campania, h.lote_id,
               date_trunc('week', h.fecha)::date AS fecha_objetivo,
               d.empresa, d.fundo, d.modulo, d.lote,
               SUM(h.kg)::double precision AS real_kg
        FROM stg.v_h01_cosecha h
        LEFT JOIN dim.lote d ON d.lote_id = h.lote_id
        WHERE h.lote_id IS NOT NULL AND h.fecha IS NOT NULL
        GROUP BY h.campania, h.lote_id, date_trunc('week', h.fecha)::date,
                 d.empresa, d.fundo, d.modulo, d.lote
        """,
        conexion,
    )


def _preparar_r09(real: pd.DataFrame, emitido: pd.DataFrame) -> pd.DataFrame:
    claves = ["campania", "lote_id", "fecha_objetivo"]
    if real.empty:
        raise RuntimeError("No hay cosecha real para construir el universo R09")
    tabla = real.merge(
        emitido,
        on=claves,
        how="left",
        suffixes=("_real", ""),
        validate="one_to_one",
    )
    tabla["modelo"] = MODELO_R09
    tabla["version_modelo"] = tabla["version_modelo"].fillna("R09_publicado_vintage_v1")
    tabla["version_fuente"] = tabla["version_fuente"].fillna("SIN_EMISION_R09")
    tabla["empresa"] = tabla["empresa"].fillna(tabla.get("empresa_real"))
    tabla["fundo"] = tabla["fundo"].fillna(tabla.get("fundo_real"))
    tabla["modulo"] = tabla["modulo"].fillna(tabla.get("modulo_real"))
    tabla["lote"] = tabla["lote"].fillna(tabla.get("lote_real"))
    tabla["real_kg"] = tabla["real_kg"].fillna(tabla["real_kg_real"])
    emitio = tabla["p50_kg"].notna()
    tabla["p50_kg"] = tabla["p50_kg"].fillna(0.0).clip(lower=0.0)
    tabla["fecha_emision"] = tabla["fecha_emision"].fillna(
        pd.to_datetime(tabla["fecha_objetivo"]) - pd.Timedelta(days=7)
    )
    tabla["origen_emision"] = tabla["origen_emision"].fillna(tabla["fecha_emision"])
    tabla["horizonte_semanas"] = (
        pd.to_numeric(tabla["horizonte_semanas"], errors="coerce").fillna(0).astype(int)
    )
    tabla["banda_horizonte"] = tabla["banda_horizonte"].fillna("operativo")
    tabla["p10_kg"] = np.nan
    tabla["p90_kg"] = np.nan
    tabla["plantas"] = np.nan
    tabla["frutos_por_planta"] = np.nan
    tabla["peso_baya_g"] = np.nan
    tabla["confianza"] = "baja"
    tabla["tipo_prediccion"] = "replay"
    tabla["es_replay_ciego"] = True
    tabla["es_curva_stitched"] = True
    tabla["estado_evaluacion"] = "evaluada"
    tabla["componentes"] = [
        {
            "referencia_publicada": True,
            "emitio_prediccion": bool(valor),
            "fuente_r09": CONFIG_FUENTE,
            "politica_variantes": "Sxx estándar; variantes excluidas",
            "ausencia_evaluada_como_cero": not bool(valor),
        }
        for valor in emitio
    ]
    columnas = [
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
        "componentes",
        "origen_emision",
        "tipo_prediccion",
        "es_replay_ciego",
        "es_curva_stitched",
        "estado_evaluacion",
    ]
    return tabla[columnas]


def _metricas(tabla: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for (modelo, campania), parte in tabla.groupby(["modelo", "campania"], sort=True):
        semanal = parte.groupby("fecha_objetivo", as_index=False).agg(
            real_kg=("real_kg", "sum"),
            p50_kg=("p50_kg", "sum"),
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


def persistir() -> dict[str, object]:
    """Detecta, reconstruye y persiste el replay corregido; devuelve su resumen."""

    import psycopg

    with psycopg.connect(settings.postgres_dsn()) as conexion:
        existente = pd.read_sql_query(
            """
            SELECT run_id, snapshot_id
            FROM analytics.forecast_run
            WHERE estado IN ('succeeded', 'published')
              AND configuracion->>'r09_vintage_source' = %s
            ORDER BY run_id DESC LIMIT 1
            """,
            conexion,
            params=(CONFIG_FUENTE,),
        )
        if not existente.empty:
            return {"run_id": int(existente.iloc[0].run_id), "reused": True}
        base_run, snapshot_id, base = _leer_base(conexion)
        r09 = _preparar_r09(_leer_real_universo(conexion), _leer_r09_emitido(conexion))

    predicciones = pd.concat([base, r09], ignore_index=True, sort=False)
    claves = ["modelo", "campania", "lote_id", "fecha_emision", "fecha_objetivo", "version_fuente"]
    if predicciones.duplicated(claves).any():
        duplicados = int(predicciones.duplicated(claves).sum())
        raise ValueError(f"La corrida corregida contiene {duplicados} claves duplicadas")

    metricas = _metricas(predicciones)
    repo = RepositorioAnalytics(settings.postgres_dsn())
    run_id = repo.crear_run(
        snapshot_id,
        "backtest",
        {
            "base_run": base_run,
            "r09": "referencia_publicada_no_algoritmo",
            "r09_vintage_source": CONFIG_FUENTE,
            "r09_variant_policy": "Sxx estándar; variantes excluidas",
            "r09_missing_policy": "SIN_EMISION_R09 explícito; p50=0 solo para WAPE operacional",
            "universo": "cosecha_real_completa_por_campania",
            "correccion": "reconstruccion_r09_sin_reentrenar_modelos",
        },
    )
    try:
        repo.guardar_predicciones(run_id, predicciones)
        repo.guardar_metricas(run_id, metricas)
        repo.finalizar_run(run_id, "succeeded")
    except Exception as exc:
        repo.finalizar_run(run_id, "failed", str(exc))
        raise

    r09_run = predicciones[predicciones.modelo.eq(MODELO_R09)]
    return {
        "run_id": run_id,
        "base_run": base_run,
        "filas": len(predicciones),
        "r09_filas": len(r09_run),
        "r09_emitidas": int(sum(bool(x.get("emitio_prediccion")) for x in r09_run.componentes)),
        "r09_sin_emision": int(
            sum(not bool(x.get("emitio_prediccion")) for x in r09_run.componentes)
        ),
        "campanias": sorted(predicciones.campania.dropna().astype(str).unique()),
    }


__all__ = [
    "CONFIG_FUENTE",
    "MODELO_R09",
    "persistir",
]
