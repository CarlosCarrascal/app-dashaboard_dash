-- ============================================================================
-- Cuarta etapa controlada: operación Access → stg → core
--
-- Fuentes: H00_VolumenCampo, H01_ProdHistorica, H02_BDElifab y H05_Clima.
-- H01_DetalleCosecha no participa: permanece raw_only hasta definir su grano.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

DO $b04_guard$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'B04 bloqueado: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;
END
$b04_guard$;

SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS source_snapshot_id
\gset snapshot_

SELECT coalesce(
    (
        SELECT max(r.migracion_run_id)
        FROM raw.migracion_run r
        WHERE r.source_snapshot_id = :snapshot_source_snapshot_id
          AND r.capa_destino = 'core'
          AND r.estado IN ('iniciado', 'en_proceso')
    ),
    raw.fn_iniciar_migracion(
        :snapshot_source_snapshot_id,
        'C2026',
        'core',
        'etl',
        'Ejecución incremental por bloques Access → raw → stg → core'
    )
) AS migracion_run_id
\gset mig_

SELECT raw.fn_iniciar_bloque(
    :snapshot_source_snapshot_id,
    'B04_OPERACION',
    'etl',
    'Operación: H00/H01 cosecha, H02 packing y H05 clima.'
) AS bloque_ejecucion_id
\gset bloque_

SELECT set_config('aquanqa.source_snapshot_id', :'snapshot_source_snapshot_id', false);
SELECT set_config('aquanqa.migracion_run_id', :'mig_migracion_run_id', false);
SELECT set_config('aquanqa.bloque_ejecucion_id', :'bloque_bloque_ejecucion_id', false);

UPDATE raw.migracion_run
   SET bloque_principal = 'B04_OPERACION'
 WHERE migracion_run_id = :mig_migracion_run_id;

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'en_proceso',
    NULL,
    NULL,
    NULL,
    0,
    'Materializando únicamente B04_OPERACION; forecast y fuentes pendientes siguen en raw.'
);

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'h00_volumen_campo', 'en_proceso', NULL, NULL, 0,
    'H00_VolumenCampo: kilos de campo, unificados con H01 en core.op_cosecha.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'h01_prod_historica', 'en_proceso', NULL, NULL, 0,
    'H01_ProdHistorica: paña, peso y plantas reconciliados con H00.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'h02_bd_elifab', 'en_proceso', NULL, NULL, 0,
    'H02_BDElifab: packing a nivel módulo; la columna Lote se conserva como nota.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'h05_clima', 'en_proceso', NULL, NULL, 0,
    'H05_Clima: una medición por timestamp; duplicados quedan explicados en qua.'
);

CALL stg.sp_materializar(
    ARRAY['h00_cosecha', 'h01_cosecha', 'h02_packing', 'h05_clima']
);
CALL core.sp_cargar_operacion_b04();
CALL raw.sp_registrar_lineage_operacion_b04();
CALL raw.sp_registrar_filas_no_lineage_b04();

DO $b04_cierre_tablas$
DECLARE
    r record;
    v_run bigint := current_setting('aquanqa.migracion_run_id')::bigint;
    v_bloque bigint := current_setting('aquanqa.bloque_ejecucion_id')::bigint;
    v_snapshot bigint := current_setting('aquanqa.source_snapshot_id')::bigint;
    v_cuarentena bigint;
    v_sin_rastro bigint;
    v_estado text;
