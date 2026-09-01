-- ============================================================================
-- Perfilado read-only del histórico de forecast:
--   R08_Forecast_Campaña_24
--   R08_Forecast_Campaña_25
--   R09_Forecast_Semanal_25
--
-- El objetivo es decidir si las tres fuentes representan el mismo dominio,
-- qué grano conserva cada una y si alguna puede salir de raw_only. Este script
-- no crea tablas, no cambia datos y no modifica el ledger de migración.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

DO $forecast_guard$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'PERFIL HISTÓRICOS FORECAST BLOQUEADO: la BD actual es %, se exige aquanqa_migracion.',
            current_database();
    END IF;
END
$forecast_guard$;

\echo '--- Forecast histórico: snapshot publicado ---'
SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_publicado;

\echo '--- Forecast histórico: volumen y huellas ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
)
SELECT 'r08_forecast_campania_24' AS tabla,
       count(*) AS filas,
       count(DISTINCT r.source_row_hash) AS hashes_distintos,
       count(*) - count(DISTINCT r.source_row_hash) AS filas_extra_por_hash,
       count(DISTINCT r.version) AS versiones,
       min(stg.fn_a_entero(r.anio)) AS anio_min,
       max(stg.fn_a_entero(r.anio)) AS anio_max,
       min(stg.fn_a_entero(r.semana)) AS semana_min,
       max(stg.fn_a_entero(r.semana)) AS semana_max
FROM s
JOIN raw.r08_forecast_campania_24 r ON r.source_snapshot_id = s.snapshot_id
UNION ALL
SELECT 'r08_forecast_campania_25',
       count(*),
       count(DISTINCT r.source_row_hash),
       count(*) - count(DISTINCT r.source_row_hash),
       count(DISTINCT r.version),
       min(stg.fn_a_entero(r.anio)),
       max(stg.fn_a_entero(r.anio)),
       min(stg.fn_a_entero(r.sem)),
       max(stg.fn_a_entero(r.sem))
FROM s
JOIN raw.r08_forecast_campania_25 r ON r.source_snapshot_id = s.snapshot_id
UNION ALL
SELECT 'r09_forecast_semanal_25',
       count(*),
       count(DISTINCT r.source_row_hash),
       count(*) - count(DISTINCT r.source_row_hash),
       count(DISTINCT r.version),
       min(EXTRACT(YEAR FROM stg.fn_a_fecha(r.fecha_cos))::integer),
       max(EXTRACT(YEAR FROM stg.fn_a_fecha(r.fecha_cos))::integer),
       min(stg.fn_a_entero(r.sem)),
       max(stg.fn_a_entero(r.sem))
FROM s
JOIN raw.r09_forecast_semanal_25 r ON r.source_snapshot_id = s.snapshot_id;

\echo '--- Forecast histórico: estructura Access catalogada ---'
SELECT tabla_destino,
       objeto_origen,
       schema_hash,
       jsonb_array_length(columnas) AS columnas_access,
       jsonb_array_length(indices) AS indices_access,
       jsonb_array_length(claves_primarias) AS claves_primarias_access
FROM raw.access_schema_catalog
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
  AND tabla_destino IN (
      'r08_forecast_campania_24',
      'r08_forecast_campania_25',
      'r09_forecast_semanal_25'
  )
ORDER BY tabla_destino;

\echo '--- Forecast histórico: deltas por snapshot ---'
SELECT tabla_destino,
       source_snapshot_id,
       snapshot_anterior_id,
       filas_anteriores,
       filas_actuales,
       filas_nuevas,
       filas_eliminadas,
       filas_modificadas,
       metodo
FROM raw.source_table_delta
WHERE tabla_destino IN (
    'r08_forecast_campania_24',
    'r08_forecast_campania_25',
    'r09_forecast_semanal_25'
)
ORDER BY tabla_destino, source_snapshot_id;

