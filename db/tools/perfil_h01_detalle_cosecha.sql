-- ============================================================================
-- Perfilado read-only de H01_Detalle_Cosecha.
--
-- El objetivo es decidir si la fuente puede salir de raw_only. Este script no
-- crea tablas, no cambia datos y no modifica el ledger de migración.
-- La comparación contra H01_ProdHistorica es de conciliación; no implica que
-- una fuente pueda reemplazar a la otra.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

DO $h01_guard$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'PERFIL H01 BLOQUEADO: la BD actual es %, se exige aquanqa_migracion.',
            current_database();
    END IF;
END
$h01_guard$;

\echo '--- H01_Detalle_Cosecha: snapshot y volumen ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
)
SELECT s.snapshot_id,
       count(d.*) AS filas,
       min(stg.fn_a_fecha(d.fecha_cosecha)) AS fecha_min,
       max(stg.fn_a_fecha(d.fecha_cosecha)) AS fecha_max,
       count(DISTINCT d.source_row_hash) AS hashes_distintos,
       count(*) - count(DISTINCT d.source_row_hash) AS filas_extra_por_hash
FROM s
LEFT JOIN raw.h01_detalle_cosecha d
       ON d.source_snapshot_id = s.snapshot_id
GROUP BY s.snapshot_id;

\echo '--- H01_Detalle_Cosecha: campos de identidad y correspondencia campo/planta ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
)
SELECT count(*) AS filas,
       count(*) FILTER (WHERE NULLIF(btrim(d.fundo_campo), '') IS DISTINCT FROM NULLIF(btrim(d.fundo_planta), '')) AS fundo_mismatch,
       count(*) FILTER (WHERE NULLIF(btrim(d.modulo), '') IS DISTINCT FROM NULLIF(btrim(d.modulo_planta), '')) AS modulo_mismatch,
       count(*) FILTER (WHERE NULLIF(btrim(d.turno), '') IS DISTINCT FROM NULLIF(btrim(d.turno_planta), '')) AS turno_mismatch,
       count(*) FILTER (WHERE NULLIF(btrim(d.fundo_campo), '') IS NULL) AS fundo_campo_vacio,
       count(*) FILTER (WHERE NULLIF(btrim(d.fundo_planta), '') IS NULL) AS fundo_planta_vacio,
       count(*) FILTER (WHERE NULLIF(btrim(d.grupo), '') IS NULL) AS grupo_vacio,
       count(*) FILTER (WHERE NULLIF(btrim(d.modulo), '') IS NULL) AS modulo_vacio,
       count(*) FILTER (WHERE NULLIF(btrim(d.turno), '') IS NULL) AS turno_vacio,
       count(*) FILTER (WHERE NULLIF(btrim(d.lote), '') IS NULL) AS lote_vacio,
       count(*) FILTER (WHERE NULLIF(btrim(d.variedad), '') IS NULL) AS variedad_vacia,
       count(DISTINCT NULLIF(btrim(d.grupo), '')) AS grupos_distintos,
       count(DISTINCT NULLIF(btrim(d.fundo_campo), '')) AS fundos_distintos,
       count(DISTINCT NULLIF(btrim(d.modulo), '')) AS modulos_distintos,
       count(DISTINCT NULLIF(btrim(d.turno), '')) AS turnos_distintos,
       count(DISTINCT NULLIF(btrim(d.lote), '')) AS lotes_distintos,
       count(DISTINCT NULLIF(btrim(d.variedad), '')) AS variedades_distintas
FROM s
JOIN raw.h01_detalle_cosecha d ON d.source_snapshot_id = s.snapshot_id;