BEGIN
    FOR r IN
        SELECT *
        FROM (
            SELECT 'h00_volumen_campo'::text AS tabla, 'H00_VolumenCampo'::text AS origen,
                   (SELECT count(*) FROM raw.h00_volumen_campo WHERE source_snapshot_id = v_snapshot)::bigint AS filas_raw,
                   (SELECT count(*) FROM stg.h00_cosecha)::bigint AS filas_stg,
                   (SELECT count(*) FROM core.op_cosecha WHERE en_h00)::bigint AS filas_core
            UNION ALL
            SELECT 'h01_prod_historica', 'H01_ProdHistorica',
                   (SELECT count(*) FROM raw.h01_prod_historica WHERE source_snapshot_id = v_snapshot),
                   (SELECT count(*) FROM stg.h01_cosecha),
                   (SELECT count(*) FROM core.op_cosecha WHERE en_h01)
            UNION ALL
            SELECT 'h02_bd_elifab', 'H02_BDElifab',
                   (SELECT count(*) FROM raw.h02_bd_elifab WHERE source_snapshot_id = v_snapshot),
                   (SELECT count(*) FROM stg.h02_packing),
                   (SELECT count(*) FROM core.op_packing)
            UNION ALL
            SELECT 'h05_clima', 'H05_Clima',
                   (SELECT count(*) FROM raw.h05_clima WHERE source_snapshot_id = v_snapshot),
                   (SELECT count(*) FROM stg.h05_clima),
                   (SELECT count(*) FROM core.op_clima)
        ) q
    LOOP
        SELECT count(*) INTO v_cuarentena
        FROM qua.rechazos
        WHERE bloque_ejecucion_id = v_bloque
          AND tabla_origen = r.origen;

        IF r.filas_raw <> r.filas_stg THEN
            RAISE EXCEPTION
                'B04 check-to-check fallido en %: raw=% y stg=%.',
                r.tabla, r.filas_raw, r.filas_stg;
        END IF;

        IF r.filas_core <= 0 THEN
            RAISE EXCEPTION 'B04 sin publicación core en %: filas_core=%.', r.tabla, r.filas_core;
        END IF;

        SELECT CASE r.tabla
                 WHEN 'h00_volumen_campo' THEN (
                     SELECT count(*) FROM stg.h00_cosecha s
                     WHERE s.source_snapshot_id = v_snapshot
                       AND NOT EXISTS (
                           SELECT 1 FROM raw.migracion_lineage_core l
                           WHERE l.source_snapshot_id = v_snapshot
                             AND l.source_table = 'h00_volumen_campo'
                             AND l.source_row_number = s.source_row_number
                       )
                       AND NOT EXISTS (
                           SELECT 1 FROM qua.rechazos q2
                           WHERE q2.bloque_ejecucion_id = v_bloque
                             AND q2.tabla_origen = r.origen
                             AND q2.fila->>'source_row_number' = s.source_row_number::text
                       )
                 )
                 WHEN 'h01_prod_historica' THEN (
                     SELECT count(*) FROM stg.h01_cosecha s
                     WHERE s.source_snapshot_id = v_snapshot
                       AND NOT EXISTS (
                           SELECT 1 FROM raw.migracion_lineage_core l
                           WHERE l.source_snapshot_id = v_snapshot
                             AND l.source_table = 'h01_prod_historica'
                             AND l.source_row_number = s.source_row_number
                       )
                       AND NOT EXISTS (
                           SELECT 1 FROM qua.rechazos q2
                           WHERE q2.bloque_ejecucion_id = v_bloque
                             AND q2.tabla_origen = r.origen
                             AND q2.fila->>'source_row_number' = s.source_row_number::text
                       )
                 )
                 WHEN 'h02_bd_elifab' THEN (
                     SELECT count(*) FROM stg.h02_packing s
                     WHERE s.source_snapshot_id = v_snapshot
                       AND NOT EXISTS (
                           SELECT 1 FROM raw.migracion_lineage_core l
                           WHERE l.source_snapshot_id = v_snapshot
                             AND l.source_table = 'h02_bd_elifab'
                             AND l.source_row_number = s.source_row_number
                       )
                       AND NOT EXISTS (
                           SELECT 1 FROM qua.rechazos q2
                           WHERE q2.bloque_ejecucion_id = v_bloque
                             AND q2.tabla_origen = r.origen
                             AND q2.fila->>'source_row_number' = s.source_row_number::text
                       )
                 )
                 WHEN 'h05_clima' THEN (
                     SELECT count(*) FROM stg.h05_clima s
                     WHERE s.source_snapshot_id = v_snapshot
                       AND NOT EXISTS (
                           SELECT 1 FROM raw.migracion_lineage_core l
                           WHERE l.source_snapshot_id = v_snapshot
                             AND l.source_table = 'h05_clima'
                             AND l.source_row_number = s.source_row_number
                       )
                       AND NOT EXISTS (
                           SELECT 1 FROM qua.rechazos q2
                           WHERE q2.bloque_ejecucion_id = v_bloque
                             AND q2.tabla_origen = r.origen
                             AND q2.fila->>'source_row_number' = s.source_row_number::text
                       )
                 )
               END
          INTO v_sin_rastro;

        IF v_sin_rastro <> 0 THEN
            RAISE EXCEPTION
                'B04 bloqueado en %: % filas no tienen lineage ni cuarentena.', r.tabla, v_sin_rastro;
        END IF;

        v_estado := CASE WHEN v_cuarentena = 0
                         THEN 'migrada'
                         ELSE 'migrada_con_observaciones' END;

        CALL raw.sp_registrar_tabla_migracion(
            v_run,
            r.tabla,
            v_estado,
            r.filas_stg,
            r.filas_core,
            v_cuarentena,
            format(
                'Check-to-check OK: raw=%s, stg=%s, core representativo=%s, cuarentena/incidencias=%s. '
                'H00/H01 se unifican y H02/H05 aplican su grano validado; el detalle queda en '
                'qua.rechazos y raw.migracion_lineage_core.',
                r.filas_raw, r.filas_stg, r.filas_core, v_cuarentena
            )
        );
    END LOOP;

    IF EXISTS (
        SELECT 1
        FROM qua.rechazos
        WHERE bloque_ejecucion_id = v_bloque
          AND (source_snapshot_id IS DISTINCT FROM v_snapshot
            OR migracion_run_id IS DISTINCT FROM v_run)
    ) THEN
        RAISE EXCEPTION 'B04 bloqueado: existe cuarentena sin linaje completo de ejecución.';
    END IF;
