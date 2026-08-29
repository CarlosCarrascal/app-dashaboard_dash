-- ============================================================================
-- Auditoria final de la migracion Access C2026.
-- Solo lectura: valida el ledger, los bloques, el linaje y la cuarentena.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

DO $auditoria_guard$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_modelo text;
    v_missing bigint;
    v_q_sin_traza bigint;
    v_raw_only_invalid bigint;
    v_lineage_sin_contexto bigint;
    v_bloques bigint;
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'AUDITORIA BLOQUEADA: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;

    SELECT raw.fn_snapshot_access_publicado(NULL, 'C2026')
      INTO v_snapshot;

    SELECT max(migracion_run_id)
      INTO v_run
    FROM raw.migracion_run
    WHERE source_snapshot_id = v_snapshot
      AND campania = 'C2026'
      AND capa_destino = 'core';

    IF v_run IS NULL THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: no existe run de migracion para el snapshot %. ', v_snapshot;
    END IF;

    v_modelo := raw.fn_modelo_version_vigente();

    IF EXISTS (
        SELECT 1 FROM pg_namespace
        WHERE nspname IN ('dim', 'fact', 'reporting', 'analytics', 'mlflow')
    ) THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: target contiene esquemas BI fuera de fase.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM raw.migracion_run
        WHERE migracion_run_id = v_run
          AND estado = 'completada_con_observaciones'
    ) THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: el run % no esta cerrado como completada_con_observaciones.', v_run;
    END IF;

    IF (
        SELECT count(*) FROM raw.migracion_tabla
        WHERE migracion_run_id = v_run
    ) <> 23 THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: el run % no tiene exactamente 23 controles.', v_run;
    END IF;

    IF EXISTS (
        SELECT 1 FROM raw.migracion_tabla
        WHERE migracion_run_id = v_run
          AND estado IN ('pendiente', 'en_proceso', 'fallida')
    ) THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: existen tablas pendientes, en_proceso o fallidas.';
    END IF;

    IF (
        SELECT count(*) FROM raw.migracion_tabla
        WHERE migracion_run_id = v_run AND estado IN ('migrada', 'migrada_con_observaciones')
    ) <> 18 THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: se esperaban 18 fuentes publicadas en core.';
    END IF;

    IF (
        SELECT count(*) FROM raw.migracion_tabla
        WHERE migracion_run_id = v_run AND estado = 'raw_only'
    ) <> 5 THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: se esperaban 5 fuentes cerradas como raw_only.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM raw.migracion_tabla
        WHERE migracion_run_id = v_run
          AND estado = 'raw_only'
          AND (filas_raw IS NULL OR filas_stg IS NOT NULL OR filas_core IS NOT NULL
               OR filas_cuarentena <> 0 OR detalle IS NULL OR btrim(detalle) = '')
    ) THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: raw_only no cumple el contrato de cierre.';
    END IF;

    SELECT count(*)
      INTO v_bloques
    FROM raw.v_migracion_bloques
    WHERE source_snapshot_id = v_snapshot
      AND estado = 'publicado'
      AND bloque IN ('B01_IDENTIDAD', 'B02_CONTEXTO', 'B03_FENOLOGIA',
                     'B04_OPERACION', 'B05_PRONOSTICO');

    IF v_bloques <> 5 THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: se esperaban 5 bloques core publicados; existen %.', v_bloques;
    END IF;

    SELECT count(*)
      INTO v_lineage_sin_contexto
    FROM raw.migracion_lineage_core
    WHERE migracion_run_id = v_run
      AND (modelo_version IS DISTINCT FROM v_modelo
           OR source_snapshot_id IS DISTINCT FROM v_snapshot
           OR bloque_ejecucion_id IS NULL);

    IF v_lineage_sin_contexto <> 0 THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: existen % lineas de linaje sin contexto completo.',
            v_lineage_sin_contexto;
    END IF;

    SELECT count(*)
      INTO v_q_sin_traza
    FROM qua.rechazos
    WHERE migracion_run_id = v_run
      AND (source_snapshot_id IS DISTINCT FROM v_snapshot
           OR bloque_ejecucion_id IS NULL
           OR fila IS NULL
           OR fila = '{}'::jsonb
           OR detalle IS NULL OR btrim(detalle) = '');

    IF v_q_sin_traza <> 0 THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: existen % rechazos sin traza suficiente.', v_q_sin_traza;
    END IF;

    SELECT count(*)
      INTO v_raw_only_invalid
    FROM raw.migracion_tabla mt
    WHERE mt.migracion_run_id = v_run
      AND mt.estado = 'raw_only'
      AND EXISTS (
          SELECT 1
          FROM raw.migracion_lineage_core l
          WHERE l.migracion_run_id = v_run
            AND l.source_snapshot_id = v_snapshot
            AND l.source_table = mt.tabla_raw
      );

    IF v_raw_only_invalid <> 0 THEN
        RAISE EXCEPTION 'AUDITORIA BLOQUEADA: existe linaje core para una fuente raw_only.';
    END IF;

    -- Cobertura fisica: cada fila de las 18 fuentes publicables debe aparecer
    -- en linaje o en cuarentena. E05_Seguimiento se desancha en staging, por
    -- eso la comprobacion se hace a nivel de source_row_number fisico.
    WITH src AS (
        SELECT 'm_lotes'::text AS tabla, source_row_number::bigint AS row_num FROM raw.m_lotes WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'm_evaluadores', source_row_number::bigint FROM raw.m_evaluadores WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'm_time', source_row_number::bigint FROM raw.m_time WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'm_n_muestra', source_row_number::bigint FROM raw.m_n_muestra WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'm_poda', source_row_number::bigint FROM raw.m_poda WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'm_equivalencia_elifab', source_row_number::bigint FROM raw.m_equivalencia_elifab WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'e01_ramas', source_row_number::bigint FROM raw.e01_ramas WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'e02_conteo_flores', source_row_number::bigint FROM raw.e02_conteo_flores WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'e03_conteo_estados', source_row_number::bigint FROM raw.e03_conteo_estados WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'e04_brotes', source_row_number::bigint FROM raw.e04_brotes WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'e05_diametros_bayas', source_row_number::bigint FROM raw.e05_diametros_bayas WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'e05_seguimiento', source_row_number::bigint FROM raw.e05_seguimiento WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'h00_volumen_campo', source_row_number::bigint FROM raw.h00_volumen_campo WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'h01_prod_historica', source_row_number::bigint FROM raw.h01_prod_historica WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'h02_bd_elifab', source_row_number::bigint FROM raw.h02_bd_elifab WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'h05_clima', source_row_number::bigint FROM raw.h05_clima WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'r08_forecast_campania', source_row_number::bigint FROM raw.r08_forecast_campania WHERE source_snapshot_id = v_snapshot
        UNION ALL SELECT 'r09_forecast_semanal', source_row_number::bigint FROM raw.r09_forecast_semanal WHERE source_snapshot_id = v_snapshot
    ), lin AS (
        SELECT DISTINCT source_table AS tabla, source_row_number::bigint AS row_num
        FROM raw.migracion_lineage_core
        WHERE migracion_run_id = v_run AND source_snapshot_id = v_snapshot
    ), qua AS (
        SELECT DISTINCT CASE
            WHEN tabla_origen = 'M_Evaluadores' THEN 'm_evaluadores'
            WHEN tabla_origen = 'M_nMuestra' THEN 'm_n_muestra'
            WHEN tabla_origen = 'M_Poda' THEN 'm_poda'
            WHEN tabla_origen = 'E01_Ramas' THEN 'e01_ramas'
            WHEN tabla_origen = 'E02_ConteoFlores' THEN 'e02_conteo_flores'
            WHEN tabla_origen = 'E03_ConteoEstados' THEN 'e03_conteo_estados'
            WHEN tabla_origen = 'E04_Brotes' THEN 'e04_brotes'
            WHEN tabla_origen = 'E05_DiametrosBayas' THEN 'e05_diametros_bayas'
            WHEN tabla_origen = 'E05_Seguimiento' THEN 'e05_seguimiento'
            WHEN tabla_origen = 'H00_VolumenCampo' THEN 'h00_volumen_campo'
            WHEN tabla_origen = 'H01_ProdHistorica' THEN 'h01_prod_historica'
            WHEN tabla_origen = 'H02_BDElifab' THEN 'h02_bd_elifab'
            WHEN tabla_origen LIKE 'R08_Forecast_Camp%' THEN 'r08_forecast_campania'
            WHEN tabla_origen = 'R09_Forecast_Semanal' THEN 'r09_forecast_semanal'
        END AS tabla,
        (fila->>'source_row_number')::bigint AS row_num
        FROM qua.rechazos
        WHERE migracion_run_id = v_run
          AND source_snapshot_id = v_snapshot
          AND fila ? 'source_row_number'
    ), represented AS (
        SELECT tabla, row_num FROM lin
        UNION
        SELECT tabla, row_num FROM qua WHERE tabla IS NOT NULL
    )
    SELECT count(*)
      INTO v_missing
    FROM src s
    WHERE NOT EXISTS (
        SELECT 1
        FROM represented x
        WHERE x.tabla = s.tabla AND x.row_num = s.row_num
    );

    IF v_missing <> 0 THEN
        RAISE EXCEPTION
            'AUDITORIA BLOQUEADA: existen % filas Access publicables sin linaje ni cuarentena.',
            v_missing;
    END IF;
END
$auditoria_guard$;

SELECT current_database() AS base_validada,
       raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_access,
       (SELECT max(migracion_run_id)
        FROM raw.migracion_run
        WHERE campania = 'C2026' AND capa_destino = 'core') AS migracion_run_id,
       (SELECT estado FROM raw.migracion_run
        WHERE migracion_run_id = (SELECT max(migracion_run_id)
                                  FROM raw.migracion_run
                                  WHERE campania = 'C2026' AND capa_destino = 'core')) AS estado_run,
       (SELECT count(*) FROM raw.migracion_tabla
        WHERE migracion_run_id = (SELECT max(migracion_run_id)
                                  FROM raw.migracion_run
                                  WHERE campania = 'C2026' AND capa_destino = 'core'
                                  )) AS controles_tabla,
       'OK: auditoria final superada' AS resultado;

SELECT bloque, estado, tablas_raw, filas_raw, filas_stg, filas_core, filas_cuarentena
FROM raw.v_migracion_bloques
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
ORDER BY orden;
