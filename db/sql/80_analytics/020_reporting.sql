-- ============================================================================
-- 80_analytics · 020 · Contratos de lectura
-- ============================================================================

CREATE OR REPLACE VIEW reporting.proyeccion_vigente AS
SELECT p.prediction_id, p.run_id, p.modelo, p.version_modelo, p.campania,
       p.empresa, p.fundo, p.modulo, p.lote, p.lote_id,
       p.fecha_emision, p.fecha_objetivo, p.horizonte_semanas,
       p.banda_horizonte, p.version_fuente, p.p10_kg, p.p50_kg, p.p90_kg,
       p.real_kg, p.plantas, p.frutos_por_planta, p.peso_baya_g,
       p.confianza, p.componentes,
       r.snapshot_id, r.mlflow_run_id, r.codigo_commit, r.fin AS generado_en
FROM analytics.prediction p
JOIN analytics.model_series_release l
  ON l.run_id = p.run_id
 AND l.campania = p.campania
 AND l.modelo = p.modelo
 AND l.version_modelo = COALESCE(NULLIF(p.version_modelo, ''), 'sin_version')
JOIN analytics.forecast_run r ON r.run_id = p.run_id
WHERE l.uso = 'operativo'
  AND l.activo
  AND l.estado = 'approved'
  AND l.estado_evaluacion IN ('passed', 'not_applicable')
  AND r.estado IN ('succeeded', 'published');

CREATE OR REPLACE VIEW reporting.desempeno_modelos AS
SELECT m.*, r.snapshot_id, r.mlflow_run_id, r.codigo_commit, r.inicio, r.fin
FROM analytics.metric m
JOIN analytics.forecast_run r USING (run_id)
WHERE r.estado IN ('succeeded', 'published');

CREATE OR REPLACE VIEW reporting.evidencia_analitica AS
SELECT * FROM analytics.evidence_claim;

CREATE OR REPLACE VIEW reporting.evidencia_features_modelo AS
SELECT e.*, r.snapshot_id, r.codigo_commit, r.fin AS generado_en
FROM analytics.model_feature_evidence e
JOIN analytics.forecast_run r USING (run_id)
WHERE r.estado IN ('succeeded', 'published');

CREATE OR REPLACE VIEW reporting.fuente_operativa_access AS
SELECT s.*,
       COALESCE(
           jsonb_object_agg(
               d.tabla_destino,
               jsonb_build_object(
                   'anteriores', d.filas_anteriores,
                   'actuales', d.filas_actuales,
                   'nuevas', d.filas_nuevas,
                   'eliminadas', d.filas_eliminadas,
                   'modificadas', d.filas_modificadas,
                   'metodo', d.metodo
               )
           ) FILTER (WHERE d.tabla_destino IS NOT NULL),
           '{}'::jsonb
       ) AS diferencias
FROM raw.v_ultimo_snapshot_fuente s
LEFT JOIN raw.source_table_delta d USING (source_snapshot_id)
WHERE s.tipo = 'access'
GROUP BY s.source_snapshot_id, s.tipo, s.campania, s.nombre_archivo, s.ruta_origen,
         s.sha256, s.bytes, s.modificado_en, s.extraido_en, s.version_minima_r09,
         s.version_maxima_r09, s.filas_r09, s.conteos_tabla, s.creado_en;

CREATE OR REPLACE VIEW reporting.trazabilidad_modelo AS
SELECT d.*, r.snapshot_id, r.mlflow_run_id, r.codigo_commit, r.configuracion,
       s.fuente, s.firma AS firma_snapshot, s.corte_datos, s.cobertura, s.advertencias
FROM analytics.model_decision d
LEFT JOIN analytics.forecast_run r USING (run_id)
LEFT JOIN analytics.dataset_snapshot s USING (snapshot_id);

CREATE OR REPLACE VIEW reporting.validacion_modelo_operativo AS
SELECT validation_id, run_id, modelo, creado_en, estado, archivo, sha256,
       filas_fuente, filas_motor, diferencias_filas, max_diferencia,
       advertencias, metadatos
FROM analytics.operational_model_validation;

COMMENT ON VIEW reporting.proyeccion_vigente IS
    'Única release operativa aprobada; nunca selecciona la última corrida exitosa por fecha.';

