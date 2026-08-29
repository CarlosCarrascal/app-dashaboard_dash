-- ============================================================================
-- 035 · Perfilado antes de staging/core
--
-- El perfilado no corrige datos. Solo registra evidencia de nulidad, duplicidad, claves
-- candidatas y relaciones para que una FK o una transformación se apruebe con datos reales.
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw.migracion_perfil_tabla (
    perfil_id          bigserial PRIMARY KEY,
    modelo_version     text NOT NULL,
    source_snapshot_id bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    tabla_raw          text NOT NULL REFERENCES raw.migracion_plan_access(tabla_raw),
    filas_raw          bigint NOT NULL,
    filas_distintas    bigint NOT NULL,
    filas_duplicadas   bigint NOT NULL,
    columnas           jsonb NOT NULL DEFAULT '{}'::jsonb,
    claves             jsonb NOT NULL DEFAULT '[]'::jsonb,
    estado             text NOT NULL CHECK (estado IN ('perfilada', 'con_alertas', 'fallida')),
    detalle             text,
    calculada_en       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS migracion_perfil_tabla_ultima_idx
    ON raw.migracion_perfil_tabla
       (modelo_version, source_snapshot_id, tabla_raw, calculada_en DESC, perfil_id DESC);

COMMENT ON TABLE raw.migracion_perfil_tabla IS
    'Perfil técnico de una fuente raw para un snapshot. Conserva la evidencia que precede a '
    'la decisión de crear claves y relaciones en core.';

CREATE OR REPLACE VIEW raw.v_migracion_perfil_tabla_ultimo AS
SELECT DISTINCT ON (modelo_version, source_snapshot_id, tabla_raw)
       perfil_id, modelo_version, source_snapshot_id, tabla_raw, filas_raw,
       filas_distintas, filas_duplicadas, columnas, claves, estado, detalle, calculada_en
FROM raw.migracion_perfil_tabla
ORDER BY modelo_version, source_snapshot_id, tabla_raw, calculada_en DESC, perfil_id DESC;

CREATE OR REPLACE VIEW raw.v_migracion_relaciones_sin_aprobar AS
SELECT *
FROM raw.v_migracion_modelo_relaciones
WHERE estado <> 'aprobada';
