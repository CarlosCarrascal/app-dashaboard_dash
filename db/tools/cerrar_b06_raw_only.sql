-- ============================================================================
-- Cierre controlado de B06: fuentes conservadas en raw_only
--
-- Estas tablas sí están cargadas en raw y forman parte del snapshot Access,
-- pero no se publican en core hasta aprobar su grano/regla de consolidación:
-- H01_DetalleCosecha, M_PresupuestoMO y los históricos R08/R09.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

DO $b06_guard$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'B06 bloqueado: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;
END
$b06_guard$;

SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026') AS source_snapshot_id
\gset snapshot_

SELECT max(migracion_run_id) AS migracion_run_id
FROM raw.migracion_run
WHERE source_snapshot_id = :snapshot_source_snapshot_id
  AND capa_destino = 'core'
  AND estado IN ('iniciado', 'en_proceso')
\gset mig_

SELECT set_config('aquanqa.b06_run_id', :'mig_migracion_run_id', false);

DO $b06_run_guard$
BEGIN
    IF coalesce(current_setting('aquanqa.b06_run_id', true), '') = '' THEN
        RAISE EXCEPTION
            'B06 bloqueado: no existe una ejecución incremental activa para el snapshot Access.';
    END IF;
END
$b06_run_guard$;

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id,
    'h01_detalle_cosecha',
    'raw_only',
    NULL,
    NULL,
    0,
    'B06 raw_only: H01_DetalleCosecha queda en raw hasta definir su grano y relación con H01_ProdHistorica.'
);

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id,
    'm_presupuesto_mo',
    'raw_only',
    NULL,
    NULL,
    0,
    'B06 raw_only: M_PresupuestoMO queda en raw; no se encontró una relación aprobada con el modelo operativo.'
);

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id,
    'r08_forecast_campania_24',
    'raw_only',
    NULL,
    NULL,
    0,
    'B06 raw_only: histórico R08 campaña 24 conservado en raw hasta aprobar consolidación/versionado.'
);

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id,
    'r08_forecast_campania_25',
    'raw_only',
    NULL,
    NULL,
    0,
    'B06 raw_only: histórico R08 campaña 25 conservado en raw hasta aprobar consolidación/versionado.'
);

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id,
    'r09_forecast_semanal_25',
    'raw_only',
    NULL,
    NULL,
    0,
    'B06 raw_only: histórico R09 semanal 25 conservado en raw hasta aprobar consolidación/versionado.'
);

\echo ''
\echo '════════ Cierre B06 raw_only ════════'
SELECT migracion_run_id, source_snapshot_id, campania, estado,
       tablas_migradas, tablas_raw_only, total_tablas_plan,
       tablas_pendientes, tablas_fallidas, porcentaje_migrado
FROM raw.v_migracion_resumen
WHERE migracion_run_id = :mig_migracion_run_id;

\echo ''
SELECT tabla_raw, estado, filas_raw, filas_stg, filas_core,
       filas_cuarentena, detalle
FROM raw.v_migracion_tablas
WHERE migracion_run_id = :mig_migracion_run_id
  AND estado = 'raw_only'
ORDER BY tabla_raw;