\echo '--- R08 campaña 24: calidad básica ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), n AS (
    SELECT r.*,
           stg.fn_a_entero(r.anio) AS anio_n,
           stg.fn_a_entero(r.semana) AS semana_n,
           stg.fn_a_real(r.kg) AS kg_n
    FROM s
    JOIN raw.r08_forecast_campania_24 r ON r.source_snapshot_id = s.snapshot_id
)
SELECT count(*) AS filas,
       count(*) FILTER (
           WHERE NULLIF(btrim(version), '') IS NULL
              OR NULLIF(btrim(fundo_ppto), '') IS NULL
              OR NULLIF(btrim(modulo), '') IS NULL
              OR NULLIF(btrim(anio), '') IS NULL
              OR NULLIF(btrim(semana), '') IS NULL
       ) AS claves_vacias,
       count(*) FILTER (WHERE NULLIF(btrim(anio), '') IS NOT NULL AND anio_n IS NULL) AS anio_invalido,
       count(*) FILTER (WHERE NULLIF(btrim(semana), '') IS NOT NULL AND semana_n IS NULL) AS semana_invalida,
       count(*) FILTER (WHERE NULLIF(btrim(kg), '') IS NOT NULL AND kg_n IS NULL) AS kg_invalido,
       count(*) FILTER (WHERE kg_n < 0) AS kg_negativo,
       count(*) FILTER (WHERE kg_n = 0) AS kg_cero,
       min(anio_n) AS anio_min,
       max(anio_n) AS anio_max,
       min(semana_n) AS semana_min,
       max(semana_n) AS semana_max,
       min(kg_n) AS kg_min,
       max(kg_n) AS kg_max,
       sum(kg_n) AS kg_total
FROM n;

\echo '--- R08 campaña 25: calidad básica ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), n AS (
    SELECT r.*,
           stg.fn_a_entero(r.anio) AS anio_n,
           stg.fn_a_entero(r.sem) AS semana_n,
           stg.fn_a_real(r.kg) AS kg_n
    FROM s
    JOIN raw.r08_forecast_campania_25 r ON r.source_snapshot_id = s.snapshot_id
)
SELECT count(*) AS filas,
       count(*) FILTER (
           WHERE NULLIF(btrim(version), '') IS NULL
              OR NULLIF(btrim(fundo), '') IS NULL
              OR NULLIF(btrim(modulo), '') IS NULL
              OR NULLIF(btrim(camp), '') IS NULL
              OR NULLIF(btrim(anio), '') IS NULL
              OR NULLIF(btrim(sem), '') IS NULL
       ) AS claves_vacias,
       count(*) FILTER (WHERE NULLIF(btrim(anio), '') IS NOT NULL AND anio_n IS NULL) AS anio_invalido,
       count(*) FILTER (WHERE NULLIF(btrim(sem), '') IS NOT NULL AND semana_n IS NULL) AS semana_invalida,
       count(*) FILTER (WHERE NULLIF(btrim(kg), '') IS NOT NULL AND kg_n IS NULL) AS kg_invalido,
       count(*) FILTER (WHERE kg_n < 0) AS kg_negativo,
       count(*) FILTER (WHERE kg_n = 0) AS kg_cero,
       min(anio_n) AS anio_min,
       max(anio_n) AS anio_max,
       min(semana_n) AS semana_min,
       max(semana_n) AS semana_max,
       min(kg_n) AS kg_min,
       max(kg_n) AS kg_max,
       sum(kg_n) AS kg_total
FROM n;

\echo '--- R08 campaña 25: columnas auxiliares vacías por versión ---'
SELECT version,
       count(*) AS filas,
       count(*) FILTER (WHERE NULLIF(btrim(pln_fundo), '') IS NULL) AS pln_fundo_vacio,
       count(*) FILTER (WHERE NULLIF(btrim(plnt_mod), '') IS NULL) AS plnt_mod_vacio,
       count(*) FILTER (WHERE NULLIF(btrim(turno), '') IS NULL) AS turno_vacio,
       count(*) FILTER (WHERE NULLIF(btrim(plantas), '') IS NULL) AS plantas_vacio,
       count(*) FILTER (WHERE NULLIF(btrim("desc"), '') IS NULL) AS desc_vacio,
       count(*) FILTER (WHERE NULLIF(btrim(frt_total), '') IS NULL) AS frt_total_vacio
FROM raw.r08_forecast_campania_25
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
GROUP BY version
HAVING count(*) FILTER (WHERE NULLIF(btrim(pln_fundo), '') IS NULL)
    + count(*) FILTER (WHERE NULLIF(btrim(plnt_mod), '') IS NULL)
    + count(*) FILTER (WHERE NULLIF(btrim(turno), '') IS NULL)
    + count(*) FILTER (WHERE NULLIF(btrim(plantas), '') IS NULL)
    + count(*) FILTER (WHERE NULLIF(btrim("desc"), '') IS NULL)
    + count(*) FILTER (WHERE NULLIF(btrim(frt_total), '') IS NULL) > 0
ORDER BY version;

