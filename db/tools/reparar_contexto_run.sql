-- Correccion de compatibilidad para bloques abiertos antes de que el vinculo
-- bloque -> migracion_run quedara obligatorio en el procedimiento de apertura.
-- No cambia datos de negocio: completa solo el contexto tecnico de auditoria.

\set ON_ERROR_STOP on
\pset pager off

DO $reparar_run$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloques integer;
    v_lineages integer;
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'Correccion bloqueada: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;

    v_snapshot := raw.fn_snapshot_access_publicado(NULL, 'C2026');

    SELECT max(migracion_run_id)
      INTO v_run
    FROM raw.migracion_run
    WHERE source_snapshot_id = v_snapshot
      AND campania = 'C2026'
      AND capa_destino = 'core';

    IF v_run IS NULL THEN
        RAISE EXCEPTION 'No existe run para el snapshot Access %.', v_snapshot;
    END IF;

    UPDATE raw.migracion_bloque_ejecucion b
       SET migracion_run_id = v_run
     WHERE b.source_snapshot_id = v_snapshot
       AND b.migracion_run_id IS NULL;
    GET DIAGNOSTICS v_bloques = ROW_COUNT;

    UPDATE raw.migracion_lineage_core l
       SET migracion_run_id = v_run
      FROM raw.migracion_bloque_ejecucion b
     WHERE l.bloque_ejecucion_id = b.bloque_ejecucion_id
       AND b.source_snapshot_id = v_snapshot
       AND l.migracion_run_id IS NULL;
    GET DIAGNOSTICS v_lineages = ROW_COUNT;

    -- Las primeras materializaciones de M_nMuestra no exponian el identificador tecnico.
    -- Si una incidencia queda asociada a una unica fila fisica, se completa su evidencia
    -- sin cambiar el hallazgo ni el contenido de negocio.
    WITH candidatos AS (
        SELECT q.rechazo_id,
               min(s.source_row_number) AS source_row_number,
               min(s.source_row_hash) AS source_row_hash,
               count(*) AS n
        FROM qua.rechazos q
        JOIN raw.m_n_muestra s
          ON s.source_snapshot_id = v_snapshot
         AND stg.fn_resolver_lote(s.fundo, s.modulo, s.lote) IS NULL
         AND q.fila->>'evaluacion' = btrim(s.evaluacion)
         AND q.fila->>'muestras' = btrim(s.muestras)
         AND (q.fila->>'cortina') IS NOT DISTINCT FROM nullif(btrim(s.cortina), '')
         AND (q.fila->>'hilera') IS NOT DISTINCT FROM nullif(btrim(s.hilera), '')
         AND (q.fila->>'planta') IS NOT DISTINCT FROM nullif(btrim(s.planta), '')
        WHERE q.migracion_run_id = v_run
          AND q.tabla_origen = 'M_nMuestra'
          AND NOT (q.fila ? 'source_row_number')
        GROUP BY q.rechazo_id
    ), unicos AS (
        SELECT rechazo_id, source_row_number, source_row_hash
        FROM candidatos
        WHERE n = 1
    )
    UPDATE qua.rechazos q
       SET fila = q.fila || jsonb_build_object(
           'source_snapshot_id', v_snapshot,
           'source_row_number', u.source_row_number,
           'source_row_hash', u.source_row_hash
       )
      FROM unicos u
     WHERE q.rechazo_id = u.rechazo_id;

    GET DIAGNOSTICS v_lineages = ROW_COUNT;

    RAISE NOTICE 'Contexto corregido: % bloques enlazados; linaje historico y evidencia M_nMuestra actualizados para el run %.',
        v_bloques, v_run;
END
$reparar_run$;

SELECT bloque_ejecucion_id, migracion_run_id, source_snapshot_id, bloque, estado
FROM raw.migracion_bloque_ejecucion
WHERE source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
ORDER BY bloque_ejecucion_id;
