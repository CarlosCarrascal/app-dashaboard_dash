-- ============================================================================
-- Perfilado read-only de M_PresupuestoMO.
--
-- El objetivo es decidir si esta fuente puede salir de raw_only. Este script
-- no crea tablas, no cambia datos y no modifica el ledger de migración.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

DO $mpmo_guard$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'PERFIL M_PresupuestoMO BLOQUEADO: la BD actual es %, se exige aquanqa_migracion.',
            current_database();
    END IF;
END
$mpmo_guard$;

\echo '--- M_PresupuestoMO: snapshot y volumen ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
)
SELECT s.snapshot_id,
       count(p.*) AS filas,
       count(DISTINCT p.source_row_hash) AS hashes_distintos,
       count(*) - count(DISTINCT p.source_row_hash) AS filas_extra_por_hash,
       min(p.loaded_at) AS primera_carga,
       max(p.loaded_at) AS ultima_carga
FROM s
LEFT JOIN raw.m_presupuesto_mo p
       ON p.source_snapshot_id = s.snapshot_id
GROUP BY s.snapshot_id;

\echo '--- M_PresupuestoMO: historial de snapshots cargados ---'
SELECT source_snapshot_id,
       count(*) AS filas,
       count(DISTINCT source_row_hash) AS hashes_distintos,
       count(*) - count(DISTINCT source_row_hash) AS filas_extra_por_hash,
       min(stg.fn_a_entero(anio)) AS anio_min,
       max(stg.fn_a_entero(anio)) AS anio_max
FROM raw.m_presupuesto_mo
GROUP BY source_snapshot_id
ORDER BY source_snapshot_id;

\echo '--- M_PresupuestoMO: estructura Access catalogada ---'
SELECT source_snapshot_id,
       objeto_origen,
       schema_hash,
       jsonb_array_length(columnas) AS columnas_access,
       jsonb_array_length(indices) AS indices_access,
       jsonb_array_length(claves_primarias) AS claves_primarias_access
FROM raw.access_schema_catalog
WHERE tabla_destino = 'm_presupuesto_mo'
  AND source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
ORDER BY source_snapshot_id;

\echo '--- M_PresupuestoMO: deltas por snapshot ---'
SELECT source_snapshot_id,
       snapshot_anterior_id,
       filas_anteriores,
       filas_actuales,
       filas_nuevas,
       filas_eliminadas,
       filas_modificadas,
       metodo
FROM raw.source_table_delta
WHERE tabla_destino = 'm_presupuesto_mo'
ORDER BY source_snapshot_id;

\echo '--- M_PresupuestoMO: grano y cobertura observados ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), d AS (
    SELECT NULLIF(btrim(p.anio), '') AS anio,
           NULLIF(btrim(p.semana), '') AS semana,
           NULLIF(btrim(p.fundo), '') AS fundo,
           NULLIF(btrim(p.evaluacion), '') AS evaluacion,
           NULLIF(btrim(p.mo_sem), '') AS mo_sem
    FROM s
    JOIN raw.m_presupuesto_mo p ON p.source_snapshot_id = s.snapshot_id
)
SELECT count(*) AS filas,
       count(DISTINCT (anio, semana, fundo, evaluacion)) AS claves_distintas,
       count(*) - count(DISTINCT (anio, semana, fundo, evaluacion)) AS filas_duplicadas_por_clave,
       count(DISTINCT (anio, semana)) AS semanas_distintas,
       count(DISTINCT fundo) AS fundos_distintos,
       count(DISTINCT evaluacion) AS evaluaciones_distintas,
       count(*) FILTER (WHERE anio IS NULL) AS anio_vacio,
       count(*) FILTER (WHERE semana IS NULL) AS semana_vacia,
       count(*) FILTER (WHERE fundo IS NULL) AS fundo_vacio,
       count(*) FILTER (WHERE evaluacion IS NULL) AS evaluacion_vacia,
       count(*) FILTER (WHERE mo_sem IS NULL) AS mo_sem_vacio
FROM d;

\echo '--- M_PresupuestoMO: duplicados por la clave candidata ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
)
SELECT p.anio, p.semana, p.fundo, p.evaluacion, count(*) AS filas
FROM s
JOIN raw.m_presupuesto_mo p ON p.source_snapshot_id = s.snapshot_id
GROUP BY p.anio, p.semana, p.fundo, p.evaluacion
HAVING count(*) > 1
ORDER BY filas DESC, p.anio, p.semana, p.fundo, p.evaluacion
LIMIT 50;

\echo '--- M_PresupuestoMO: tipado, rango y signo de MOSem ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), n AS (
    SELECT p.*,
           stg.fn_a_entero(p.anio) AS anio_n,
           stg.fn_a_entero(p.semana) AS semana_n,
           stg.fn_a_real(p.mo_sem) AS mo_sem_n
    FROM s
    JOIN raw.m_presupuesto_mo p ON p.source_snapshot_id = s.snapshot_id
)
SELECT count(*) AS filas,
       count(*) FILTER (WHERE NULLIF(btrim(anio), '') IS NOT NULL AND anio_n IS NULL) AS anio_invalido,
       count(*) FILTER (WHERE NULLIF(btrim(semana), '') IS NOT NULL AND semana_n IS NULL) AS semana_invalida,
       count(*) FILTER (WHERE NULLIF(btrim(mo_sem), '') IS NOT NULL AND mo_sem_n IS NULL) AS mo_sem_invalido,
       min(anio_n) AS anio_min,
       max(anio_n) AS anio_max,
       min(semana_n) AS semana_min,
       max(semana_n) AS semana_max,
       min(mo_sem_n) AS mo_sem_min,
       max(mo_sem_n) AS mo_sem_max,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY mo_sem_n) AS mo_sem_mediana,
       sum(mo_sem_n) AS mo_sem_total,
       count(*) FILTER (WHERE mo_sem_n = 0) AS mo_sem_cero,
       count(*) FILTER (WHERE mo_sem_n > 0) AS mo_sem_positivo,
       count(*) FILTER (WHERE mo_sem_n < 0) AS mo_sem_negativo