\echo '--- R09 semanal 25: calidad y consistencia temporal ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), n AS (
    SELECT r.*,
           stg.fn_a_fecha(r.fecha_cos_ant) AS fecha_cos_ant_n,
           stg.fn_a_fecha(r.fecha_cos) AS fecha_cos_n,
           stg.fn_a_entero(r.sem) AS semana_n,
           stg.fn_a_real(r.area) AS area_n,
           stg.fn_a_real(r.frt_cos) AS frt_cos_n,
           stg.fn_a_real(r.rend) AS rend_n,
           stg.fn_a_real(r.kg) AS kg_n,
           stg.fn_a_entero(r.dr) AS dr_n
    FROM s
    JOIN raw.r09_forecast_semanal_25 r ON r.source_snapshot_id = s.snapshot_id
)
SELECT count(*) AS filas,
       count(*) FILTER (
           WHERE NULLIF(btrim(version), '') IS NULL
              OR NULLIF(btrim(campania), '') IS NULL
              OR NULLIF(btrim(fundo), '') IS NULL
              OR NULLIF(btrim(modulo), '') IS NULL
              OR NULLIF(btrim(turno), '') IS NULL
              OR NULLIF(btrim(lote), '') IS NULL
              OR NULLIF(btrim(fecha_cos), '') IS NULL
              OR NULLIF(btrim(sem), '') IS NULL
       ) AS claves_vacias,
       count(*) FILTER (WHERE NULLIF(btrim(fecha_cos_ant), '') IS NOT NULL AND fecha_cos_ant_n IS NULL) AS fecha_ant_invalida,
       count(*) FILTER (WHERE NULLIF(btrim(fecha_cos), '') IS NOT NULL AND fecha_cos_n IS NULL) AS fecha_cos_invalida,
       count(*) FILTER (WHERE NULLIF(btrim(area), '') IS NOT NULL AND area_n IS NULL) AS area_invalida,
       count(*) FILTER (WHERE NULLIF(btrim(frt_cos), '') IS NOT NULL AND frt_cos_n IS NULL) AS frt_cos_invalido,
       count(*) FILTER (WHERE NULLIF(btrim(rend), '') IS NOT NULL AND rend_n IS NULL) AS rend_invalido,
       count(*) FILTER (WHERE NULLIF(btrim(kg), '') IS NOT NULL AND kg_n IS NULL) AS kg_invalido,
       count(*) FILTER (WHERE NULLIF(btrim(dr), '') IS NOT NULL AND dr_n IS NULL) AS dr_invalido,
       count(*) FILTER (WHERE fecha_cos_ant_n > fecha_cos_n) AS fecha_invertida,
       count(*) FILTER (
           WHERE semana_n <> EXTRACT(WEEK FROM fecha_cos_n)::integer
       ) AS semana_distinta_de_fecha,
       count(*) FILTER (
           WHERE area_n < 0 OR frt_cos_n < 0 OR rend_n < 0 OR kg_n < 0 OR dr_n < 0
       ) AS valores_negativos,
       count(*) FILTER (WHERE kg_n = 0) AS kg_cero,
       min(fecha_cos_n) AS fecha_cos_min,
       max(fecha_cos_n) AS fecha_cos_max,
       min(semana_n) AS semana_min,
       max(semana_n) AS semana_max,
       min(kg_n) AS kg_min,
       max(kg_n) AS kg_max,
       sum(kg_n) AS kg_total
FROM n;

\echo '--- Forecast histórico: grano candidato ---'
SELECT 'r08_forecast_campania_24' AS tabla,
       count(*) AS filas,
       count(DISTINCT (version, fundo_ppto, modulo, anio, semana)) AS claves_distintas,
       count(*) - count(DISTINCT (version, fundo_ppto, modulo, anio, semana)) AS excedente
FROM raw.r08_forecast_campania_24
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
UNION ALL
SELECT 'r08_forecast_campania_25',
       count(*),
       count(DISTINCT (version, fundo, modulo, pln_fundo, plnt_mod, turno,
                       plantas, camp, anio, sem, "desc")),
       count(*) - count(DISTINCT (version, fundo, modulo, pln_fundo, plnt_mod, turno,
                                  plantas, camp, anio, sem, "desc"))
FROM raw.r08_forecast_campania_25
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
UNION ALL
SELECT 'r09_forecast_semanal_25',
       count(*),
       count(DISTINCT (version, campania, fundo, modulo, turno, lote, sem,
                       fecha_cos_ant, fecha_cos)),
       count(*) - count(DISTINCT (version, campania, fundo, modulo, turno, lote, sem,
                                  fecha_cos_ant, fecha_cos))
