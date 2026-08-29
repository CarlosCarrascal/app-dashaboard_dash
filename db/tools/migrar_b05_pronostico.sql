-- ============================================================================
-- Quinta etapa controlada: pronóstico Access → stg → core
--
-- Fuentes publicables: R08_Forecast_Campaña y R09_Forecast_Semanal.
-- Los históricos R08/R09 _24/_25 permanecen raw_only hasta aprobar su regla
-- de consolidación con el negocio.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

DO $b05_guard$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'B05 bloqueado: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;
END
$b05_guard$;

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
    'B05_PRONOSTICO',
    'etl',
    'Pronóstico: R08 y R09 vigentes; históricos pendientes de regla de consolidación.'
) AS bloque_ejecucion_id
\gset bloque_

SELECT set_config('aquanqa.source_snapshot_id', :'snapshot_source_snapshot_id', false);
SELECT set_config('aquanqa.migracion_run_id', :'mig_migracion_run_id', false);
SELECT set_config('aquanqa.bloque_ejecucion_id', :'bloque_bloque_ejecucion_id', false);

UPDATE raw.migracion_run
   SET bloque_principal = 'B05_PRONOSTICO'
 WHERE migracion_run_id = :mig_migracion_run_id;

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'en_proceso',
    NULL,
    NULL,
    NULL,
    0,
    'Materializando únicamente B05_PRONOSTICO; históricos de forecast siguen en raw.'
);

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'r08_forecast_campania', 'en_proceso', NULL, NULL, 0,
    'R08_Forecast_Campaña: pronóstico vigente, versionado por campaña.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'r09_forecast_semanal', 'en_proceso', NULL, NULL, 0,
    'R09_Forecast_Semanal: pronóstico vigente, versionado semanalmente.'
);

CALL stg.sp_materializar(ARRAY['r08_forecast', 'r09_forecast']);
CALL core.sp_cargar_pronostico_b05();
CALL raw.sp_registrar_lineage_pronostico_b05();
CALL raw.sp_registrar_filas_no_lineage_b05();

DO $b05_cierre_tablas$
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
            SELECT 'r08_forecast_campania'::text AS tabla,
                   'R08_Forecast_Campaña'::text AS origen,
                   (SELECT count(*) FROM raw.r08_forecast_campania
                    WHERE source_snapshot_id = v_snapshot)::bigint AS filas_raw,
                   (SELECT count(*) FROM stg.r08_forecast)::bigint AS filas_stg,
                   (SELECT count(*) FROM core.op_forecast_campania)::bigint AS filas_core
            UNION ALL
            SELECT 'r09_forecast_semanal',
                   'R09_Forecast_Semanal',
                   (SELECT count(*) FROM raw.r09_forecast_semanal
                    WHERE source_snapshot_id = v_snapshot),
                   (SELECT count(*) FROM stg.r09_forecast),
                   (SELECT count(*) FROM core.op_forecast_semanal)
        ) q
    LOOP
        SELECT count(*) INTO v_cuarentena
        FROM qua.rechazos
        WHERE bloque_ejecucion_id = v_bloque
          AND tabla_origen = r.origen;

        IF r.filas_raw <> r.filas_stg THEN
            RAISE EXCEPTION
                'B05 check-to-check fallido en %: raw=% y stg=%.',
                r.tabla, r.filas_raw, r.filas_stg;
        END IF;

        IF r.filas_core <= 0 THEN
            RAISE EXCEPTION 'B05 sin publicación core en %: filas_core=%.', r.tabla, r.filas_core;
        END IF;

        SELECT CASE r.tabla
                 WHEN 'r08_forecast_campania' THEN (
                     SELECT count(*) FROM stg.r08_forecast s
                     WHERE s.source_snapshot_id = v_snapshot
                       AND s.version IS NOT NULL AND s.version <> ''
                       AND NOT EXISTS (
                           SELECT 1 FROM raw.migracion_lineage_core l
                           WHERE l.source_snapshot_id = v_snapshot
                             AND l.source_table = 'r08_forecast_campania'
                             AND l.source_row_number = s.source_row_number
                             AND l.destino_tabla = 'forecast_campania'
                       )
                       AND NOT EXISTS (
                           SELECT 1 FROM qua.rechazos q2
                           WHERE q2.bloque_ejecucion_id = v_bloque
                             AND q2.tabla_origen = r.origen
                             AND q2.fila->>'source_row_number' = s.source_row_number::text
                       )
                 )
                 WHEN 'r09_forecast_semanal' THEN (
                     SELECT count(*) FROM stg.r09_forecast s
                     WHERE s.source_snapshot_id = v_snapshot
                       AND s.version IS NOT NULL AND s.version <> ''
                       AND NOT EXISTS (
                           SELECT 1 FROM raw.migracion_lineage_core l
                           WHERE l.source_snapshot_id = v_snapshot
                             AND l.source_table = 'r09_forecast_semanal'
                             AND l.source_row_number = s.source_row_number
                             AND l.destino_tabla = 'forecast_semanal'
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
                'B05 bloqueado en %: % filas no tienen lineage ni cuarentena.', r.tabla, v_sin_rastro;
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
                'Check-to-check OK: raw=%s, stg=%s, core=%s, cuarentena/incidencias=%s. '
                'Las versiones y hechos conservan linaje hacia el snapshot; los históricos '
                'R08/R09 _24/_25 quedan pendientes como raw_only.',
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
        RAISE EXCEPTION 'B05 bloqueado: existe cuarentena sin linaje completo de ejecución.';
    END IF;
END
$b05_cierre_tablas$;

SELECT coalesce(sum(filas_raw), 0) AS filas_raw,
       coalesce(sum(filas_stg), 0) AS filas_stg,
       coalesce(sum(filas_core), 0) AS filas_core,
       coalesce(sum(filas_cuarentena), 0) AS filas_cuarentena
FROM raw.v_migracion_tablas
WHERE migracion_run_id = :mig_migracion_run_id
  AND tabla_raw IN ('r08_forecast_campania', 'r09_forecast_semanal')
\gset b05_

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'validado',
    :b05_filas_raw,
    :b05_filas_stg,
    :b05_filas_core,
    :b05_filas_cuarentena,
    'B05 validado: R08/R09 vigentes tienen check-to-check, core o cuarentena y linaje completo.'
);

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'publicado',
    :b05_filas_raw,
    :b05_filas_stg,
    :b05_filas_core,
    :b05_filas_cuarentena,
    'B05 publicado con observaciones documentadas en qua.rechazos; los históricos permanecen raw_only.'
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