FROM n;

\echo '--- M_PresupuestoMO: vocabularios de origen ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
)
SELECT 'fundo' AS atributo, p.fundo AS valor, count(*) AS filas
FROM s
JOIN raw.m_presupuesto_mo p ON p.source_snapshot_id = s.snapshot_id
GROUP BY p.fundo
UNION ALL
SELECT 'evaluacion', p.evaluacion, count(*)
FROM s
JOIN raw.m_presupuesto_mo p ON p.source_snapshot_id = s.snapshot_id
GROUP BY p.evaluacion
ORDER BY atributo, filas DESC, valor;

\echo '--- M_PresupuestoMO: cobertura rectangular por semana/fundo/evaluacion ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), d AS (
    SELECT p.anio, p.semana, p.fundo, p.evaluacion
    FROM s
    JOIN raw.m_presupuesto_mo p ON p.source_snapshot_id = s.snapshot_id
), c AS (
    SELECT count(DISTINCT (anio, semana)) AS semanas,
           count(DISTINCT fundo) AS fundos,
           count(DISTINCT evaluacion) AS evaluaciones,
           count(DISTINCT (anio, semana, fundo, evaluacion)) AS combinaciones
    FROM d
)
SELECT semanas,
       fundos,
       evaluaciones,
       combinaciones,
       semanas * fundos * evaluaciones AS combinaciones_esperadas,
       combinaciones = semanas * fundos * evaluaciones AS grilla_completa
FROM c;

\echo '--- M_PresupuestoMO: correspondencia con tiempo ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), p AS (
    SELECT DISTINCT stg.fn_a_entero(m.anio) AS anio,
                    stg.fn_a_entero(m.semana) AS semana
    FROM s
    JOIN raw.m_presupuesto_mo m ON m.source_snapshot_id = s.snapshot_id
), c AS (
    SELECT p.anio, p.semana,
           min(cal.fecha) AS fecha_inicio_calendario,
           max(cal.fecha) AS fecha_fin_calendario
    FROM p
    LEFT JOIN core.t_calendario cal
           ON cal.anio = p.anio
          AND cal.semana = p.semana
    GROUP BY p.anio, p.semana
), e AS (
    SELECT p.anio, p.semana,
           se.fecha_inicio AS fecha_inicio_evaluacion,
           se.fecha_fin AS fecha_fin_evaluacion
    FROM p
    LEFT JOIN core.t_semana_evaluacion se
           ON se.anio = p.anio
          AND se.sem_ev_conteo = p.semana
)
SELECT count(*) AS semanas_origen,
       count(*) FILTER (WHERE c.fecha_inicio_calendario IS NOT NULL) AS semanas_en_calendario,
       count(*) FILTER (WHERE e.fecha_inicio_evaluacion IS NOT NULL) AS coincidencias_numericas_con_semana_evaluacion,
       count(*) FILTER (
           WHERE c.fecha_inicio_calendario IS NOT NULL
             AND e.fecha_inicio_evaluacion IS NOT NULL
             AND (
                 c.fecha_inicio_calendario IS DISTINCT FROM e.fecha_inicio_evaluacion
                 OR c.fecha_fin_calendario IS DISTINCT FROM e.fecha_fin_evaluacion
             )
       ) AS rangos_distintos_calendario_vs_evaluacion
FROM c
JOIN e USING (anio, semana);

\echo '--- M_PresupuestoMO: resolución del fundo contra el diccionario core ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
)
SELECT p.fundo,
       count(*) AS filas,
       max(fa.alias_norm) AS alias_norm,
       max(fa.fundo_id) AS fundo_id_resuelto,
       bool_or(fa.ambiguo) AS alias_ambiguo,
       count(*) FILTER (WHERE fa.alias_norm IS NULL) AS filas_sin_alias,
       count(*) FILTER (WHERE fa.ambiguo) AS filas_con_alias_ambiguo,
       count(*) FILTER (WHERE fa.fundo_id IS NOT NULL) AS filas_con_fundo_resuelto
FROM s
JOIN raw.m_presupuesto_mo p ON p.source_snapshot_id = s.snapshot_id
LEFT JOIN core.m_fundo_alias fa
       ON fa.alias_norm = stg.fn_norm_texto(p.fundo)
GROUP BY p.fundo
ORDER BY p.fundo;

\echo '--- M_PresupuestoMO: evaluación contra la configuración vigente ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), v AS (
    SELECT p.evaluacion,
           count(*) AS filas,
           EXISTS (
               SELECT 1
               FROM core.cfg_muestra_requerida c
               WHERE c.evaluacion = p.evaluacion
           ) AS coincide_cfg_muestra
    FROM s
    JOIN raw.m_presupuesto_mo p ON p.source_snapshot_id = s.snapshot_id
    GROUP BY p.evaluacion
)
SELECT *
FROM v
ORDER BY evaluacion;

\echo '--- M_PresupuestoMO: no se promueve; queda raw_only hasta cerrar identidad y semántica ---'