END
$b04_cierre_tablas$;

SELECT coalesce(sum(filas_raw), 0) AS filas_raw,
       coalesce(sum(filas_stg), 0) AS filas_stg,
       coalesce(sum(filas_core), 0) AS filas_core,
       coalesce(sum(filas_cuarentena), 0) AS filas_cuarentena
FROM raw.v_migracion_tablas
WHERE migracion_run_id = :mig_migracion_run_id
  AND tabla_raw IN ('h00_volumen_campo', 'h01_prod_historica', 'h02_bd_elifab', 'h05_clima')
\gset b04_

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'validado',
    :b04_filas_raw,
    :b04_filas_stg,
    :b04_filas_core,
    :b04_filas_cuarentena,
    'B04 validado: cosecha, packing y clima tienen grano, core o cuarentena y linaje completo.'
);

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'publicado',
    :b04_filas_raw,
    :b04_filas_stg,
    :b04_filas_core,
    :b04_filas_cuarentena,
    'B04 publicado con observaciones documentadas en qua.rechazos; H01_DetalleCosecha sigue raw_only.'
);

\echo ''
\echo '════════ Avance de la migración ════════'
SELECT migracion_run_id, source_snapshot_id, campania, estado,
       tablas_migradas, total_tablas_plan, tablas_pendientes, tablas_fallidas,
       porcentaje_migrado
FROM raw.v_migracion_resumen
WHERE migracion_run_id = :mig_migracion_run_id;

\echo ''
\echo '════════ Bloques ════════'
SELECT bloque, estado, tablas_raw, filas_raw, filas_stg, filas_core,
       filas_cuarentena, detalle
FROM raw.v_migracion_bloques
ORDER BY orden;
