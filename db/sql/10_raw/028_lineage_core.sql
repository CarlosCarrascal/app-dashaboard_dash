-- ============================================================================
-- 028 · Linaje de objetos publicados en core
--
-- Los objetos de core pueden ser derivados, agregados o desancho de una fuente. Por eso el
-- linaje se conserva en una tabla técnica 1:N en vez de forzar columnas de origen en cada
-- entidad de negocio. Una fila de core puede tener varias filas de origen (por ejemplo, una
-- cosecha unificada desde H00 y H01).
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw.migracion_lineage_core (
    lineage_id           bigserial PRIMARY KEY,
    modelo_version       text,
    migracion_run_id     bigint REFERENCES raw.migracion_run(migracion_run_id),
    bloque_ejecucion_id  bigint REFERENCES raw.migracion_bloque_ejecucion(bloque_ejecucion_id),
    source_snapshot_id   bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    source_table         text NOT NULL,
    source_row_number    bigint,
    source_row_hash      text,
    destino_schema       text NOT NULL CHECK (destino_schema = 'core'),
    destino_tabla        text NOT NULL,
    destino_pk           jsonb NOT NULL,
    tipo                 text NOT NULL DEFAULT 'directa'
                         CHECK (tipo IN ('directa', 'deduplicada', 'agregada', 'desancho', 'derivada')),
    detalle              jsonb NOT NULL DEFAULT '{}'::jsonb,
    registrado_en        timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS migracion_lineage_core_uk
    ON raw.migracion_lineage_core (
        source_snapshot_id, source_table, coalesce(source_row_number, -1),
        destino_tabla, destino_pk, tipo
    );

CREATE INDEX IF NOT EXISTS migracion_lineage_core_destino_idx
    ON raw.migracion_lineage_core (destino_tabla, destino_pk);

CREATE INDEX IF NOT EXISTS migracion_lineage_core_origen_idx
    ON raw.migracion_lineage_core (source_snapshot_id, source_table, source_row_number);

CREATE OR REPLACE VIEW raw.v_migracion_lineage_core AS
SELECT l.*
FROM raw.migracion_lineage_core l;

COMMENT ON TABLE raw.migracion_lineage_core IS
    'Linaje técnico de cada objeto publicado en core hasta snapshot, tabla, fila y hash de origen. '
    'No sustituye las claves de negocio ni crea relaciones funcionales.';

COMMENT ON VIEW raw.v_migracion_lineage_core IS
    'Consulta de trazabilidad core → raw. Una entidad agregada puede tener varios orígenes.';