\echo '--- H01_Detalle_Cosecha: tipado numerico y reglas aritmeticas ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), n AS (
    SELECT d.*,
           stg.fn_a_real(d.area) AS area_n,
           stg.fn_a_real(d.kg_cosechados) AS kg_cosechados_n,
           stg.fn_a_real(d.kg_entierro) AS kg_entierro_n,
           stg.fn_a_real(d.kg_ingreso_planta) AS kg_ingreso_planta_n,
           stg.fn_a_real(d.kg_descarte) AS kg_descarte_n,
           stg.fn_a_real(d.kg_descarte_congelado) AS kg_descarte_congelado_n,
           stg.fn_a_real(d.kg_exportable) AS kg_exportable_n,
           stg.fn_a_real(d.jarras) AS jarras_n
    FROM s
    JOIN raw.h01_detalle_cosecha d ON d.source_snapshot_id = s.snapshot_id
)
SELECT count(*) AS filas,
       count(*) FILTER (WHERE NULLIF(btrim(area), '') IS NOT NULL AND area_n IS NULL) AS area_invalida,
       count(*) FILTER (WHERE NULLIF(btrim(kg_cosechados), '') IS NOT NULL AND kg_cosechados_n IS NULL) AS kg_cosechados_invalido,
       count(*) FILTER (WHERE NULLIF(btrim(kg_ingreso_planta), '') IS NOT NULL AND kg_ingreso_planta_n IS NULL) AS kg_ingreso_invalido,
       count(*) FILTER (WHERE NULLIF(btrim(kg_exportable), '') IS NOT NULL AND kg_exportable_n IS NULL) AS kg_exportable_invalido,
       count(*) FILTER (WHERE kg_cosechados_n < 0 OR kg_entierro_n < 0 OR kg_ingreso_planta_n < 0 OR kg_descarte_n < 0 OR kg_descarte_congelado_n < 0 OR kg_exportable_n < 0 OR jarras_n < 0) AS negativos,
       count(*) FILTER (WHERE kg_cosechados_n IS NOT NULL AND kg_entierro_n IS NOT NULL AND kg_ingreso_planta_n IS NOT NULL
                              AND abs(kg_cosechados_n - kg_entierro_n - kg_ingreso_planta_n) > 0.01) AS regla_cosechados_inconsistente,
       count(*) FILTER (WHERE kg_exportable_n IS NOT NULL AND kg_ingreso_planta_n IS NOT NULL
                              AND kg_descarte_n IS NOT NULL AND kg_descarte_congelado_n IS NOT NULL
                              AND abs(kg_exportable_n - kg_ingreso_planta_n + kg_descarte_n + kg_descarte_congelado_n) > 0.01) AS regla_exportable_inconsistente,
       max(abs(kg_cosechados_n - kg_entierro_n - kg_ingreso_planta_n))
           FILTER (WHERE kg_cosechados_n IS NOT NULL AND kg_entierro_n IS NOT NULL AND kg_ingreso_planta_n IS NOT NULL) AS max_delta_cosechados,
       max(abs(kg_exportable_n - kg_ingreso_planta_n + kg_descarte_n + kg_descarte_congelado_n))
           FILTER (WHERE kg_exportable_n IS NOT NULL AND kg_ingreso_planta_n IS NOT NULL
                         AND kg_descarte_n IS NOT NULL AND kg_descarte_congelado_n IS NOT NULL) AS max_delta_exportable
FROM n;

\echo '--- H01_Detalle_Cosecha: claves candidatas y grano observado ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), n AS (
    SELECT stg.fn_a_fecha(d.fecha_cosecha) AS fecha,
           NULLIF(btrim(d.fundo_campo), '') AS fundo_campo_fuente,
           NULLIF(btrim(d.fundo_planta), '') AS fundo_planta_fuente,
           NULLIF(btrim(d.grupo), '') AS grupo_fuente,
           NULLIF(btrim(d.modulo_planta), '') AS modulo_planta_fuente,
           NULLIF(btrim(d.turno_planta), '') AS turno_planta_fuente,
           NULLIF(btrim(d.modulo), '') AS modulo_fuente,
           NULLIF(btrim(d.turno), '') AS turno_fuente,
           NULLIF(btrim(d.lote), '') AS lote_fuente,
           NULLIF(btrim(d.variedad), '') AS variedad_fuente,
           stg.fn_norm_texto(d.fundo_campo) AS fundo_campo_norm,
           stg.fn_norm_texto(d.fundo_planta) AS fundo_planta_norm,
           stg.fn_norm_texto(d.grupo) AS grupo_norm,
           stg.fn_norm_modulo(d.modulo_planta) AS modulo_planta,
           stg.fn_norm_turno(d.turno_planta) AS turno_planta,
           stg.fn_norm_modulo(d.modulo) AS modulo,
           stg.fn_norm_turno(d.turno) AS turno,
           stg.fn_norm_lote(d.lote) AS lote,
           stg.fn_norm_texto(d.variedad) AS variedad
    FROM s
    JOIN raw.h01_detalle_cosecha d ON d.source_snapshot_id = s.snapshot_id
)
SELECT 'incluye_grupo_fuente' AS clave,
       count(*) AS filas,
       count(DISTINCT (fecha, fundo_campo_fuente, fundo_planta_fuente, grupo_fuente,
                       modulo_planta_fuente, turno_planta_fuente, modulo_fuente,
                       turno_fuente, lote_fuente, variedad_fuente)) AS grupos,
       count(*) - count(DISTINCT (fecha, fundo_campo_fuente, fundo_planta_fuente,
                                  grupo_fuente, modulo_planta_fuente, turno_planta_fuente,
                                  modulo_fuente, turno_fuente, lote_fuente, variedad_fuente)) AS filas_extra