-- Nowcast gobernado y separado del forecast. Una release histórica siempre
-- necesita contrato aprobado; una release operativa puede existir antes de que
-- llegue el real final, pero nunca se selecciona por ser simplemente la última.
CREATE OR REPLACE VIEW reporting.nowcast_cierre_semanal AS
SELECT n.nowcast_id, n.run_id, n.modelo, n.version_modelo, n.campania,
       n.semana_inicio, n.semana_cierre, n.fecha_corte, n.fecha_emision,
       n.fundo, n.kg_lun_mar, n.p50_kg, n.real_kg, n.macro_kg,
       n.r09_presemana_kg, n.r09_misma_semana_kg, n.estado_evaluacion,
       n.componentes, l.release_id, l.evaluation_contract_id, l.uso,
       l.estado AS estado_release, l.estado_evaluacion AS evaluacion_release,
       l.source_hash, r.snapshot_id, r.codigo_commit, r.fin AS generado_en,
       CASE
           WHEN n.real_kg IS NULL OR n.real_kg = 0 THEN NULL
           ELSE abs(n.p50_kg - n.real_kg) / n.real_kg
       END AS ape,
       CASE
           WHEN n.real_kg IS NULL OR n.real_kg = 0 THEN NULL
           ELSE (n.p50_kg - n.real_kg) / n.real_kg
       END AS sesgo_pct
FROM analytics.weekly_nowcast n
JOIN analytics.model_series_release l
  ON l.run_id = n.run_id
 AND l.campania = n.campania
 AND l.modelo = n.modelo
 AND l.version_modelo = n.version_modelo
JOIN analytics.forecast_run r
  ON r.run_id = n.run_id
 AND r.snapshot_id = l.snapshot_id
LEFT JOIN analytics.evaluation_contract c
  ON c.evaluation_contract_id = l.evaluation_contract_id
WHERE l.activo
  AND l.estado = 'approved'
  AND l.uso IN ('historico', 'operativo')
  AND (
      (l.uso = 'historico'
       AND l.estado_evaluacion = 'passed'
       AND c.estado = 'approved')
      OR
      (l.uso = 'operativo'
       AND l.estado_evaluacion IN ('passed', 'not_applicable'))
  )
  AND r.estado IN ('succeeded', 'published');

COMMENT ON VIEW reporting.nowcast_cierre_semanal IS
    'Release aprobada de cierre intra-semanal; conserva corte, avance Lun-Mar y referencias sin mezclarlas como predictores.';

CREATE OR REPLACE VIEW reporting.proyeccion_experimental AS
WITH ultima AS (
    SELECT r.run_id
    FROM analytics.forecast_run r
    JOIN analytics.prediction p USING (run_id)
    WHERE r.tipo = 'project'
      AND r.estado IN ('published', 'succeeded')
      AND r.configuracion->>'publicacion' = 'experimental'
      AND p.modelo = 'ModeloOperativoActual_v1'
    GROUP BY r.run_id, r.fin
    ORDER BY r.fin DESC NULLS LAST, r.run_id DESC
    LIMIT 1
)
SELECT p.prediction_id, p.run_id, p.modelo, p.version_modelo, p.campania,
       p.empresa, p.fundo, p.modulo, p.lote, p.lote_id,
       p.fecha_emision, p.fecha_objetivo, p.horizonte_semanas,
       p.banda_horizonte, p.version_fuente, p.p10_kg, p.p50_kg, p.p90_kg,
       p.real_kg, p.plantas, p.frutos_por_planta, p.peso_baya_g,
       p.confianza, p.componentes,
       r.snapshot_id, r.mlflow_run_id, r.codigo_commit, r.fin AS generado_en,
       r.configuracion
FROM analytics.prediction p
JOIN ultima u USING (run_id)
JOIN analytics.forecast_run r USING (run_id);

