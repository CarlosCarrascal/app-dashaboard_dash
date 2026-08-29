-- ============================================================================
-- Segunda etapa controlada: maestros y contexto Access → stg → core
--
-- Ejecutar únicamente contra aquanqa_migracion:
--   node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/migrar_b02_contexto.sql
--
-- B02 no consulta ni materializa evaluaciones, operación ni forecast. Las fuentes posteriores
-- siguen en raw y no participan en la construcción del contexto.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

DO $b02_guard$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'B02 bloqueado: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;
END
$b02_guard$;

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
        'Ejecución B02: maestros y contexto Access'
    )
) AS migracion_run_id
\gset mig_

SELECT raw.fn_iniciar_bloque(
    :snapshot_source_snapshot_id,
    'B02_CONTEXTO',
    'etl',
    'Maestros y contexto: M_Evaluadores, M_Time, M_nMuestra, M_Poda y M_Equiv.'
) AS bloque_ejecucion_id
\gset bloque_

SELECT set_config('aquanqa.source_snapshot_id', :'snapshot_source_snapshot_id', false);
SELECT set_config('aquanqa.migracion_run_id', :'mig_migracion_run_id', false);
SELECT set_config('aquanqa.bloque_ejecucion_id', :'bloque_bloque_ejecucion_id', false);

UPDATE raw.migracion_run
   SET bloque_principal = 'B02_CONTEXTO'
 WHERE migracion_run_id = :mig_migracion_run_id;

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'en_proceso',
    NULL,
    NULL,
    NULL,
    0,
    'Materializando únicamente B02_CONTEXTO; no se leen fuentes posteriores.'
);

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'm_evaluadores', 'en_proceso', NULL, NULL, 0,
    'M_Evaluadores: staging y deduplicación por DNI.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'm_time', 'en_proceso', NULL, NULL, 0,
    'M_Time: calendario diario y semana de evaluación.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'm_n_muestra', 'en_proceso', NULL, NULL, 0,
    'M_nMuestra: muestreo requerido por ubicación.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'm_poda', 'en_proceso', NULL, NULL, 0,
    'M_Poda: campaña y evento de poda por lote.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'm_equivalencia_elifab', 'en_proceso', NULL, NULL, 0,
    'M_EquivalenciaElifab: vocabulario de productor y empresa.'
);

-- El mapa debe calcularse después de B01 y antes de materializar las vistas que llevan lote_id.
CALL stg.sp_refrescar_mapa_lote();
CALL stg.sp_materializar(
    ARRAY['m_evaluadores', 'm_time', 'm_n_muestra', 'm_poda']
);
CALL core.sp_cargar_contexto_b02();
CALL raw.sp_registrar_lineage_contexto_b02();

-- Cada fuente tiene su propio grano. Para M_Equiv no hay staging físico: su check-to-check usa
-- raw como staging lógico y deja la carga directa documentada.
DO $b02_cierre_tablas$
DECLARE
    r record;
    v_run bigint := current_setting('aquanqa.migracion_run_id')::bigint;
    v_bloque bigint := current_setting('aquanqa.bloque_ejecucion_id')::bigint;
    v_cuarentena bigint;
    v_estado text;