FROM n
UNION ALL
SELECT 'incluye_grupo_normalizado',
       count(*),
       count(DISTINCT (fecha, fundo_campo_norm, fundo_planta_norm, grupo_norm,
                       modulo_planta, turno_planta, modulo, turno, lote, variedad)),
       count(*) - count(DISTINCT (fecha, fundo_campo_norm, fundo_planta_norm,
                                  grupo_norm, modulo_planta, turno_planta, modulo,
                                  turno, lote, variedad))
FROM n
UNION ALL
SELECT 'sin_grupo',
       count(*),
       count(DISTINCT (fecha, modulo, turno, lote, variedad)),
       count(*) - count(DISTINCT (fecha, modulo, turno, lote, variedad))
FROM n;

\echo '--- H01_Detalle_Cosecha: resolucion de identidad con M_Lotes ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), n AS (
    SELECT d.source_row_number,
           stg.fn_a_fecha(d.fecha_cosecha) AS fecha,
           stg.fn_norm_texto(d.fundo_campo) AS fundo_norm,
           stg.fn_norm_modulo(d.modulo) AS modulo_norm,
           stg.fn_norm_lote(d.lote) AS lote_norm
    FROM s
    JOIN raw.h01_detalle_cosecha d ON d.source_snapshot_id = s.snapshot_id
), r AS (
    SELECT n.source_row_number,
           count(DISTINCT l.lote_id) AS lotes_resueltos,
           min(l.lote_id) AS lote_id
    FROM n
    LEFT JOIN core.m_fundo_alias fa ON fa.alias_norm = n.fundo_norm
    LEFT JOIN core.m_modulo m
           ON stg.fn_norm_modulo(m.codigo) = n.modulo_norm
          AND fa.alias_norm IS NOT NULL
          AND (fa.fundo_id = m.fundo_id OR fa.fundo_id IS NULL)
    LEFT JOIN core.m_lote l
           ON l.modulo_id = m.modulo_id
          AND stg.fn_norm_lote(l.codigo) = n.lote_norm
    GROUP BY n.source_row_number
)
SELECT count(*) AS filas,
       count(*) FILTER (WHERE lotes_resueltos = 1) AS filas_resueltas,
       count(*) FILTER (WHERE lotes_resueltos = 0) AS filas_sin_resolver,
       count(*) FILTER (WHERE lotes_resueltos > 1) AS filas_ambiguas,
       count(DISTINCT lote_id) FILTER (WHERE lotes_resueltos = 1) AS lotes_core_distintos
FROM r;

\echo '--- H01_Detalle_Cosecha: filas no resolubles ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), n AS (
    SELECT d.source_row_number,
           d.fundo_campo, d.modulo, d.lote,
           stg.fn_norm_texto(d.fundo_campo) AS fundo_norm,
           stg.fn_norm_modulo(d.modulo) AS modulo_norm,
           stg.fn_norm_lote(d.lote) AS lote_norm
    FROM s
    JOIN raw.h01_detalle_cosecha d ON d.source_snapshot_id = s.snapshot_id
), r AS (
    SELECT n.source_row_number, n.fundo_campo, n.modulo, n.lote,
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
    GROUP BY n.source_row_number, n.fundo_campo, n.modulo, n.lote
)
SELECT fundo_campo, modulo, lote, count(*) AS filas
FROM r
WHERE lotes_resueltos = 0
GROUP BY fundo_campo, modulo, lote
ORDER BY filas DESC, fundo_campo, modulo, lote;

