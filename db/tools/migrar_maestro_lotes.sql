-- ============================================================================
-- Primera etapa controlada: M_Lotes Access → stg → core
--
-- Ejecutar únicamente contra aquanqa_migracion:
--   node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/migrar_maestro_lotes.sql
--
-- No carga hechos ni toca la base aquanqa del dashboard. Las 23 tablas Access quedan
-- sembradas en raw.migracion_tabla; esta etapa solo cambia M_Lotes a migrada.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

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
        NULL,
        'C2026',
        'core',
        'etl',
        'Primera etapa: maestro de lotes Access validado'
    )
) AS migracion_run_id \gset mig_

\echo ''
\echo '════════ Migración controlada de M_Lotes ════════'
\echo 'Ejecución:' :mig_migracion_run_id

SELECT EXISTS (
    SELECT 1
    FROM raw.migracion_bloque_ejecucion
    WHERE modelo_version = raw.fn_modelo_version_vigente()
      AND source_snapshot_id = :snapshot_source_snapshot_id
      AND bloque = 'B01_IDENTIDAD'
      AND estado = 'publicado'
) AS ya_publicado
\gset bloque_

\if :bloque_ya_publicado
DO $bloque_ya_publicado$
BEGIN
    RAISE EXCEPTION
        'B01_IDENTIDAD ya fue publicado para este snapshot; no se repite sobre el mismo snapshot.';
END
$bloque_ya_publicado$;
\endif

SELECT raw.fn_iniciar_bloque(
    :snapshot_source_snapshot_id,
    'B01_IDENTIDAD',
    'etl',
    'Primera etapa: maestro de lotes Access validado con check-to-check.'
) AS bloque_ejecucion_id
\gset bloque_

UPDATE raw.migracion_run
   SET bloque_principal = 'B01_IDENTIDAD'
 WHERE migracion_run_id = :mig_migracion_run_id;

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'en_proceso',
    NULL,
    NULL,
    NULL,
    0,
    'Materializando únicamente B01_IDENTIDAD: M_Lotes Access → stg → core.'
);

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id,
    'm_lotes',
    'en_proceso',
    NULL,
    NULL,
    0,
    'Materializando stg.maestro_lote desde raw.v_m_lotes_principal_vigente (Access).'
);

CALL stg.sp_materializar(ARRAY['maestro_lote']);
CALL core.sp_cargar_ubicacion();

SELECT
    (SELECT count(*)::bigint FROM raw.v_m_lotes_principal_vigente) AS filas_raw,
    (SELECT count(*)::bigint FROM stg.maestro_lote) AS filas_stg,
    (SELECT count(*)::bigint FROM core.m_lote WHERE NOT es_sentinel) AS filas_core,
    (SELECT count(*)::bigint FROM qua.rechazos WHERE tabla_origen = 'M_Lotes') AS filas_cuarentena
\gset ctl_

SELECT (:ctl_filas_raw::bigint = :ctl_filas_stg::bigint
        AND :ctl_filas_stg::bigint = :ctl_filas_core::bigint
        AND :ctl_filas_cuarentena::bigint = 0) AS check_to_check_ok
\gset ctl_

\if :ctl_check_to_check_ok
\else
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id,
    'm_lotes',
    'fallida',
    :ctl_filas_stg,
    :ctl_filas_core,
    :ctl_filas_cuarentena,
    'Check-to-check fallido: revisar raw, stg, core y qua.'
);
CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'fallido',
    :ctl_filas_raw,
    :ctl_filas_stg,
    :ctl_filas_core,
    :ctl_filas_cuarentena,
    'Check-to-check fallido para B01_IDENTIDAD.'
);
DO $validar_m_lotes_fallida$
BEGIN
    RAISE EXCEPTION 'M_Lotes no pasó el check-to-check: revisar raw, stg, core y qua.';
END
$validar_m_lotes_fallida$;
\endif

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id,
    'm_lotes',
    'migrada',
    :ctl_filas_stg,
    :ctl_filas_core,
    :ctl_filas_cuarentena,
    'Check-to-check OK: Access/raw = stg = core; 0 filas en cuarentena.'
);

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'validado',
    :ctl_filas_raw,
    :ctl_filas_stg,
    :ctl_filas_core,
    :ctl_filas_cuarentena,
    'Check-to-check OK: B01_IDENTIDAD validado; 0 filas en cuarentena.'
);

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'publicado',
    :ctl_filas_raw,
    :ctl_filas_stg,
    :ctl_filas_core,
    :ctl_filas_cuarentena,
    'B01_IDENTIDAD publicado en core para el snapshot Access validado.'
);

-- B01 también debe cerrar la cobertura de linaje. La tabla M_Lotes tiene una correspondencia
-- directa con core.m_lote y derivaciones hacia el resto del maestro; sin este paso el cierre
-- check-to-check parece correcto, pero la auditoría final detecta sus filas como no trazadas.
CALL raw.sp_registrar_lineage_b01();

\echo ''
\echo '════════ Resumen de avance ════════'
SELECT migracion_run_id, source_snapshot_id, campania, capa_destino, estado,
       tablas_migradas, total_tablas_plan, tablas_pendientes, tablas_fallidas,
       porcentaje_migrado
FROM raw.v_migracion_resumen
WHERE migracion_run_id = :mig_migracion_run_id;

\echo ''
\echo '════════ Detalle por tabla ════════'
SELECT tabla_raw, estado, filas_raw, filas_stg, filas_core, filas_cuarentena,
       detalle
FROM raw.v_migracion_tablas
WHERE migracion_run_id = :mig_migracion_run_id
ORDER BY tabla_raw;

\echo ''
\echo '════════ Detalle del bloque ════════'
SELECT bloque, estado, tablas_raw, filas_raw, filas_stg, filas_core,
       filas_cuarentena, detalle
FROM raw.v_migracion_bloques
WHERE bloque = 'B01_IDENTIDAD';
