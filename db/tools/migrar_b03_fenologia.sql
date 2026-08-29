-- ============================================================================
-- Tercera etapa controlada: evaluaciones fenológicas Access → stg → core
--
-- Fuentes: E01_Ramas, E02_ConteoFlores, E03_ConteoEstados, E04_Brotes,
-- E05_DiametrosBayas y E05_Seguimiento.
--
-- E05_Seguimiento es especial: una fila física de Access se convierte en hasta 25 filas
-- lógicas en staging. El ledger conserva ambas cifras y el linaje conserva el par
-- source_row_number + numero_muestra.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

DO $b03_guard$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'B03 bloqueado: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;
END
$b03_guard$;

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
    'B03_FENOLOGIA',
    'etl',
    'Evaluaciones fenológicas E01, E02, E03, E04 y E05 de Access.'
) AS bloque_ejecucion_id
\gset bloque_

SELECT set_config('aquanqa.source_snapshot_id', :'snapshot_source_snapshot_id', false);
SELECT set_config('aquanqa.migracion_run_id', :'mig_migracion_run_id', false);
SELECT set_config('aquanqa.bloque_ejecucion_id', :'bloque_bloque_ejecucion_id', false);

UPDATE raw.migracion_run
   SET bloque_principal = 'B03_FENOLOGIA'
 WHERE migracion_run_id = :mig_migracion_run_id;

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'en_proceso',
    NULL,
    NULL,
    NULL,
    0,
    'Materializando únicamente B03_FENOLOGIA; las fuentes de operación y forecast siguen en raw.'
);

CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'e01_ramas', 'en_proceso', NULL, NULL, 0,
    'E01_Ramas: cabecera por planta y detalle por rama, con deduplicación explícita.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'e02_conteo_flores', 'en_proceso', NULL, NULL, 0,
    'E02_ConteoFlores: todas las filas identificables; conflictos naturales quedan en qua.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'e03_conteo_estados', 'en_proceso', NULL, NULL, 0,
    'E03_ConteoEstados: item forma parte de la clave natural validada.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'e04_brotes', 'en_proceso', NULL, NULL, 0,
    'E04_Brotes: la fecha forma parte de la identidad de captura.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'e05_diametros_bayas', 'en_proceso', NULL, NULL, 0,
    'E05_DiametrosBayas: número de muestra derivado por orden estable.'
);
CALL raw.sp_registrar_tabla_migracion(
    :mig_migracion_run_id, 'e05_seguimiento', 'en_proceso', NULL, NULL, 0,
    'E05_Seguimiento: desancho de 25 pares; raw físico, staging lógico y core se reportan por separado.'
);

CALL stg.sp_refrescar_mapa_lote();
CALL stg.sp_materializar(
    ARRAY['e01_ramas', 'e02_flores', 'e03_estados', 'e04_brotes',
          'e05_bayas', 'e05_seguimiento']
);
CALL core.sp_cargar_fenologia_b03();
CALL raw.sp_registrar_lineage_fenologia_b03();
CALL raw.sp_registrar_filas_no_lineage_b03();