\echo '--- H01_Detalle_Cosecha: campaña derivable desde lote y fecha ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), n AS (
    SELECT d.source_row_number,
           stg.fn_a_fecha(d.fecha_cosecha) AS fecha,
           stg.fn_norm_texto(d.fundo_campo) AS fundo_norm,
           stg.fn_norm_modulo(d.modulo) AS modulo_norm,
           stg.fn_norm_lote(d.lote) AS lote_norm
    FROM s
    JOIN raw.h01_detalle_cosecha d ON d.source_snapshot_id = s.snapshot_id
), r AS (
    SELECT n.source_row_number, n.fecha, l.lote_id
    FROM n
    JOIN core.m_fundo_alias fa ON fa.alias_norm = n.fundo_norm
    JOIN core.m_modulo m
         ON stg.fn_norm_modulo(m.codigo) = n.modulo_norm
        AND (fa.fundo_id = m.fundo_id OR fa.fundo_id IS NULL)
    JOIN core.m_lote l
         ON l.modulo_id = m.modulo_id
        AND stg.fn_norm_lote(l.codigo) = n.lote_norm
)
SELECT count(*) AS filas_resueltas,
       count(*) FILTER (WHERE core.fn_campania_de_lote(lote_id, fecha) IS NULL) AS filas_sin_campania,
       count(DISTINCT core.fn_campania_de_lote(lote_id, fecha)) AS campanias_distintas
FROM r;

\echo '--- H01_Detalle_Cosecha vs H01_ProdHistorica: conciliacion por lote/fecha/turno ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), d0 AS (
    SELECT stg.fn_a_fecha(d.fecha_cosecha) AS fecha,
           stg.fn_norm_turno(d.turno) AS turno,
           stg.fn_norm_texto(d.fundo_campo) AS fundo_norm,
           stg.fn_norm_modulo(d.modulo) AS modulo_norm,
           stg.fn_norm_lote(d.lote) AS lote_norm,
           stg.fn_a_real(d.kg_cosechados) AS kg_cosechados,
           stg.fn_a_real(d.kg_ingreso_planta) AS kg_ingreso_planta,
           stg.fn_a_real(d.kg_exportable) AS kg_exportable
    FROM s
    JOIN raw.h01_detalle_cosecha d ON d.source_snapshot_id = s.snapshot_id
), d AS (
    SELECT d0.*, l.lote_id
    FROM d0
    JOIN core.m_fundo_alias fa ON fa.alias_norm = d0.fundo_norm
    JOIN core.m_modulo m
         ON stg.fn_norm_modulo(m.codigo) = d0.modulo_norm
        AND (fa.fundo_id = m.fundo_id OR fa.fundo_id IS NULL)
    JOIN core.m_lote l
         ON l.modulo_id = m.modulo_id
        AND stg.fn_norm_lote(l.codigo) = d0.lote_norm
), detalle AS (
    SELECT lote_id, fecha, turno,
           count(*) AS filas_detalle,
           sum(kg_cosechados) AS kg_cosechados,
           sum(kg_ingreso_planta) AS kg_ingreso_planta,
           sum(kg_exportable) AS kg_exportable
    FROM d
    GROUP BY lote_id, fecha, turno
), prod AS (
    SELECT lote_id, fecha, turno,
           count(*) AS filas_prod,
           sum(kg) AS kg_prod
    FROM stg.v_h01_cosecha h
    CROSS JOIN s
    WHERE h.source_snapshot_id = s.snapshot_id
      AND h.lote_id IS NOT NULL
      AND h.fecha IS NOT NULL
    GROUP BY lote_id, fecha, turno
), cmp AS (
    SELECT d.*, p.filas_prod, p.kg_prod
    FROM detalle d
    LEFT JOIN prod p USING (lote_id, fecha, turno)
)
SELECT count(*) AS grupos_detalle,
       count(*) FILTER (WHERE filas_prod IS NOT NULL) AS grupos_con_prod,
       count(*) FILTER (WHERE filas_prod IS NULL) AS grupos_sin_prod,
       sum(filas_detalle) AS filas_detalle_resueltas,
       sum(filas_detalle) FILTER (WHERE filas_prod IS NULL) AS filas_sin_prod,
       sum(kg_cosechados) AS total_kg_cosechados,
       sum(kg_ingreso_planta) AS total_kg_ingreso_planta,
       sum(kg_exportable) AS total_kg_exportable,
       sum(kg_prod) FILTER (WHERE filas_prod IS NOT NULL) AS total_kg_prod_comparable,
       count(*) FILTER (WHERE filas_prod IS NOT NULL AND abs(kg_cosechados - kg_prod) <= 0.01) AS cosechados_igual_001,
       count(*) FILTER (WHERE filas_prod IS NOT NULL AND abs(kg_ingreso_planta - kg_prod) <= 0.01) AS ingreso_igual_001,
       count(*) FILTER (WHERE filas_prod IS NOT NULL AND abs(kg_exportable - kg_prod) <= 0.01) AS exportable_igual_001,
       count(*) FILTER (WHERE filas_prod IS NOT NULL AND abs(kg_exportable - kg_prod) <= 1.00) AS exportable_igual_1,
       max(abs(kg_exportable - kg_prod)) FILTER (WHERE filas_prod IS NOT NULL) AS max_delta_exportable