BEGIN
    FOR r IN
        SELECT *
        FROM (
            SELECT 'm_evaluadores'::text AS tabla, 'M_Evaluadores'::text AS origen,
                   (SELECT count(*) FROM raw.m_evaluadores
                     WHERE source_snapshot_id = current_setting('aquanqa.source_snapshot_id')::bigint)::bigint AS filas_raw,
                   (SELECT count(*) FROM stg.m_evaluadores)::bigint AS filas_stg,
                   (SELECT count(*) FROM core.m_evaluador)::bigint AS filas_core
            UNION ALL
            SELECT 'm_time', 'M_Time',
                   (SELECT count(*) FROM raw.m_time
                     WHERE source_snapshot_id = current_setting('aquanqa.source_snapshot_id')::bigint),
                   (SELECT count(*) FROM stg.m_time),
                   (SELECT count(*) FROM core.t_calendario)
            UNION ALL
            SELECT 'm_n_muestra', 'M_nMuestra',
                   (SELECT count(*) FROM raw.m_n_muestra
                     WHERE source_snapshot_id = current_setting('aquanqa.source_snapshot_id')::bigint),
                   (SELECT count(*) FROM stg.m_n_muestra),
                   (SELECT count(*) FROM core.cfg_muestra_requerida)
            UNION ALL
            SELECT 'm_poda', 'M_Poda',
                   (SELECT count(*) FROM raw.m_poda
                     WHERE source_snapshot_id = current_setting('aquanqa.source_snapshot_id')::bigint),
                   (SELECT count(*) FROM stg.m_poda),
                   (SELECT count(*) FROM core.evt_poda)
            UNION ALL
            SELECT 'm_equivalencia_elifab', 'M_EquivalenciaElifab',
                   (SELECT count(*) FROM raw.m_equivalencia_elifab
                     WHERE source_snapshot_id = current_setting('aquanqa.source_snapshot_id')::bigint),
                   (SELECT count(*) FROM raw.m_equivalencia_elifab
                     WHERE source_snapshot_id = current_setting('aquanqa.source_snapshot_id')::bigint),
                   (SELECT count(*) FROM core.m_productor_equivalencia)
        ) q
    LOOP
        SELECT count(*) INTO v_cuarentena
        FROM qua.rechazos
        WHERE bloque_ejecucion_id = v_bloque
          AND tabla_origen = r.origen;

        IF r.filas_raw <> r.filas_stg THEN
            RAISE EXCEPTION
                'B02 check-to-check fallido en %: raw=% y stg=%.',
                r.tabla, r.filas_raw, r.filas_stg;
        END IF;

        IF r.filas_core + v_cuarentena <> r.filas_raw THEN
            RAISE EXCEPTION
                'B02 check-to-check fallido en %: raw=% core=% cuarentena=%.',
                r.tabla, r.filas_raw, r.filas_core, v_cuarentena;
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
                'Check-to-check OK: raw=%s, stg=%s, core=%s, cuarentena=%s. %s',
                r.filas_raw, r.filas_stg, r.filas_core, v_cuarentena,
                CASE WHEN v_cuarentena = 0
                     THEN 'Sin observaciones.'
                     ELSE 'Observaciones documentadas en qua.rechazos.' END
            )
        );
    END LOOP;

    IF EXISTS (
        SELECT 1
        FROM qua.rechazos
        WHERE bloque_ejecucion_id = v_bloque
          AND (source_snapshot_id IS DISTINCT FROM current_setting('aquanqa.source_snapshot_id')::bigint
            OR migracion_run_id IS DISTINCT FROM v_run)
    ) THEN
        RAISE EXCEPTION 'B02 bloqueado: existe cuarentena sin linaje completo de ejecución.';
    END IF;
END
$b02_cierre_tablas$;

SELECT coalesce(sum(filas_raw), 0) AS filas_raw,
       coalesce(sum(filas_stg), 0) AS filas_stg,
       coalesce(sum(filas_core), 0) AS filas_core,
       coalesce(sum(filas_cuarentena), 0) AS filas_cuarentena
FROM raw.v_migracion_tablas
WHERE migracion_run_id = :mig_migracion_run_id
  AND tabla_raw IN ('m_evaluadores', 'm_time', 'm_n_muestra', 'm_poda', 'm_equivalencia_elifab')
\gset b02_

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'validado',
    :b02_filas_raw,
    :b02_filas_stg,
    :b02_filas_core,
    :b02_filas_cuarentena,
    'B02 validado: todas las fuentes cuadran y las excepciones están documentadas.'
);

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'publicado',
    :b02_filas_raw,
    :b02_filas_stg,
    :b02_filas_core,
    :b02_filas_cuarentena,
    'B02 publicado con observaciones documentadas en qua.rechazos; no se crean FK nuevas automáticamente.'
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