FROM raw.r09_forecast_semanal_25
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026');

\echo '--- R09 semanal 25: repetir solo por Semana no es suficiente ---'
SELECT count(*) AS filas,
       count(DISTINCT (version, campania, fundo, modulo, turno, lote, sem)) AS claves_sin_fechas,
       count(*) - count(DISTINCT (version, campania, fundo, modulo, turno, lote, sem)) AS excedente_sin_fechas,
       count(DISTINCT (version, campania, fundo, modulo, turno, lote, sem,
                       fecha_cos_ant, fecha_cos)) AS claves_con_fechas
FROM raw.r09_forecast_semanal_25
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026');

\echo '--- R08 campaña 25: duplicados exactos por huella ---'
SELECT source_row_hash,
       count(*) AS filas,
       min(source_row_number) AS fila_min,
       max(source_row_number) AS fila_max
FROM raw.r08_forecast_campania_25
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
GROUP BY source_row_hash
HAVING count(*) > 1
ORDER BY fila_min;

\echo '--- Forecast histórico: versiones y campañas ---'
SELECT 'r08_24' AS tabla,
       version,
       count(*) AS filas,
       min(stg.fn_a_entero(anio)) AS anio_min,
       max(stg.fn_a_entero(anio)) AS anio_max,
       min(stg.fn_a_entero(semana)) AS semana_min,
       max(stg.fn_a_entero(semana)) AS semana_max
FROM raw.r08_forecast_campania_24
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
GROUP BY version
UNION ALL
SELECT 'r08_25',
       version,
       count(*),
       min(stg.fn_a_entero(anio)),
       max(stg.fn_a_entero(anio)),
       min(stg.fn_a_entero(sem)),
       max(stg.fn_a_entero(sem))
FROM raw.r08_forecast_campania_25
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
GROUP BY version
ORDER BY tabla, version;

SELECT 'r08_25' AS tabla, camp AS campania, count(*) AS filas
FROM raw.r08_forecast_campania_25
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
GROUP BY camp
UNION ALL
SELECT 'r09_25', campania, count(*)
FROM raw.r09_forecast_semanal_25
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
GROUP BY campania
ORDER BY tabla, campania;

\echo '--- R09 semanal 25: versiones que solo cambian mayúsculas ---'
SELECT lower(version) AS codigo_normalizado,
       string_agg(DISTINCT version, ', ' ORDER BY version) AS grafias,
       sum(filas) AS filas
FROM (
    SELECT version, count(*) AS filas
    FROM raw.r09_forecast_semanal_25
    WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
    GROUP BY version
) v
GROUP BY lower(version)
HAVING count(*) > 1
ORDER BY codigo_normalizado;

\echo '--- R08 campaña 24: identidad de FundoPPto contra aliases aprobados ---'
SELECT r.fundo_ppto,
       count(*) AS filas,
       fa.alias_norm,
       fa.tipo,
       fa.empresa_id,
       fa.fundo_id,
       fa.ambiguo
FROM raw.r08_forecast_campania_24 r
LEFT JOIN core.m_fundo_alias fa
       ON fa.alias_norm = stg.fn_norm_texto(r.fundo_ppto)
WHERE r.source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
GROUP BY r.fundo_ppto, fa.alias_norm, fa.tipo, fa.empresa_id, fa.fundo_id, fa.ambiguo
ORDER BY r.fundo_ppto;

\echo '--- R08 campaña 25: identidad de Fundo contra aliases aprobados ---'
SELECT r.fundo,
       count(*) AS filas,
       fa.alias_norm,
       fa.tipo,
       fa.empresa_id,
       fa.fundo_id,
       fa.ambiguo
FROM raw.r08_forecast_campania_25 r
LEFT JOIN core.m_fundo_alias fa
       ON fa.alias_norm = stg.fn_norm_texto(r.fundo)
WHERE r.source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
GROUP BY r.fundo, fa.alias_norm, fa.tipo, fa.empresa_id, fa.fundo_id, fa.ambiguo
ORDER BY r.fundo;