FROM cmp;

\echo '--- H01_Detalle_Cosecha: mayores diferencias contra H01_ProdHistorica ---'
WITH s AS (
    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_id
), d0 AS (
    SELECT stg.fn_a_fecha(d.fecha_cosecha) AS fecha,
           stg.fn_norm_turno(d.turno) AS turno,
           stg.fn_norm_texto(d.fundo_campo) AS fundo_norm,
           stg.fn_norm_modulo(d.modulo) AS modulo_norm,
           stg.fn_norm_lote(d.lote) AS lote_norm,
           stg.fn_a_real(d.kg_exportable) AS kg_exportable,
           d.fundo_campo, d.modulo AS modulo_origen, d.lote AS lote_origen
    FROM s
    JOIN raw.h01_detalle_cosecha d ON d.source_snapshot_id = s.snapshot_id
), d AS (
    SELECT d0.*, l.lote_id
    FROM d0
    JOIN core.m_fundo_alias fa ON fa.alias_norm = d0.fundo_norm
    JOIN core.m_modulo m
         ON stg.fn_norm_modulo(m.codigo) = d0.modulo_norm
        AND (fa.fundo_id = m.fundo_id OR fa.fundo_id IS NULL)
    JOIN core.m_lote l
         ON l.modulo_id = m.modulo_id
        AND stg.fn_norm_lote(l.codigo) = d0.lote_norm
), detalle AS (
    SELECT lote_id, fecha, turno, min(fundo_campo) AS fundo_campo,
           min(modulo_origen) AS modulo, min(lote_origen) AS lote,
           sum(kg_exportable) AS kg_exportable
    FROM d
    GROUP BY lote_id, fecha, turno
), prod AS (
    SELECT lote_id, fecha, turno, sum(kg) AS kg_prod
    FROM stg.v_h01_cosecha h
    CROSS JOIN s
    WHERE h.source_snapshot_id = s.snapshot_id
      AND h.lote_id IS NOT NULL
      AND h.fecha IS NOT NULL
    GROUP BY lote_id, fecha, turno
)
SELECT d.lote_id, d.fecha, d.turno, d.fundo_campo, d.modulo, d.lote,
       round(d.kg_exportable::numeric, 2) AS kg_exportable_detalle,
       round(p.kg_prod::numeric, 2) AS kg_prod,
       round((d.kg_exportable - p.kg_prod)::numeric, 2) AS delta_kg
FROM detalle d
JOIN prod p USING (lote_id, fecha, turno)
WHERE abs(d.kg_exportable - p.kg_prod) > 100
ORDER BY abs(d.kg_exportable - p.kg_prod) DESC, d.fecha, d.lote_id
LIMIT 10;

\echo '--- FIN: H01 permanece raw_only hasta aprobar grano y conciliacion ---'