-- Check-to-check del bloque. No se exige raw = core porque el modelo tiene transformaciones
-- válidas: cabecera/detalle, deduplicación, claves sustitutas y desancho de E05. Sí se exige
-- raw = staging físico cuando aplica, que cada fila no representada tenga qua y que todo
-- rechazo del bloque tenga snapshot, run y bloque.
DO $b03_cierre_tablas$
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
            SELECT 'e01_ramas'::text AS tabla, 'E01_Ramas'::text AS origen,
                   (SELECT count(*) FROM raw.e01_ramas WHERE source_snapshot_id = v_snapshot)::bigint AS filas_raw,
                   (SELECT count(*) FROM stg.e01_ramas)::bigint AS filas_stg,
                   (SELECT count(*) FROM core.ev_rama_medicion)::bigint AS filas_core
            UNION ALL
            SELECT 'e02_conteo_flores', 'E02_ConteoFlores',
                   (SELECT count(*) FROM raw.e02_conteo_flores WHERE source_snapshot_id = v_snapshot),
                   (SELECT count(*) FROM stg.e02_flores),
                   (SELECT count(*) FROM core.ev_flores)
            UNION ALL
            SELECT 'e03_conteo_estados', 'E03_ConteoEstados',
                   (SELECT count(*) FROM raw.e03_conteo_estados WHERE source_snapshot_id = v_snapshot),
                   (SELECT count(*) FROM stg.e03_estados),
                   (SELECT count(*) FROM core.ev_estados)
            UNION ALL
            SELECT 'e04_brotes', 'E04_Brotes',
                   (SELECT count(*) FROM raw.e04_brotes WHERE source_snapshot_id = v_snapshot),
                   (SELECT count(*) FROM stg.e04_brotes),
                   (SELECT count(*) FROM core.ev_brotes)
            UNION ALL
            SELECT 'e05_diametros_bayas', 'E05_DiametrosBayas',
                   (SELECT count(*) FROM raw.e05_diametros_bayas WHERE source_snapshot_id = v_snapshot),
                   (SELECT count(*) FROM stg.e05_bayas),
                   (SELECT count(*) FROM core.ev_baya_medicion)
            UNION ALL
            SELECT 'e05_seguimiento', 'E05_Seguimiento',
                   (SELECT count(*) FROM raw.e05_seguimiento WHERE source_snapshot_id = v_snapshot),
                   (SELECT count(*) FROM stg.e05_seguimiento),
                   (SELECT count(*) FROM core.ev_evaluacion_baya)
        ) q
    LOOP
        SELECT count(*) INTO v_cuarentena
        FROM qua.rechazos
        WHERE bloque_ejecucion_id = v_bloque
          AND tabla_origen = r.origen;

        IF r.tabla <> 'e05_seguimiento' AND r.filas_raw <> r.filas_stg THEN
            RAISE EXCEPTION
                'B03 check-to-check fallido en %: raw=% y stg=%.',
                r.tabla, r.filas_raw, r.filas_stg;
        END IF;

        IF r.tabla = 'e05_seguimiento'
           AND (SELECT count(DISTINCT source_row_number) FROM stg.e05_seguimiento) <> r.filas_raw THEN
            RAISE EXCEPTION
                'B03 check-to-check fallido en E05_Seguimiento: raw físico=% y filas físicas representadas en stg=%.',
                r.filas_raw, (SELECT count(DISTINCT source_row_number) FROM stg.e05_seguimiento);
        END IF;

        IF r.filas_core <= 0 THEN
            RAISE EXCEPTION 'B03 sin publicación core en %: filas_core=%.', r.tabla, r.filas_core;
        END IF;

        -- Para E05 el staging es lógico (25 pares); para el resto cada fila representa la
        -- misma fuente física. La búsqueda usa el destino de cualquier lineage del bloque.
        IF r.tabla = 'e05_seguimiento' THEN
            SELECT count(*) INTO v_sin_rastro
            FROM stg.e05_seguimiento s
            WHERE s.source_snapshot_id = v_snapshot
              AND NOT EXISTS (
                  SELECT 1 FROM raw.migracion_lineage_core l
                  WHERE l.source_snapshot_id = v_snapshot
                    AND l.source_table = 'e05_seguimiento'
                    AND l.source_row_number = s.source_row_number
                    AND l.detalle->>'numero_muestra' = s.numero_muestra::text
              )
              AND NOT EXISTS (
                  SELECT 1 FROM qua.rechazos q2
                  WHERE q2.bloque_ejecucion_id = v_bloque
                    AND q2.tabla_origen = r.origen
                    AND q2.fila->>'source_row_number' = s.source_row_number::text
                    AND q2.fila->>'numero_muestra' = s.numero_muestra::text
              );
        ELSE
            SELECT count(*) INTO v_sin_rastro
            FROM (
                SELECT CASE r.tabla
                         WHEN 'e01_ramas' THEN source_row_number
                         WHEN 'e02_conteo_flores' THEN source_row_number
                         WHEN 'e03_conteo_estados' THEN source_row_number
                         WHEN 'e04_brotes' THEN source_row_number
                         WHEN 'e05_diametros_bayas' THEN source_row_number
                       END AS source_row_number
                FROM (
                    SELECT source_row_number FROM stg.e01_ramas WHERE r.tabla = 'e01_ramas'
                    UNION ALL SELECT source_row_number FROM stg.e02_flores WHERE r.tabla = 'e02_conteo_flores'
                    UNION ALL SELECT source_row_number FROM stg.e03_estados WHERE r.tabla = 'e03_conteo_estados'
                    UNION ALL SELECT source_row_number FROM stg.e04_brotes WHERE r.tabla = 'e04_brotes'
                    UNION ALL SELECT source_row_number FROM stg.e05_bayas WHERE r.tabla = 'e05_diametros_bayas'
                ) s
            ) s
            WHERE NOT EXISTS (
                SELECT 1 FROM raw.migracion_lineage_core l
                WHERE l.source_snapshot_id = v_snapshot
                  AND l.source_table = CASE r.tabla
                      WHEN 'e01_ramas' THEN 'e01_ramas'
                      WHEN 'e02_conteo_flores' THEN 'e02_conteo_flores'
                      WHEN 'e03_conteo_estados' THEN 'e03_conteo_estados'
                      WHEN 'e04_brotes' THEN 'e04_brotes'
                      WHEN 'e05_diametros_bayas' THEN 'e05_diametros_bayas'
                    END
                  AND l.source_row_number = s.source_row_number
            )
            AND NOT EXISTS (
                SELECT 1 FROM qua.rechazos q2
                WHERE q2.bloque_ejecucion_id = v_bloque
                  AND q2.tabla_origen = r.origen
                  AND q2.fila->>'source_row_number' = s.source_row_number::text
            );
        END IF;

        IF v_sin_rastro <> 0 THEN
            RAISE EXCEPTION
                'B03 bloqueado en %: % filas no tienen lineage ni cuarentena.', r.tabla, v_sin_rastro;
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
                'Check-to-check OK: raw físico=%s, stg lógico=%s, core representativo=%s, '
                'cuarentena/incidencias=%s. %s',
                r.filas_raw, r.filas_stg, r.filas_core, v_cuarentena,
                CASE WHEN r.tabla = 'e05_seguimiento'
                     THEN 'E05 se desancha de una fila Access a hasta 25 observaciones; las cabeceras y observaciones se trazan por fila+muestra.'
                     ELSE 'Transformaciones y excepciones documentadas en qua.rechazos y raw.migracion_lineage_core.' END
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
        RAISE EXCEPTION 'B03 bloqueado: existe cuarentena sin linaje completo de ejecución.';
    END IF;
END
$b03_cierre_tablas$;

SELECT coalesce(sum(filas_raw), 0) AS filas_raw,
       coalesce(sum(filas_stg), 0) AS filas_stg,
       coalesce(sum(filas_core), 0) AS filas_core,
       coalesce(sum(filas_cuarentena), 0) AS filas_cuarentena
FROM raw.v_migracion_tablas
WHERE migracion_run_id = :mig_migracion_run_id
  AND tabla_raw IN ('e01_ramas', 'e02_conteo_flores', 'e03_conteo_estados',
                    'e04_brotes', 'e05_diametros_bayas', 'e05_seguimiento')
\gset b03_

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'validado',
    :b03_filas_raw,
    :b03_filas_stg,
    :b03_filas_core,
    :b03_filas_cuarentena,
    'B03 validado: las seis fuentes fenológicas tienen staging, core o cuarentena y linaje completo.'
);

CALL raw.sp_registrar_bloque(
    :bloque_bloque_ejecucion_id,
    'publicado',
    :b03_filas_raw,
    :b03_filas_stg,
    :b03_filas_core,
    :b03_filas_cuarentena,
    'B03 publicado con observaciones documentadas en qua.rechazos; E05 conserva el desancho en lineage.'
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
