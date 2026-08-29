"""Fachada de lecturas operativas heredadas para el dashboard.

Los servicios de página consumen funciones de este módulo y no conocen las tablas ``stg``
ni ``dim``. Esta es la única frontera explícita para consultas que todavía no tienen una
vista ``reporting`` equivalente; moverlas aquí no cambia SQL, columnas ni resultados.
"""

from __future__ import annotations

import pandas as pd

from .consultas import consulta, consulta_si_existe


def cosecha_real_analitica(conexion) -> pd.DataFrame:
    return consulta_si_existe(
        conexion,
        "stg.v_h01_cosecha",
        """
        SELECT h.campania, date_trunc('week', h.fecha)::date AS fecha_objetivo,
               h.lote_id, d.empresa, d.fundo, d.modulo, d.lote,
               SUM(h.kg)::double precision AS real_kg
        FROM stg.v_h01_cosecha h
        LEFT JOIN dim.lote d USING (lote_id)
        WHERE h.lote_id IS NOT NULL AND h.fecha IS NOT NULL
        GROUP BY h.campania, date_trunc('week', h.fecha)::date, h.lote_id,
                 d.empresa, d.fundo, d.modulo, d.lote
        """,
    )


def cosecha_real_operativa(conexion) -> pd.DataFrame:
    return consulta_si_existe(
        conexion,
        "stg.v_h01_cosecha",
        """
        SELECT h.campania, date_trunc('week', h.fecha)::date AS fecha_objetivo,
               h.lote_id, d.empresa, d.fundo, d.modulo, d.lote,
               SUM(h.kg)::double precision AS real_kg,
               MAX(h.fecha)::date AS ultima_fecha_real
        FROM stg.v_h01_cosecha h
        LEFT JOIN dim.lote d USING (lote_id)
        WHERE h.lote_id IS NOT NULL AND h.fecha IS NOT NULL
          AND h.campania IN (
              SELECT DISTINCT campania
              FROM reporting.proyeccion_operativa_detalle
          )
        GROUP BY h.campania, date_trunc('week', h.fecha)::date, h.lote_id,
                 d.empresa, d.fundo, d.modulo, d.lote
        """,
    )


def lotes(conexion) -> pd.DataFrame:
    return consulta(
        conexion,
        """
        SELECT lote_id, clave_negocio, empresa, fundo, modulo, turno, lote,
               variedad, area_ha, n_plantas
        FROM dim.lote
        WHERE NOT es_sentinel AND NOT es_ficticio
        """,
    )


def hibrido_v2(conexion) -> pd.DataFrame:
    return consulta_si_existe(
        conexion,
        "analytics.prediction",
        """
        WITH corrida AS (
            SELECT p.run_id
            FROM analytics.prediction p
            JOIN analytics.forecast_run r USING (run_id)
            JOIN analytics.model_series_release l
              ON l.run_id = p.run_id
             AND l.campania = p.campania
             AND l.modelo = p.modelo
             AND l.version_modelo = COALESCE(p.version_modelo, 'sin_version')
            WHERE p.modelo = 'HibridoOcurrenciaOnline_v2'
              AND p.version_modelo = 'macro_hurdle_online_full_coverage_v2'
              AND r.estado IN ('succeeded', 'published')
              AND l.uso IN ('historico', 'referencia')
              AND l.activo
              AND l.estado = 'approved'
              AND l.estado_evaluacion = 'passed'
            GROUP BY p.run_id
            ORDER BY MAX(p.fecha_emision) DESC, p.run_id DESC
            LIMIT 1
        )
        SELECT p.prediction_id, p.run_id, p.modelo, p.version_modelo,
               p.version_fuente, p.campania, p.empresa,
               reporting.fundo_operativo(p.fundo) AS fundo,
               p.fundo AS fundo_fuente, p.modulo, p.lote, p.lote_id,
               p.fecha_emision, p.fecha_objetivo, p.horizonte_semanas,
               p.banda_horizonte, p.p10_kg, p.p50_kg, p.p90_kg, p.real_kg,
               p.plantas, p.frutos_por_planta, p.peso_baya_g,
               p.componentes, p.confianza, r.snapshot_id,
               r.mlflow_run_id, r.codigo_commit, r.fin AS generado_en,
               r.configuracion, d.turno, d.variedad, d.area_ha, d.n_plantas
        FROM analytics.prediction p
        JOIN corrida c ON c.run_id = p.run_id
        JOIN analytics.forecast_run r ON r.run_id = p.run_id
        LEFT JOIN dim.lote d USING (lote_id)
        WHERE p.modelo = 'HibridoOcurrenciaOnline_v2'
          AND p.version_modelo = 'macro_hurdle_online_full_coverage_v2'
          AND p.horizonte_semanas BETWEEN 0 AND 6
        ORDER BY p.fecha_objetivo, fundo, p.modulo, p.lote_id
        """,
    )