\echo '--- R09 semanal 25: resolución de lote contra M_Lotes vigente ---'
WITH n AS (
    SELECT r.source_row_number,
           r.fundo,
           r.modulo,
           r.lote,
           stg.fn_norm_texto(r.fundo) AS fundo_norm,
           stg.fn_norm_modulo(r.modulo) AS modulo_norm,
           stg.fn_norm_lote(r.lote) AS lote_norm
    FROM raw.r09_forecast_semanal_25 r
    WHERE r.source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
), resol AS (
    SELECT n.source_row_number,
           n.fundo,
           n.modulo,
           n.lote,
           count(DISTINCT l.lote_id) AS lotes_resueltos
    FROM n
    LEFT JOIN core.m_fundo_alias fa ON fa.alias_norm = n.fundo_norm
    LEFT JOIN core.m_modulo m
           ON stg.fn_norm_modulo(m.codigo) = n.modulo_norm
          AND fa.alias_norm IS NOT NULL
          AND (fa.fundo_id = m.fundo_id OR fa.fundo_id IS NULL)
    LEFT JOIN core.m_lote l
           ON l.modulo_id = m.modulo_id
          AND stg.fn_norm_lote(l.codigo) = n.lote_norm
    GROUP BY n.source_row_number, n.fundo, n.modulo, n.lote
)
SELECT count(*) AS filas,
       count(*) FILTER (WHERE lotes_resueltos = 1) AS filas_resueltas,
       count(*) FILTER (WHERE lotes_resueltos = 0) AS filas_sin_resolver,
       count(*) FILTER (WHERE lotes_resueltos > 1) AS filas_ambiguas
FROM resol;

WITH n AS (
    SELECT r.source_row_number,
           r.fundo,
           r.modulo,
           r.lote,
           stg.fn_norm_texto(r.fundo) AS fundo_norm,
           stg.fn_norm_modulo(r.modulo) AS modulo_norm,
           stg.fn_norm_lote(r.lote) AS lote_norm
    FROM raw.r09_forecast_semanal_25 r
    WHERE r.source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
), resol AS (
    SELECT n.source_row_number,
           n.fundo,
           n.modulo,
           n.lote,
           count(DISTINCT l.lote_id) AS lotes_resueltos
    FROM n
    LEFT JOIN core.m_fundo_alias fa ON fa.alias_norm = n.fundo_norm
    LEFT JOIN core.m_modulo m
           ON stg.fn_norm_modulo(m.codigo) = n.modulo_norm
          AND fa.alias_norm IS NOT NULL
          AND (fa.fundo_id = m.fundo_id OR fa.fundo_id IS NULL)
    LEFT JOIN core.m_lote l
           ON l.modulo_id = m.modulo_id
          AND stg.fn_norm_lote(l.codigo) = n.lote_norm
    GROUP BY n.source_row_number, n.fundo, n.modulo, n.lote
)
SELECT fundo, modulo, lote, count(*) AS filas
FROM resol
WHERE lotes_resueltos = 0
GROUP BY fundo, modulo, lote
ORDER BY filas DESC, fundo, modulo, lote;

\echo '--- R09 histórico vs R09 vigente: pares versión/campaña ---'
WITH historico AS (
    SELECT DISTINCT version, campania
    FROM raw.r09_forecast_semanal_25
    WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
), vigente AS (
    SELECT DISTINCT version, campania
    FROM raw.r09_forecast_semanal
    WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
), comunes AS (
    SELECT version, campania FROM historico
    INTERSECT
    SELECT version, campania FROM vigente
)
SELECT (SELECT count(*) FROM historico) AS pares_historicos,
       (SELECT count(*) FROM vigente) AS pares_vigentes,
       (SELECT count(*) FROM comunes) AS pares_comunes;

\echo '--- R09 histórico: colisión con el catálogo core de versiones ---'
WITH historico AS (
    SELECT DISTINCT version, campania
    FROM raw.r09_forecast_semanal_25
    WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
)
SELECT count(*) AS pares_version_campania_historicos,
       count(v.version_id) AS pares_que_reutilizarian_version_core,
       count(DISTINCT v.version_id) AS versiones_core_reutilizadas
FROM historico h
LEFT JOIN core.m_version_forecast v
       ON v.sistema = 'semanal'
      AND v.codigo = h.version;

WITH historico AS (
    SELECT version,
           string_agg(DISTINCT campania, ', ' ORDER BY campania) AS campanias
    FROM raw.r09_forecast_semanal_25
    WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
    GROUP BY version
), colisiones AS (
    SELECT h.version, h.campanias, v.version_id
    FROM historico h
    JOIN core.m_version_forecast v
      ON v.sistema = 'semanal'
     AND v.codigo = h.version
)
SELECT *
FROM colisiones
ORDER BY version_id;

\echo '--- FIN: los tres históricos permanecen raw_only hasta aprobar versionado, grano e identidad ---'
