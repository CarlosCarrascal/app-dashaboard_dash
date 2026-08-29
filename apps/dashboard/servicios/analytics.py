"""Lectura pequeña y tolerante del contrato de negocio ``analytics``.

El dashboard nunca entrena ni reconstruye resultados. Solo consume corridas finalizadas y
expone el origen efectivo del snapshot; si PostgreSQL no está disponible, lo comunica en
vez de caer silenciosamente a Excel.
"""

from __future__ import annotations

import json
import time
from contextlib import suppress
from functools import lru_cache
from pathlib import Path

import pandas as pd

from analitica import settings

from .consultas import consulta as _consulta
from .consultas import consulta_si_existe as _consulta_si_existe
from .reporting import cosecha_real_analitica, lotes

RAIZ = Path(__file__).resolve().parents[3]


def _artefactos_de(conexion, tipo: str, nombres: dict[str, str]) -> dict[str, pd.DataFrame]:
    """Lee los parquet de detalle de la última corrida de un tipo.

    El detalle de relaciones y de explicabilidad no cabe en `analytics.metric`: son tablas
    con estructura propia (una fila por hipótesis, por familia de variables o por rezago).
    Viven como parquet dentro del paquete de auditoría de la corrida.

    La base sigue siendo la autoridad sobre **qué** corrida mirar; el disco solo aporta el
    detalle de esa corrida concreta. Así no se pierde la trazabilidad: si la base dice que
    la corrida vigente es la 23, se leen los artefactos de la 23 y de ninguna otra.
    """
    salida = {clave: pd.DataFrame() for clave in nombres}
    with conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT a.uri FROM analytics.artifact a
            JOIN analytics.forecast_run r USING (run_id)
            WHERE r.tipo = %s
              AND r.estado IN ('succeeded', 'published')
              AND COALESCE(r.configuracion->>'publicacion', 'official') <> 'experimental'
            ORDER BY r.run_id DESC, a.artifact_id DESC LIMIT 1
            """,
            (tipo,),
        )
        fila = cursor.fetchone()
    if not fila or not fila[0]:
        return salida
    # El ZIP y el directorio con los parquet son hermanos: mismo nombre, sin extensión.
    directorio = Path(str(fila[0]))
    directorio = directorio.with_suffix("") if directorio.suffix else directorio
    if not directorio.is_dir():
        return salida
    for clave, archivo in nombres.items():
        ruta = directorio / archivo
        if ruta.is_file():
            with suppress(Exception):
                salida[clave] = pd.read_parquet(ruta)
    return salida


def _catalogo() -> pd.DataFrame:
    ruta = RAIZ / "docs" / "cientifico" / "catalogo_evidencia.json"
    if not ruta.is_file():
        return pd.DataFrame()
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    return pd.DataFrame(contenido.get("estudios", []))


@lru_cache(maxsize=2)
def _estado_cache(minuto: int) -> dict[str, object]:
    del minuto
    resultado: dict[str, object] = {
        "error": None,
        "runs": pd.DataFrame(),
        "decisiones": pd.DataFrame(),
        "metricas": pd.DataFrame(),
        "metricas_comparacion": pd.DataFrame(),
        "replay": pd.DataFrame(),
        "replay_detalle": pd.DataFrame(),
        "replay_meta": pd.DataFrame(),
        "curva_historica": pd.DataFrame(),
        "claims": pd.DataFrame(),
        "proyeccion": pd.DataFrame(),
        "proyeccion_experimental": pd.DataFrame(),
        "proyeccion_operativa_semana": pd.DataFrame(),
        "cosecha_real": pd.DataFrame(),
        "cosecha_real_semana": pd.DataFrame(),
        "evidencia_features": pd.DataFrame(),
        "fuente_access": pd.DataFrame(),
        "fuente_access_control": pd.DataFrame(),
        "validacion_operativa": pd.DataFrame(),
        "escenarios_guardados": pd.DataFrame(),
        "lotes": pd.DataFrame(),
        "calidad": pd.DataFrame(),
        "artefactos": pd.DataFrame(),
        "catalogo": _catalogo(),
        # Detalle de relaciones y de importancia de variables, desde los parquet de la
        # corrida correspondiente.
        "relaciones": pd.DataFrame(),
        "inferencia": pd.DataFrame(),
        "matriz": pd.DataFrame(),
        "packing": pd.DataFrame(),
        "ensamblaje": pd.DataFrame(),
        "ablaciones": pd.DataFrame(),
        "permutacion": pd.DataFrame(),
        "shap": pd.DataFrame(),
        "fuentes": pd.DataFrame(),
    }
    dsn = settings.postgres_dsn()
    if not dsn:
        resultado["error"] = "PostgreSQL no está configurado; no se activa un fallback implícito."
        return resultado
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=3) as conexion:
            resultado["runs"] = _consulta(
                conexion,
                """
                SELECT r.run_id, r.tipo, r.estado, r.inicio, r.fin, r.codigo_commit,
                       r.mlflow_run_id, s.snapshot_id, s.fuente, s.firma AS firma_snapshot,
                       s.corte_datos, s.cobertura, s.advertencias
                FROM analytics.forecast_run r
                JOIN analytics.dataset_snapshot s USING (snapshot_id)
                ORDER BY r.run_id DESC LIMIT 20
            """,
            )
            decisiones = _consulta(
                conexion,
                """
                SELECT banda_horizonte, campeon, challenger, resultado, justificacion,
                       regla, metricas, decidido_en, run_id, firma_snapshot, fuente,
                       codigo_commit, mlflow_run_id
                FROM reporting.trazabilidad_modelo
                WHERE vigente ORDER BY banda_horizonte
                """,
            )
            if not decisiones.empty:
                detalle = pd.json_normalize(decisiones.metricas).add_prefix("decision_")
                decisiones = pd.concat(
                    [decisiones.reset_index(drop=True), detalle.reset_index(drop=True)], axis=1
                )
            resultado["decisiones"] = decisiones
            metricas = _consulta(
                conexion,
                """
                WITH ultima AS (
                    SELECT DISTINCT ON (l.campania)
                           r.run_id, l.campania
                    FROM analytics.forecast_run r
                    JOIN analytics.model_series_release l ON l.run_id = r.run_id
                    JOIN analytics.evaluation_contract c
                      ON c.evaluation_contract_id = l.evaluation_contract_id
                    WHERE r.tipo = 'backtest'
                      AND r.estado IN ('succeeded', 'published')
                      AND l.uso IN ('historico', 'referencia')
                      AND l.activo
                      AND l.estado = 'approved'
                      AND l.estado_evaluacion = 'passed'
                      AND c.estado = 'approved'
                    ORDER BY l.campania, r.fin DESC NULLS LAST, r.run_id DESC
                )
                SELECT m.run_id, u.campania, m.modelo, m.banda_horizonte,
                       m.metrica, m.valor, m.n
                FROM analytics.metric m
                JOIN ultima u USING (run_id)
            """,
            )
            if not metricas.empty:
                resultado["metricas"] = (
                    metricas.pivot_table(
                        index=["run_id", "campania", "modelo", "banda_horizonte", "n"],
                        columns="metrica",
                        values="valor",
                        aggfunc="first",
                    )
                    .reset_index()
                    .rename_axis(columns=None)
                )
            resultado["metricas_comparacion"] = _consulta_si_existe(
                conexion,
                "reporting.comparacion_modelos_historica",
                """
                WITH ultima AS (
                    SELECT DISTINCT ON (l.campania)
                           r.run_id, l.campania
                    FROM analytics.forecast_run r
                    JOIN analytics.model_series_release l ON l.run_id = r.run_id
                    JOIN analytics.evaluation_contract c
                      ON c.evaluation_contract_id = l.evaluation_contract_id
                    WHERE r.tipo = 'backtest'
                      AND r.estado IN ('succeeded', 'published')
                      AND l.uso IN ('historico', 'referencia')
                      AND l.activo
                      AND l.estado = 'approved'
                      AND l.estado_evaluacion = 'passed'
                      AND c.estado = 'approved'
                    ORDER BY l.campania, r.fin DESC NULLS LAST, r.run_id DESC
                )
                SELECT m.run_id, u.campania, m.modelo, m.banda_horizonte, m.n, m.wape, m.mae_kg,
                       m.sesgo_pct, m.cobertura_80, m.mase,
                       NULL::double precision AS escala_naive,
                       m.volumen_real_kg, m.universo, m.modelo_base
                FROM reporting.comparacion_modelos_historica m
                JOIN ultima u USING (run_id)
                ORDER BY banda_horizonte, modelo
                """,
            )
            # Replay agregado por emisión y semana. La cosecha real se une aquí solo
            # después de que la fecha objetivo ya ocurrió; nunca alimenta la proyección
            # operativa. Sirve para que la mesa muestre cómo habría funcionado cada
            # alternativa en una fecha histórica concreta, no solo el plan futuro.
            resultado["replay"] = _consulta_si_existe(
                conexion,
                "analytics.prediction",
                """
                WITH ultima AS (
                    SELECT DISTINCT ON (l.campania)
                           r.run_id, l.campania
                    FROM analytics.forecast_run r
                    JOIN analytics.model_series_release l ON l.run_id = r.run_id
                    JOIN analytics.evaluation_contract c
                      ON c.evaluation_contract_id = l.evaluation_contract_id
                    WHERE r.tipo = 'backtest'
                      AND r.estado IN ('succeeded', 'published')
                      AND l.uso IN ('historico', 'referencia')
                      AND l.activo
                      AND l.estado = 'approved'
                      AND l.estado_evaluacion = 'passed'
                      AND c.estado = 'approved'
                    ORDER BY l.campania, r.fin DESC NULLS LAST, r.run_id DESC
                )
                SELECT p.run_id, u.campania, p.modelo, p.fecha_emision,
                       date_trunc('week', p.fecha_objetivo)::date AS fecha_objetivo,
                       p.horizonte_semanas, p.banda_horizonte,
                       MAX(p.version_fuente) AS version_fuente,
                       SUM(p.p10_kg)::double precision AS p10_kg,
                       SUM(p.p50_kg)::double precision AS p50_kg,
                       SUM(p.p90_kg)::double precision AS p90_kg,
                       SUM(p.real_kg)::double precision AS real_kg,
                       COUNT(*)::bigint AS n_lotes
                FROM analytics.prediction p
                JOIN ultima u
                  ON u.run_id = p.run_id
                 AND u.campania = p.campania
                WHERE p.real_kg IS NOT NULL
                  AND p.modelo IN ('R09_publicado', 'ModeloOperativoActual_v1',
                                   'MacroLegacy_v1', 'HibridoLegacyResidual_v1',
                                   'FenologicoComponentes_v1', 'HibridoParametrosAsOf_v1')
                GROUP BY p.run_id, u.campania, p.modelo, p.fecha_emision,
                         date_trunc('week', p.fecha_objetivo)::date,
                         p.horizonte_semanas, p.banda_horizonte
                ORDER BY p.fecha_emision, fecha_objetivo, p.modelo
                """,
            )
            # Vintage histórico a grano lote-semana. Se elige para cada objetivo la
            # última emisión que existía antes de cosecharlo. Esta tabla alimenta la
            # comparación real vs proyección y permite filtrar sin volver a consultar
            # PostgreSQL desde cada callback.
            resultado["replay_detalle"] = _consulta_si_existe(
                conexion,
                "analytics.prediction",
                """
                WITH ultima AS (
                    SELECT DISTINCT ON (l.campania)
                           r.run_id, l.campania
                    FROM analytics.forecast_run r
                    JOIN analytics.model_series_release l ON l.run_id = r.run_id
                    JOIN analytics.evaluation_contract c
                      ON c.evaluation_contract_id = l.evaluation_contract_id
                    WHERE r.tipo = 'backtest'
                      AND r.estado IN ('succeeded', 'published')
                      AND l.uso IN ('historico', 'referencia')
                      AND l.activo
                      AND l.estado = 'approved'
                      AND l.estado_evaluacion = 'passed'
                      AND c.estado = 'approved'
                    ORDER BY l.campania, r.fin DESC NULLS LAST, r.run_id DESC
                ), candidatos AS (
                    SELECT p.run_id, p.modelo, p.version_modelo, p.version_fuente,
                           p.campania, p.empresa, p.fundo, p.modulo, p.lote, p.lote_id,
                           p.fecha_emision, p.fecha_objetivo, p.horizonte_semanas,
                           p.banda_horizonte, p.p50_kg, p.real_kg,
                           COALESCE(p.origen_emision, p.fecha_emision) AS origen_emision
                    FROM analytics.prediction p
                    JOIN ultima u
                      ON u.run_id = p.run_id
                     AND u.campania = p.campania
                    WHERE p.real_kg IS NOT NULL
                      AND p.modelo IN ('R09_publicado', 'ModeloOperativoActual_v1',
                                       'MacroLegacy_v1', 'HibridoLegacyResidual_v1',
                                       'FenologicoComponentes_v1', 'HibridoParametrosAsOf_v1')
                      AND COALESCE(p.origen_emision, p.fecha_emision) < p.fecha_objetivo
                )
                SELECT DISTINCT ON (modelo, campania, lote_id, fecha_objetivo)
                       run_id, modelo, version_modelo, version_fuente, campania,
                       empresa, fundo, modulo, lote, lote_id, fecha_emision,
                       fecha_objetivo, horizonte_semanas, banda_horizonte,
                       p50_kg, real_kg, origen_emision
                FROM candidatos
                ORDER BY modelo, campania, lote_id, fecha_objetivo,
                         origen_emision DESC, fecha_emision DESC
                """,
            )
            resultado["curva_historica"] = _consulta_si_existe(
                conexion,
                "reporting.curva_historica_modelos",
                """
                SELECT campania, fecha_objetivo, modelo, p10_kg, p50_kg, p90_kg,
                       real_kg, origen_emision_min, origen_emision_max, n_lotes, tipo_curva
                FROM reporting.curva_historica_modelos
                ORDER BY campania, fecha_objetivo, modelo
                """,
            )
            resultado["replay_meta"] = _consulta_si_existe(
                conexion,
                "analytics.forecast_run",
                """
                SELECT r.run_id, r.fin, r.codigo_commit, r.mlflow_run_id,
                       u.campania,
                       s.snapshot_id, s.fuente, s.firma AS firma_snapshot,
                       s.corte_datos, s.advertencias
                FROM analytics.forecast_run r
                JOIN analytics.dataset_snapshot s USING (snapshot_id)
                JOIN (
                    SELECT DISTINCT ON (l.campania)
                           r2.run_id, l.campania
                    FROM analytics.forecast_run r2
                    JOIN analytics.model_series_release l ON l.run_id = r2.run_id
                    JOIN analytics.evaluation_contract c
                      ON c.evaluation_contract_id = l.evaluation_contract_id
                    WHERE r2.tipo = 'backtest'
                      AND r2.estado IN ('succeeded', 'published')
                      AND l.uso IN ('historico', 'referencia')
                      AND l.activo
                      AND l.estado = 'approved'
                      AND l.estado_evaluacion = 'passed'
                      AND c.estado = 'approved'
                    ORDER BY l.campania, r2.fin DESC NULLS LAST, r2.run_id DESC
                ) u USING (run_id)
                ORDER BY u.campania, r.fin DESC NULLS LAST, r.run_id DESC
                """,
            )
            resultado["validacion_operativa"] = _consulta_si_existe(
                conexion,
                "reporting.validacion_modelo_operativo",
                """
                SELECT validation_id, run_id, modelo, creado_en, estado, archivo, sha256,
                       filas_fuente, filas_motor, diferencias_filas, max_diferencia,
                       advertencias, metadatos
                FROM reporting.validacion_modelo_operativo
                WHERE modelo = 'ModeloOperativoActual_v1'
                ORDER BY creado_en DESC, validation_id DESC
                """,
            )
            resultado["claims"] = _consulta(
                conexion,
                """
                SELECT claim_id, hipotesis_id, hipotesis, clase_evidencia, estado, afirmacion,
                       estimacion, intervalo_inferior, intervalo_superior, n_efectivo,
                       alcance, supuestos, limitaciones, referencias, actualizado_en, run_id
                FROM reporting.evidencia_analitica ORDER BY claim_id
            """,
            )
            # Sin LIMIT: la emisión completa se trae en ~90 ms (2.600 filas medidas el
            # 2026-08-19) y un recorte arbitrario haría que un fundo desapareciera de la
            # vista sin avisar. Se seleccionan también los componentes, que ya están
            # persistidos y son los que permiten juzgar si el pronóstico tiene sentido
            # agronómico.
            resultado["proyeccion"] = _consulta(
                conexion,
                """
                SELECT modelo, version_fuente, campania, empresa, fundo, modulo, lote,
                       lote_id, fecha_emision, fecha_objetivo, horizonte_semanas,
                       banda_horizonte, p10_kg, p50_kg, p90_kg, real_kg,
                       plantas, frutos_por_planta, peso_baya_g, componentes,
                       confianza, snapshot_id, generado_en
                FROM reporting.proyeccion_vigente
                ORDER BY fecha_objetivo, fundo, modulo, lote_id
            """,
            )
            resultado["proyeccion_experimental"] = _consulta_si_existe(
                conexion,
                "reporting.proyeccion_operativa_detalle",
                """
                SELECT run_id, modelo, version_fuente, campania, empresa, fundo, modulo, lote,
                       fundo_fuente, lote_id, fecha_emision, fecha_objetivo, horizonte_semanas,
                       banda_horizonte, p10_kg, p50_kg, p90_kg, real_kg,
                       plantas, frutos_por_planta, peso_baya_g, componentes,
                       confianza, snapshot_id, generado_en, configuracion,
                       turno, variedad, area_ha, n_plantas
                FROM reporting.proyeccion_operativa_detalle
                ORDER BY fecha_objetivo, fundo, modulo, lote_id
                """,
            )
            resultado["proyeccion_operativa_semana"] = _consulta_si_existe(
                conexion,
                "reporting.proyeccion_operativa_fundo_semana",
                """
                SELECT run_id, modelo, version_modelo, campania, fecha_emision,
                       semana_inicio, fundo, kg, filas, lotes
                FROM reporting.proyeccion_operativa_fundo_semana
                ORDER BY semana_inicio, fundo
                """,
            )
            # La curva real no se obtiene de `prediction.real_kg`: esa columna solo se
            # rellena cuando un replay ya cerró el objetivo. Para la mesa diaria se lee la
            # cosecha observada directamente y se muestra únicamente antes del corte de la
            # emisión; nunca se usa como predictor de una fecha futura.
            resultado["cosecha_real"] = cosecha_real_analitica(conexion)
            resultado["cosecha_real_semana"] = _consulta_si_existe(
                conexion,
                "reporting.cosecha_real_fundo_semana",
                """
                SELECT campania, semana_inicio, fundo, kg, lotes
                FROM reporting.cosecha_real_fundo_semana
                ORDER BY semana_inicio, fundo
                """,
            )
            resultado["evidencia_features"] = _consulta_si_existe(
                conexion,
                "reporting.evidencia_features_modelo",
                """
                SELECT modelo, modelo_componente, predictor, objetivo, rezago,
                       transformacion, hipotesis_id, hipotesis, referencias, metodo, papel,
                       estado, admitida, cobertura, n_efectivo, estimacion,
                       q_value, placebo, estabilidad_modulo, fecha_emision,
                       limitacion, claim_id, run_id, snapshot_id
                FROM reporting.evidencia_features_modelo
                ORDER BY fecha_emision DESC, objetivo, admitida DESC, predictor
                """,
            )
            resultado["fuente_access"] = _consulta_si_existe(
                conexion,
                "reporting.fuente_operativa_access",
                """
                SELECT source_snapshot_id, campania, nombre_archivo, ruta_origen, sha256,
                       bytes, modificado_en, extraido_en, version_minima_r09,
                       version_maxima_r09, filas_r09, conteos_tabla, diferencias
                FROM reporting.fuente_operativa_access
                """,
            )
            resultado["escenarios_guardados"] = _consulta_si_existe(
                conexion,
                "analytics.projection_scenario",
                """
                SELECT scenario_id, nombre, modo_decision, estado, run_base_id,
                       parametros, advertencias, creado_por, creado_en, actualizado_en
                FROM analytics.projection_scenario
                ORDER BY actualizado_en DESC LIMIT 50
                """,
            )
            resultado["calidad"] = _consulta(
                conexion,
                """
                WITH releases AS (
                    SELECT l.run_id,
                           bool_or(
                               l.activo
                               AND l.estado = 'approved'
                               AND (
                                   (l.uso = 'operativo'
                                    AND l.estado_evaluacion IN ('passed', 'not_applicable'))
                                   OR (l.uso <> 'operativo'
                                       AND l.estado_evaluacion = 'passed'
                                       AND c.estado = 'approved')
                               )
                           ) AS certificada
                    FROM analytics.model_series_release l
                    LEFT JOIN analytics.evaluation_contract c
                      ON c.evaluation_contract_id = l.evaluation_contract_id
                    GROUP BY l.run_id
                ), ultima AS (
                    SELECT r.run_id
                    FROM analytics.forecast_run r
                    JOIN releases l USING (run_id)
                    WHERE r.estado IN ('succeeded', 'published') AND l.certificada
                    ORDER BY r.fin DESC NULLS LAST, r.run_id DESC LIMIT 1
                )
                SELECT q.regla, q.estado, q.observados, q.afectados, q.detalle
                FROM analytics.quality_result q JOIN ultima u USING (run_id)
                ORDER BY (q.estado = 'error') DESC, (q.estado = 'warning') DESC, q.regla
            """,
            )
            resultado["artefactos"] = _consulta(
                conexion,
                """
                WITH releases AS (
                    SELECT l.run_id,
                           bool_or(
                               l.activo
                               AND l.estado = 'approved'
                               AND (
                                   (l.uso = 'operativo'
                                    AND l.estado_evaluacion IN ('passed', 'not_applicable'))
                                   OR (l.uso <> 'operativo'
                                       AND l.estado_evaluacion = 'passed'
                                       AND c.estado = 'approved')
                               )
                           ) AS release_aprobada
                    FROM analytics.model_series_release l
                    LEFT JOIN analytics.evaluation_contract c
                      ON c.evaluation_contract_id = l.evaluation_contract_id
                    GROUP BY l.run_id
                )
                SELECT a.run_id, r.tipo, a.tipo AS artefacto, a.uri, a.sha256, a.bytes,
                       a.creado_en, COALESCE(l.release_aprobada, false) AS release_aprobada
                FROM analytics.artifact a JOIN analytics.forecast_run r USING (run_id)
                LEFT JOIN releases l USING (run_id)
                WHERE r.estado IN ('succeeded', 'published')
                  AND COALESCE(r.configuracion->>'publicacion', 'official') <> 'experimental'
                ORDER BY a.artifact_id DESC LIMIT 20
            """,
            )
            # Atributos del lote para las unidades con que el agrónomo juzga un pronóstico
            # (kg/ha, kg por planta) y para agrupar por turno o variedad. El área viene de
            # la dimensión y se toma una vez por lote: sumarla desde el hecho la contaría
            # una vez por semana (defecto B-4 de ADR-0004).
            resultado["lotes"] = lotes(conexion)
            # Qué tablas alimentaron la corrida vigente y con cuántas filas cada una. Sale
            # del propio snapshot, así que describe los datos que de verdad se usaron y no
            # el estado actual de la base, que puede haber cambiado desde entonces.
            resultado["fuentes"] = _consulta(
                conexion,
                """
                SELECT s.snapshot_id, s.fuente, s.corte_datos, s.firma, s.tablas, s.cobertura,
                       NULLIF(s.cobertura->>'source_snapshot_id', '')::bigint
                           AS source_snapshot_id,
                       s.advertencias, r.run_id, r.tipo, r.fin
                FROM analytics.dataset_snapshot s
                JOIN analytics.forecast_run r USING (snapshot_id)
                JOIN (
                    SELECT r2.run_id
                    FROM analytics.forecast_run r2
                    JOIN analytics.model_series_release l ON l.run_id = r2.run_id
                    JOIN analytics.evaluation_contract c
                      ON c.evaluation_contract_id = l.evaluation_contract_id
                    WHERE r2.tipo = 'backtest'
                      AND r2.estado IN ('succeeded', 'published')
                      AND l.uso IN ('historico', 'referencia')
                      AND l.activo
                      AND l.estado = 'approved'
                      AND l.estado_evaluacion = 'passed'
                      AND c.estado = 'approved'
                    ORDER BY r2.fin DESC NULLS LAST, r2.run_id DESC
                    LIMIT 1
                ) vigente USING (run_id)
            """,
            )
            fuente_visible = resultado["fuentes"]
            source_snapshot_id = None
            if not fuente_visible.empty:
                valor = fuente_visible.iloc[0].get("source_snapshot_id")
                if pd.notna(valor):
                    source_snapshot_id = int(valor)
            if source_snapshot_id is not None:
                resultado["fuente_access_control"] = _consulta_si_existe(
                    conexion,
                    "raw.source_snapshot",
                    """
                    SELECT source_snapshot_id, campania, nombre_archivo, extraido_en,
                           manifiesto->>'alcance' AS alcance,
                           CASE
                               WHEN manifiesto->>'snapshot_completo' IN ('true', 'false')
                               THEN (manifiesto->>'snapshot_completo')::boolean
                               ELSE NULL
                           END AS snapshot_completo,
                           NULLIF(manifiesto->>'tablas_catalogo', '')::integer AS tablas_catalogo,
                           NULLIF(manifiesto->>'tablas_extraidas', '')::integer AS tablas_extraidas,
                           jsonb_array_length(
                               CASE
                                   WHEN jsonb_typeof(manifiesto->'tablas_omitidas') = 'array'
                                   THEN manifiesto->'tablas_omitidas'
                                   ELSE '[]'::jsonb
                               END
                           ) AS tablas_omitidas
                    FROM raw.source_snapshot
                    WHERE tipo = 'access' AND source_snapshot_id = %s
                    """,
                    (source_snapshot_id,),
                )
            resultado.update(
                _artefactos_de(
                    conexion,
                    "relations",
                    {
                        "relaciones": "relaciones.parquet",
                        "inferencia": "inferencia.parquet",
                        "matriz": "matriz_relaciones.parquet",
                        "packing": "relaciones_packing.parquet",
                        "ensamblaje": "auditoria_ensamblaje.parquet",
                    },
                )
            )
            resultado.update(
                _artefactos_de(
                    conexion,
                    "train",
                    {
                        "ablaciones": "explicacion_ablaciones.parquet",
                        "permutacion": "explicacion_permutacion_agrupada.parquet",
                        "shap": "explicacion_shap.parquet",
                    },
                )
            )
    except Exception as exc:  # La vista debe abrir incluso durante bootstrap/migración.
        resultado["error"] = f"Analytics no disponible: {type(exc).__name__}: {exc}"
    return resultado


def estado_analitico() -> dict[str, object]:
    """Snapshot de lectura con refresco máximo de un minuto."""
    return _estado_cache(int(time.time() // 60))


def guardar_escenario_proyeccion(
    *,
    nombre: str,
    modo_decision: str,
    run_base_id: int | None,
    parametros: dict,
    advertencias: list[str],
) -> int:
    from analitica.proyeccion.gobernanza import RepositorioAnalytics

    scenario_id = RepositorioAnalytics().guardar_escenario(
        nombre=nombre,
        modo_decision=modo_decision,
        run_base_id=run_base_id,
        parametros=parametros,
        advertencias=advertencias,
        actor="dashboard",
    )
    _estado_cache.cache_clear()
    return scenario_id


def enviar_escenario_revision(scenario_id: int) -> None:
    from analitica.proyeccion.gobernanza import RepositorioAnalytics

    RepositorioAnalytics().cambiar_estado_escenario(
        scenario_id,
        "en_revision",
        comentario="Enviado desde el dashboard",
        actor="dashboard",
    )
    _estado_cache.cache_clear()
