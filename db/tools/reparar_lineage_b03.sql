-- Reparación controlada de linaje B03.
--
-- Se usa únicamente cuando una versión corregida de la regla de conversión cambia el vínculo
-- técnico, sin reconstruir core ni crear otro bloque publicado. No vuelve a cargar datos.

\set ON_ERROR_STOP on
\pset pager off

DO $guard$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION 'Reparacion bloqueada: se exige aquanqa_migracion.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM raw.migracion_bloque_ejecucion
        WHERE bloque_ejecucion_id = 5
          AND estado = 'publicado'
          AND bloque = 'B03_FENOLOGIA'
    ) THEN
        RAISE EXCEPTION 'No existe el B03 publicado esperado para reparar.';
    END IF;
END
$guard$;

SELECT set_config('aquanqa.source_snapshot_id', '1', false);
SELECT set_config('aquanqa.migracion_run_id', '1', false);
SELECT set_config('aquanqa.bloque_ejecucion_id', '5', false);

DELETE FROM raw.migracion_lineage_core
WHERE source_snapshot_id = 1
  AND bloque_ejecucion_id = 5
  AND source_table = 'e05_diametros_bayas';

DELETE FROM qua.rechazos
WHERE source_snapshot_id = 1
  AND migracion_run_id = 1
  AND bloque_ejecucion_id = 5
  AND tabla_origen = 'E05_DiametrosBayas'
  AND motivo = 'FILA_NO_REPRESENTADA';

CALL raw.sp_registrar_lineage_fenologia_b03();
CALL raw.sp_registrar_filas_no_lineage_b03();

DO $check$
DECLARE
    v_q bigint;
    v_lineage bigint;
BEGIN
    SELECT count(*) INTO v_q
    FROM qua.rechazos
    WHERE bloque_ejecucion_id = 5
      AND tabla_origen = 'E05_DiametrosBayas';

    SELECT count(*) INTO v_lineage
    FROM raw.migracion_lineage_core
    WHERE bloque_ejecucion_id = 5
      AND source_table = 'e05_diametros_bayas';

    IF v_lineage <> 4091 OR v_q <> 105 THEN
        RAISE EXCEPTION
            'Reparacion B03 no conciliada: lineage E05=% (esperado 4091), qua=% (esperado 105).',
            v_lineage, v_q;
    END IF;

    IF EXISTS (
        SELECT 1 FROM qua.rechazos
        WHERE bloque_ejecucion_id = 5
          AND (source_snapshot_id IS DISTINCT FROM 1
            OR migracion_run_id IS DISTINCT FROM 1)
    ) THEN
        RAISE EXCEPTION 'Reparacion B03 dejo rechazos sin linaje completo.';
    END IF;
END
$check$;

CALL raw.sp_registrar_tabla_migracion(
    1, 'e05_diametros_bayas', 'migrada_con_observaciones', 4193, 4091, 105,
    'Check-to-check corregido: raw=4193, stg=4193, core=4091, cuarentena=105. '
    'La unión usa diámetro redondeado a la precisión publicada en core; lineage completo.'
);

SELECT coalesce(sum(filas_raw), 0) AS filas_raw,
       coalesce(sum(filas_stg), 0) AS filas_stg,
       coalesce(sum(filas_core), 0) AS filas_core,
       coalesce(sum(filas_cuarentena), 0) AS filas_cuarentena
FROM raw.v_migracion_tablas
WHERE migracion_run_id = 1
  AND tabla_raw IN ('e01_ramas', 'e02_conteo_flores', 'e03_conteo_estados',
                    'e04_brotes', 'e05_diametros_bayas', 'e05_seguimiento')
\gset b03_reparado_

CALL raw.sp_registrar_bloque(
    5, 'publicado', :b03_reparado_filas_raw, :b03_reparado_filas_stg,
    :b03_reparado_filas_core, :b03_reparado_filas_cuarentena,
    'B03 publicado: linaje E05_DiametrosBayas reparado y conciliado; observaciones de qua '
    'actualizadas; datos core no reconstruidos.'
);

SELECT 'B03 lineage repair OK' AS resultado,
       :b03_reparado_filas_raw AS filas_raw,
       :b03_reparado_filas_stg AS filas_stg,
       :b03_reparado_filas_core AS filas_core,
       :b03_reparado_filas_cuarentena AS filas_cuarentena;
