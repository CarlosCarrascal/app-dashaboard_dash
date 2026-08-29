-- Metadata relacional de Access obtenida por DAO.
-- No crea FK en raw ni promueve relaciones: conserva evidencia para el modelado posterior.

CREATE TABLE IF NOT EXISTS raw.access_relation_catalog (
    relation_catalog_id bigserial PRIMARY KEY,
    source_snapshot_id  bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    nombre              text NOT NULL,
    tabla_padre         text NOT NULL,
    tabla_hija          text NOT NULL,
    atributos           jsonb NOT NULL DEFAULT '{}'::jsonb,
    campos              jsonb NOT NULL DEFAULT '[]'::jsonb,
    estado              text NOT NULL DEFAULT 'catalogada'
        CHECK (estado IN ('catalogada', 'incompleta', 'no_disponible')),
    detalle             text,
    registrado_en       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_snapshot_id, nombre)
);

COMMENT ON TABLE raw.access_relation_catalog IS
    'Relaciones declaradas en Access, capturadas por DAO. Son metadata/evidencia y no equivalen '
    'a FK aprobada en core.';

CREATE INDEX IF NOT EXISTS access_relation_catalog_tables_idx
    ON raw.access_relation_catalog (source_snapshot_id, tabla_padre, tabla_hija);