-- La comparación se calcula una sola vez al finalizar el backtest. La interfaz no
-- debe ejecutar un self-join de cientos de miles de predicciones en cada apertura.
CREATE OR REPLACE VIEW reporting.comparacion_r09_fenologico_pareada AS
WITH ultima AS (
    SELECT max(run_id) AS run_id
    FROM analytics.model_comparison_metric
    WHERE modelo_base = 'R09_publicado'
      AND modelo IN ('R09_publicado', 'FenologicoComponentes_v1')
)
SELECT m.run_id, m.modelo, m.banda_horizonte, m.n::bigint AS n, m.wape, m.mae_kg,
       m.sesgo_pct, m.cobertura_80::numeric AS cobertura_80, m.volumen_real_kg,
       m.mase, NULL::double precision AS escala_naive, m.universo
FROM analytics.model_comparison_metric m
JOIN ultima u USING (run_id)
WHERE m.modelo_base = 'R09_publicado'
  AND m.modelo IN ('R09_publicado', 'FenologicoComponentes_v1');

COMMENT ON VIEW reporting.proyeccion_experimental IS
    'Última corrida experimental, separada de la proyección vigente para evitar promoverla por accidente.';

-- La operación agronómica trabaja con cuatro fundos. Aqu Anqa 3 y 5 son dos códigos
-- administrativos de Kawsay, no dos fundos que deban mostrarse o sumarse por separado.
CREATE OR REPLACE FUNCTION reporting.fundo_operativo(nombre text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT CASE lower(trim(COALESCE(nombre, '')))
        WHEN 'aqu anqa 1' THEN 'Arena'
        WHEN 'aqu anqa 2' THEN 'Quri'
        WHEN 'aqu anqa 3' THEN 'Kawsay'
        WHEN 'aqu anqa 4' THEN 'Ayllu'
        WHEN 'aqu anqa 5' THEN 'Kawsay'
        WHEN 'arena' THEN 'Arena'
        WHEN 'ayllu' THEN 'Ayllu'
        WHEN 'ayllu allpa' THEN 'Ayllu'
        WHEN 'kawsay' THEN 'Kawsay'
        WHEN 'kawsay allpa' THEN 'Kawsay'
        WHEN 'quri' THEN 'Quri'
        WHEN 'quri allpa' THEN 'Quri'
        ELSE NULLIF(trim(nombre), '')
    END
$$;

CREATE OR REPLACE VIEW reporting.proyeccion_operativa_detalle AS
SELECT p.prediction_id, p.run_id, p.modelo, p.version_modelo, p.campania,
       p.empresa, reporting.fundo_operativo(p.fundo) AS fundo,
       p.fundo AS fundo_fuente, p.modulo, p.lote, p.lote_id,
       p.fecha_emision, p.fecha_objetivo, p.horizonte_semanas,
       p.banda_horizonte, p.version_fuente, p.p10_kg, p.p50_kg, p.p90_kg,
       p.real_kg, p.plantas, p.frutos_por_planta, p.peso_baya_g,
       p.confianza, p.componentes, r.snapshot_id, r.mlflow_run_id,
       r.codigo_commit, r.fin AS generado_en, r.configuracion,
       d.turno, d.variedad, d.area_ha, d.n_plantas
FROM analytics.prediction p
JOIN analytics.model_series_release l
  ON l.run_id = p.run_id
 AND l.campania = p.campania
 AND l.modelo = p.modelo
 AND l.version_modelo = COALESCE(NULLIF(p.version_modelo, ''), 'sin_version')
JOIN analytics.forecast_run r ON r.run_id = p.run_id
LEFT JOIN dim.lote d USING (lote_id)
WHERE l.uso = 'operativo'
  AND l.activo
  AND l.estado = 'approved'
  AND l.estado_evaluacion IN ('passed', 'not_applicable')
  AND r.estado IN ('succeeded', 'published')
  AND p.modelo = 'ModeloOperativoActual_v1';

CREATE OR REPLACE VIEW reporting.proyeccion_operativa_fundo_semana AS
SELECT run_id, modelo, version_modelo, campania, fecha_emision,
       date_trunc('week', fecha_objetivo)::date AS semana_inicio,
       fundo, SUM(p50_kg)::double precision AS kg,
       COUNT(*)::bigint AS filas,
       COUNT(DISTINCT lote_id)::bigint AS lotes
FROM reporting.proyeccion_operativa_detalle
GROUP BY run_id, modelo, version_modelo, campania, fecha_emision,
         date_trunc('week', fecha_objetivo)::date, fundo;

CREATE OR REPLACE VIEW reporting.cosecha_real_fundo_semana AS
SELECT h.campania, date_trunc('week', h.fecha)::date AS semana_inicio,
       reporting.fundo_operativo(d.fundo) AS fundo,
       SUM(h.kg)::double precision AS kg,
       COUNT(DISTINCT h.lote_id)::bigint AS lotes
FROM stg.v_h01_cosecha h
JOIN dim.lote d USING (lote_id)
WHERE h.fecha IS NOT NULL AND h.lote_id IS NOT NULL
GROUP BY h.campania, date_trunc('week', h.fecha)::date,
         reporting.fundo_operativo(d.fundo);

COMMENT ON VIEW reporting.proyeccion_operativa_detalle IS
    'Release operativa aprobada de ModeloOperativoActual_v1 a grano lote-paña; jamás usa la última corrida experimental como fallback.';
COMMENT ON VIEW reporting.proyeccion_operativa_fundo_semana IS
    'Agregado liviano de la corrida Python por semana y por Arena, Ayllu, Kawsay o Quri.';
COMMENT ON VIEW reporting.cosecha_real_fundo_semana IS
    'Cosecha observada por semana y cuatro fundos operativos para la curva diaria.';
COMMENT ON VIEW reporting.comparacion_r09_fenologico_pareada IS
    'R09 y FenologicoComponentes_v1 medidos sobre exactamente las mismas filas del último backtest común.';
COMMENT ON VIEW reporting.desempeno_modelos IS
    'Métricas fuera de muestra por modelo, campaña, fundo y horizonte.';
COMMENT ON VIEW reporting.evidencia_analitica IS
    'Conclusiones con grado de evidencia, supuestos, limitaciones y referencias.';
COMMENT ON VIEW reporting.evidencia_features_modelo IS
    'Features usadas o descartadas y su evidencia predictiva calculada dentro del fold.';
COMMENT ON VIEW reporting.fuente_operativa_access IS
    'Copia Access por campaña, hash, rango R09 y diferencias de filas por tabla.';
COMMENT ON VIEW reporting.trazabilidad_modelo IS
    'Decisiones champion-challenger y snapshot que las sustenta.';

CREATE OR REPLACE VIEW reporting.comparacion_modelos_historica AS
SELECT m.run_id, m.modelo_base, m.modelo, m.banda_horizonte, m.n, m.wape,
       m.mae_kg, m.sesgo_pct, m.cobertura_80, m.volumen_real_kg,
       m.mase, m.universo, r.snapshot_id, r.codigo_commit, r.fin AS generado_en
FROM analytics.model_comparison_metric m
JOIN analytics.forecast_run r USING (run_id)
WHERE r.estado IN ('succeeded', 'published')
  AND m.modelo_base = 'R09_publicado';

-- Estado de gobierno consumible por el dashboard. Esta vista no elige una corrida: expone
-- la release explícita y el contrato que justifican su publicación.
CREATE OR REPLACE VIEW reporting.model_series_release_status AS
SELECT l.release_id, l.evaluation_contract_id, l.run_id, l.snapshot_id,
       l.campania, l.modelo, l.version_modelo, l.uso,
       l.estado AS estado_release, l.estado_evaluacion, l.activo,
       (l.activo
        AND l.estado = 'approved'
        AND (
            (l.uso = 'operativo' AND l.estado_evaluacion IN ('passed', 'not_applicable'))
            OR (l.uso <> 'operativo' AND l.estado_evaluacion = 'passed'
                AND c.estado = 'approved')
        )
        AND r.estado IN ('succeeded', 'published')) AS certificado,
       l.source_hash, l.predicciones_sha256,
       c.firma AS contrato_firma, c.granularidad,
       c.fecha_inicio_objetivo, c.fecha_fin_objetivo, c.cerrado_hasta,
       c.horizontes_semanas, c.keyset_sha256, c.closed_calendar_sha256,
       c.volumen_real_kg, c.n_unidades, c.n_emisiones,
       c.estado AS estado_contrato,
       r.tipo AS tipo_corrida, r.estado AS estado_corrida,
       r.codigo_commit, r.inicio, r.fin,
       l.creado_en, l.aprobado_en, l.aprobado_por
FROM analytics.model_series_release l
LEFT JOIN analytics.evaluation_contract c
  ON c.evaluation_contract_id = l.evaluation_contract_id
JOIN analytics.forecast_run r
  ON r.run_id = l.run_id;

-- Curva vintage certificada. No existe fallback a la última corrida exitosa: si todavía no
-- hay releases aprobadas la vista queda vacía, evitando publicar un experimento como histórico.
-- Para cada modelo-semana se selecciona una sola emisión común a todos sus lotes, siempre
-- estrictamente anterior al lunes de la semana objetivo. `semanas_cerradas` almacena lunes
-- ISO en formato YYYY-MM-DD y excluye semanas parciales aunque ya haya terminado el calendario.
CREATE OR REPLACE VIEW reporting.curva_historica_modelos AS
WITH releases_aprobadas AS (
    SELECT l.release_id, l.evaluation_contract_id, l.run_id, l.snapshot_id,
           l.campania, l.modelo, l.version_modelo, l.uso,
           l.estado AS estado_release, l.estado_evaluacion,
           l.source_hash,
           c.firma AS contrato_firma, c.estado AS estado_contrato,
           c.fecha_inicio_objetivo, c.fecha_fin_objetivo, c.cerrado_hasta,
           c.semanas_cerradas, c.keyset_sha256, c.closed_calendar_sha256
    FROM analytics.model_series_release l
    JOIN analytics.evaluation_contract c
      ON c.evaluation_contract_id = l.evaluation_contract_id
     AND c.campania = l.campania
     AND c.snapshot_id = l.snapshot_id
    JOIN analytics.forecast_run r
      ON r.run_id = l.run_id
     AND r.snapshot_id = l.snapshot_id
    WHERE l.activo
      AND l.estado = 'approved'
      AND l.estado_evaluacion = 'passed'
      AND l.uso IN ('historico', 'referencia')
      AND c.estado = 'approved'
      AND r.estado IN ('succeeded', 'published')
), predicciones_elegibles AS (
    SELECT p.prediction_id, p.run_id, p.modelo, p.version_modelo,
           p.campania, p.lote_id, p.fecha_emision,
           date_trunc('week', p.fecha_objetivo)::date AS semana_inicio,
           p.horizonte_semanas, p.p10_kg, p.p50_kg, p.p90_kg, p.real_kg,
           l.release_id, l.evaluation_contract_id, l.snapshot_id,
           l.version_modelo AS version_release, l.uso,
           l.estado_release, l.estado_evaluacion, l.source_hash,
           l.contrato_firma, l.estado_contrato, l.cerrado_hasta,
           l.keyset_sha256, l.closed_calendar_sha256
    FROM analytics.prediction p
    JOIN releases_aprobadas l
      ON l.run_id = p.run_id
     AND l.campania = p.campania
     AND l.modelo = p.modelo
     AND l.version_modelo = COALESCE(NULLIF(p.version_modelo, ''), 'sin_version')
    WHERE p.lote_id IS NOT NULL
      AND p.fecha_emision < date_trunc('week', p.fecha_objetivo)::date
      AND date_trunc('week', p.fecha_objetivo)::date
          BETWEEN l.fecha_inicio_objetivo AND l.fecha_fin_objetivo
      AND date_trunc('week', p.fecha_objetivo)::date + 6 <= l.cerrado_hasta
      AND l.semanas_cerradas
          ? to_char(date_trunc('week', p.fecha_objetivo)::date, 'YYYY-MM-DD')
), emision_coherente AS (
    SELECT release_id, semana_inicio, MAX(fecha_emision) AS fecha_emision
    FROM predicciones_elegibles
    GROUP BY release_id, semana_inicio
), vintages AS (
    SELECT DISTINCT ON (p.release_id, p.semana_inicio, p.lote_id)
           p.*
    FROM predicciones_elegibles p
    JOIN emision_coherente e
      ON e.release_id = p.release_id
     AND e.semana_inicio = p.semana_inicio
     AND e.fecha_emision = p.fecha_emision
    ORDER BY p.release_id, p.semana_inicio, p.lote_id, p.prediction_id DESC
), pronosticos AS (
    SELECT campania, semana_inicio AS fecha_objetivo, modelo,
           SUM(p10_kg)::double precision AS p10_kg,
           SUM(p50_kg)::double precision AS p50_kg,
           SUM(p90_kg)::double precision AS p90_kg,
           SUM(real_kg)::double precision AS real_kg,
           MIN(fecha_emision) AS origen_emision_min,
           MAX(fecha_emision) AS origen_emision_max,
           COUNT(DISTINCT lote_id)::bigint AS n_lotes,
           'vintage_certificado'::text AS tipo_curva,
           evaluation_contract_id, contrato_firma, release_id,
           version_release AS version_modelo, uso AS uso_release,
           estado_release, estado_evaluacion AS estado_evaluacion_release,
           estado_contrato, true AS certificado, snapshot_id, run_id,
           MIN(horizonte_semanas)::smallint AS horizonte_semanas,
           cerrado_hasta, keyset_sha256, closed_calendar_sha256,
           source_hash, 'release_activa_aprobada'::text AS origen_seleccion
    FROM vintages
    GROUP BY campania, semana_inicio, modelo, evaluation_contract_id,
             contrato_firma, release_id, version_release, uso, estado_release,
             estado_evaluacion, estado_contrato, snapshot_id, run_id,
             cerrado_hasta, keyset_sha256, closed_calendar_sha256, source_hash
), reales_lote AS (
    SELECT DISTINCT ON (evaluation_contract_id, semana_inicio, lote_id)
           campania, semana_inicio, lote_id, real_kg,
           evaluation_contract_id, contrato_firma, estado_contrato,
           snapshot_id, cerrado_hasta, keyset_sha256, closed_calendar_sha256
    FROM predicciones_elegibles
    WHERE real_kg IS NOT NULL
    ORDER BY evaluation_contract_id, semana_inicio, lote_id, prediction_id
), reales AS (
    SELECT h.campania, h.semana_inicio AS fecha_objetivo,
           'Real cosechado'::text AS modelo,
           SUM(h.real_kg)::double precision AS p10_kg,
           SUM(h.real_kg)::double precision AS p50_kg,
           SUM(h.real_kg)::double precision AS p90_kg,
           SUM(h.real_kg)::double precision AS real_kg,
           NULL::date AS origen_emision_min,
           NULL::date AS origen_emision_max,
           COUNT(DISTINCT h.lote_id)::bigint AS n_lotes,
           'observado_contrato'::text AS tipo_curva,
           h.evaluation_contract_id, h.contrato_firma,
           NULL::bigint AS release_id, NULL::text AS version_modelo,
           'observado'::text AS uso_release, NULL::text AS estado_release,
           NULL::text AS estado_evaluacion_release,
           h.estado_contrato, true AS certificado, h.snapshot_id,
           NULL::bigint AS run_id, NULL::smallint AS horizonte_semanas,
           h.cerrado_hasta, h.keyset_sha256, h.closed_calendar_sha256,
           NULL::text AS source_hash,
           'contrato_aprobado'::text AS origen_seleccion
    FROM reales_lote h
    GROUP BY h.campania, h.semana_inicio, h.evaluation_contract_id,
             h.contrato_firma, h.estado_contrato, h.snapshot_id,
             h.cerrado_hasta, h.keyset_sha256, h.closed_calendar_sha256
)
SELECT * FROM pronosticos
UNION ALL
SELECT * FROM reales;

COMMENT ON VIEW reporting.comparacion_modelos_historica IS
    'Comparación R09 contra MacroLegacy, híbrido y Fenologico sobre el mismo replay.';
COMMENT ON VIEW reporting.curva_historica_modelos IS
    'Curva real y vintage certificada por release y contrato; no usa fallback a la última corrida exitosa.';
COMMENT ON VIEW reporting.model_series_release_status IS
    'Estado de releases, contratos y corridas para que el dashboard distinga ejecución, evaluación y publicación.';
COMMENT ON VIEW reporting.validacion_modelo_operativo IS
    'Paridad de los libros operativos y bloqueo explícito de fuentes inconsistentes.';
