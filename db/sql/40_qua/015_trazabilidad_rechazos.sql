-- ============================================================================
-- 40_qua · 015 · Linaje de cuarentena
--
-- Una fila rechazada debe poder ubicarse en el snapshot y en el bloque que la produjo.
-- Las columnas son opcionales para conservar compatibilidad con cargas históricas; un trigger
-- las completa cuando el ejecutor gobernado fija los GUC de la ejecución actual.
-- ============================================================================

ALTER TABLE qua.rechazos
    ADD COLUMN IF NOT EXISTS source_snapshot_id bigint
        REFERENCES raw.source_snapshot(source_snapshot_id),
    ADD COLUMN IF NOT EXISTS migracion_run_id bigint
        REFERENCES raw.migracion_run(migracion_run_id),
    ADD COLUMN IF NOT EXISTS bloque_ejecucion_id bigint
        REFERENCES raw.migracion_bloque_ejecucion(bloque_ejecucion_id);

CREATE INDEX IF NOT EXISTS rechazos_snapshot_idx
    ON qua.rechazos (source_snapshot_id, tabla_origen, motivo);

CREATE INDEX IF NOT EXISTS rechazos_bloque_idx
    ON qua.rechazos (bloque_ejecucion_id, tabla_origen, motivo);

CREATE OR REPLACE FUNCTION qua.fn_trazar_rechazo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloque bigint;
BEGIN
    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        v_snapshot := NULL;
    END;
    BEGIN
        v_run := nullif(current_setting('aquanqa.migracion_run_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        v_run := NULL;
    END;
    BEGIN
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        v_bloque := NULL;
    END;

    NEW.source_snapshot_id := coalesce(NEW.source_snapshot_id, v_snapshot);
    NEW.migracion_run_id := coalesce(NEW.migracion_run_id, v_run);
    NEW.bloque_ejecucion_id := coalesce(NEW.bloque_ejecucion_id, v_bloque);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_trazar_rechazo ON qua.rechazos;
CREATE TRIGGER trg_trazar_rechazo
BEFORE INSERT ON qua.rechazos
FOR EACH ROW
EXECUTE FUNCTION qua.fn_trazar_rechazo();

COMMENT ON COLUMN qua.rechazos.source_snapshot_id IS
    'Snapshot que produjo el rechazo; NULL solo para datos históricos cargados antes del ledger.';
COMMENT ON COLUMN qua.rechazos.migracion_run_id IS
    'Ejecución de migración que produjo el rechazo.';
COMMENT ON COLUMN qua.rechazos.bloque_ejecucion_id IS
    'Intento de bloque que produjo el rechazo.';