def _snapshots_analiticos_access(conexion) -> dict[str, int]:
    """Resuelve el snapshot analítico Access de cada campaña disponible."""
    fuente = consulta_si_existe(
        conexion,
        "raw.v_ultimo_snapshot_fuente",
        """
        SELECT campania, source_snapshot_id
        FROM raw.v_ultimo_snapshot_fuente
        WHERE tipo = 'access'
        ORDER BY extraido_en DESC, source_snapshot_id DESC
        """,
    )
    if fuente.empty:
        return {}
    snapshot = consulta_si_existe(
        conexion,
        "analytics.dataset_snapshot",
        """
        SELECT snapshot_id, cobertura->>'source_snapshot_id' AS source_snapshot_id
        FROM analytics.dataset_snapshot
        ORDER BY creado_en DESC, snapshot_id DESC
        """,
    )
    if snapshot.empty:
        return {}
    por_source = {}
    for fila in snapshot.itertuples(index=False):
        if pd.notna(fila.source_snapshot_id):
            por_source.setdefault(str(fila.source_snapshot_id), int(fila.snapshot_id))
    salida = {}
    for fila in fuente.itertuples(index=False):
        if pd.notna(fila.campania) and pd.notna(fila.source_snapshot_id):
            snapshot_id = por_source.get(str(fila.source_snapshot_id))
            if snapshot_id is not None:
                salida[str(fila.campania)] = snapshot_id
    return salida


def r09_referencia(conexion) -> pd.DataFrame:
    snapshot_por_campania = _snapshots_analiticos_access(conexion)
    tabla = consulta_si_existe(
        conexion,
        "stg.v_r09_forecast",
        """
        WITH versiones_oficiales AS (
            SELECT r.*,
                   (regexp_match(r.version, '^[Ss]0*([0-9]+)$'))[1]::integer
                       AS numero_version
            FROM stg.v_r09_forecast r
            WHERE r.version ~* '^[Ss]0*[0-9]+$'
              AND r.semana IS NOT NULL
        ), version_por_semana AS (
            SELECT campania, semana, MAX(numero_version) AS numero_version
            FROM versiones_oficiales
            WHERE numero_version <= semana
            GROUP BY campania, semana
        ), referencia AS (
            SELECT r.*
            FROM versiones_oficiales r
            JOIN version_por_semana v
              ON v.campania = r.campania
             AND v.semana = r.semana
             AND v.numero_version = r.numero_version
        )
        SELECT 'R09_publicado'::text AS modelo,
               r.version AS version_fuente,
               r.campania, d.empresa, d.fundo, d.modulo, d.lote,
               r.lote_id,
               to_date(substring(r.campania from '[0-9]{4}') ||
                       lpad(r.numero_version::text, 2, '0') || '1', 'IYYYIWID')
                   AS fecha_emision,
               date_trunc('week', r.fecha_cos)::date AS fecha_objetivo,
               GREATEST(0, r.semana - r.numero_version) AS horizonte_semanas,
               CASE
                   WHEN r.semana - r.numero_version <= 2 THEN 'operativo'
                   WHEN r.semana - r.numero_version <= 6 THEN 'planificacion'
                   ELSE 'escenario'
               END AS banda_horizonte,
               NULL::double precision AS p10_kg,
               r.kg::double precision AS p50_kg,
               NULL::double precision AS p90_kg,
               NULL::double precision AS real_kg,
               CASE WHEN r.frutos_por_planta > 0
                    THEN r.frutos_total / r.frutos_por_planta END AS plantas,
               r.frutos_por_planta,
               r.peso_baya AS peso_baya_g,
               jsonb_build_object(
                   'fuente', 'Access · R09_Forecast_Semanal',
                   'version', r.version
               ) AS componentes,
               'referencia'::text AS confianza,
               NULL::bigint AS snapshot_id,
               NULL::timestamptz AS generado_en
        FROM referencia r
        LEFT JOIN dim.lote d USING (lote_id)
        WHERE r.fecha_cos IS NOT NULL
        ORDER BY fecha_objetivo, d.fundo, d.modulo, r.lote_id
        """,
    )
    if not tabla.empty and snapshot_por_campania:
        tabla["snapshot_id"] = tabla["campania"].map(snapshot_por_campania).astype("Int64")
    return tabla


__all__ = [
    "cosecha_real_analitica",
    "cosecha_real_operativa",
    "hibrido_v2",
    "lotes",
    "r09_referencia",
]
