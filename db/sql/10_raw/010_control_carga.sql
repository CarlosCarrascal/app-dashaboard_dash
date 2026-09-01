-- ============================================================================
-- 010 · Control de carga
--
-- Cada extracción deja constancia: cuántas filas trajo, de dónde y cuándo. Sin esto no se
-- puede distinguir "la tabla está vacía" de "la extracción se truncó" — y una extracción
-- truncada que pasa desapercibida es exactamente cómo nacieron H-03 y H-08.
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw.source_snapshot (
    source_snapshot_id bigserial PRIMARY KEY,
    tipo               text        NOT NULL,
    campania           text,
    ruta_origen        text        NOT NULL,
    nombre_archivo     text        NOT NULL,
    sha256             char(64)    NOT NULL,
    bytes              bigint,
    modificado_en      timestamptz,
    extraido_en        timestamptz NOT NULL,
    solo_lectura       boolean     NOT NULL DEFAULT true,
    version_minima_r09 text,
    version_maxima_r09 text,
    filas_r09          bigint,
    conteos_tabla      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    manifiesto         jsonb       NOT NULL,
    creado_en          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tipo, sha256, extraido_en)
);

COMMENT ON TABLE raw.source_snapshot IS
    'Huella inmutable de cada archivo operativo extraído antes de cargar raw.';

ALTER TABLE raw.source_snapshot
    ADD COLUMN IF NOT EXISTS campania text;

CREATE TABLE IF NOT EXISTS raw.carga_log (
    carga_id       bigserial PRIMARY KEY,
    tabla_destino  text        NOT NULL,
    objeto_origen  text        NOT NULL,
    origen         text        NOT NULL,   -- 'access' | 'xlsx'
    ruta_origen    text        NOT NULL,
    filas_origen   bigint,                 -- lo que dijo el origen
    filas_cargadas bigint      NOT NULL,   -- lo que llegó a raw
    filas_esperadas bigint,                -- de la auditoría, si hay cifra publicada
    extraido_en    timestamptz,
    cargado_en     timestamptz NOT NULL DEFAULT now(),
    estado         text        NOT NULL
                   CHECK (estado IN ('ok', 'desviacion', 'error')),
    detalle        text
);

CREATE TABLE IF NOT EXISTS raw.source_table_delta (
    source_snapshot_id bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    snapshot_anterior_id bigint REFERENCES raw.source_snapshot(source_snapshot_id),
    tabla_destino      text NOT NULL,
    filas_anteriores   bigint NOT NULL,
    filas_actuales     bigint NOT NULL,
    filas_nuevas       bigint NOT NULL,
    filas_eliminadas   bigint NOT NULL,
    filas_modificadas  bigint NOT NULL DEFAULT 0,
    metodo             text NOT NULL,
    calculado_en       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_snapshot_id, tabla_destino)
);

-- La huella histórica se calcula contra el snapshot publicado en el momento de la carga.
-- Guardar ese identificador evita presentar como vigente un delta calculado contra una base
-- anterior, algo que ocurre durante una rebase de contrato (por ejemplo, v4 → v5).
ALTER TABLE raw.source_table_delta
    ADD COLUMN IF NOT EXISTS snapshot_anterior_id bigint;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'source_table_delta_snapshot_anterior_fk'
          AND conrelid = 'raw.source_table_delta'::regclass
    ) THEN
        ALTER TABLE raw.source_table_delta
            ADD CONSTRAINT source_table_delta_snapshot_anterior_fk
            FOREIGN KEY (snapshot_anterior_id)
            REFERENCES raw.source_snapshot(source_snapshot_id);
    END IF;
END $$;

COMMENT ON TABLE raw.source_table_delta IS
    'Diferencia multiconjunto por huella de fila. Sin clave estable, una edición se expresa '
    'como una fila eliminada y otra nueva; filas_modificadas permanece 0 para no inventar pares. '
    'snapshot_anterior_id identifica contra qué publicación se calculó.';

ALTER TABLE raw.carga_log
    ADD COLUMN IF NOT EXISTS source_snapshot_id bigint;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'carga_log_source_snapshot_fk'
          AND conrelid = 'raw.carga_log'::regclass
    ) THEN
        ALTER TABLE raw.carga_log
            ADD CONSTRAINT carga_log_source_snapshot_fk
            FOREIGN KEY (source_snapshot_id)
            REFERENCES raw.source_snapshot (source_snapshot_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS carga_log_tabla_idx
    ON raw.carga_log (tabla_destino, cargado_en DESC);

COMMENT ON TABLE raw.carga_log IS
    'Bitácora de cargas a raw. estado=desviacion cuando filas_cargadas <> filas_esperadas.';
COMMENT ON COLUMN raw.carga_log.filas_esperadas IS
    'Cifra publicada en docs/historico-access/evidencia/04_metricas_validacion.txt §1. '
    'NULL para orígenes que no estaban en la auditoría (maestro vigente, tareo).';

-- Última carga de cada tabla, con su veredicto. Es lo primero que hay que mirar
-- cuando una cifra no cuadra.
CREATE OR REPLACE VIEW raw.v_ultima_carga AS
SELECT DISTINCT ON (tabla_destino)
       tabla_destino,
       objeto_origen,
       origen,
       filas_cargadas,
       filas_esperadas,
       filas_cargadas - filas_esperadas AS desvio,
       estado,
       cargado_en,
       detalle
FROM raw.carga_log
ORDER BY tabla_destino, cargado_en DESC;

COMMENT ON VIEW raw.v_ultima_carga IS
    'Estado de la última carga por tabla. desvio <> 0 significa que raw no reproduce la '
    'auditoría: repetir la extracción antes de seguir.';

CREATE OR REPLACE VIEW raw.v_ultimo_snapshot_fuente AS
SELECT DISTINCT ON (tipo, campania)
       source_snapshot_id,
       tipo,
       campania,
       nombre_archivo,
       ruta_origen,
       sha256,
       bytes,
       modificado_en,
       extraido_en,
       version_minima_r09,
       version_maxima_r09,
       filas_r09,
       conteos_tabla,
       creado_en
FROM raw.source_snapshot
ORDER BY tipo, campania, extraido_en DESC, source_snapshot_id DESC;

COMMENT ON VIEW raw.v_ultimo_snapshot_fuente IS
    'Última copia física extraída por tipo y campaña, incluida su versión máxima R09.';

-- ── Gobierno de snapshots ───────────────────────────────────────────────────
-- El histórico de Access se conserva por archivo físico. La fecha de extracción no es la
-- identidad: volver a extraer el mismo archivo debe reutilizar su snapshot por hash.
ALTER TABLE raw.source_snapshot
    ADD COLUMN IF NOT EXISTS version_fuente text,
    ADD COLUMN IF NOT EXISTS schema_hash text,
    ADD COLUMN IF NOT EXISTS estado text NOT NULL DEFAULT 'detectado',
    ADD COLUMN IF NOT EXISTS reemplaza_snapshot_id bigint REFERENCES raw.source_snapshot(source_snapshot_id),
    ADD COLUMN IF NOT EXISTS actualizado_en timestamptz NOT NULL DEFAULT now();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'source_snapshot_estado_ck'
          AND conrelid = 'raw.source_snapshot'::regclass
    ) THEN
        ALTER TABLE raw.source_snapshot
            ADD CONSTRAINT source_snapshot_estado_ck
            CHECK (estado IN ('detectado', 'extraido', 'cargando', 'cargado',
                              'en_validacion', 'aprobado', 'en_revision', 'publicado',
                              'rechazado', 'revertido'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS source_snapshot_tipo_hash_idx
    ON raw.source_snapshot (tipo, sha256);

CREATE TABLE IF NOT EXISTS raw.source_table_snapshot (
    source_snapshot_id bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    tabla_destino      text NOT NULL,
    objeto_origen      text NOT NULL,
    filas_origen       bigint,
    filas_csv          bigint,
    sha256_csv         text,
    schema_hash        text,
    estado             text NOT NULL CHECK (estado IN ('extraido', 'cargado', 'error')),
    detalle            text,
    registrado_en      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_snapshot_id, tabla_destino)
);

COMMENT ON TABLE raw.source_table_snapshot IS
    'Control por tabla de cada snapshot: conteo, hash de CSV, estructura y estado de carga.';

CREATE TABLE IF NOT EXISTS raw.access_schema_catalog (
    source_snapshot_id bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    tabla_destino      text NOT NULL,
    objeto_origen      text NOT NULL,
    schema_hash        text,
    columnas           jsonb NOT NULL DEFAULT '[]'::jsonb,
    indices            jsonb NOT NULL DEFAULT '[]'::jsonb,
    claves_primarias   jsonb NOT NULL DEFAULT '[]'::jsonb,
    registrado_en      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_snapshot_id, tabla_destino)
);

COMMENT ON TABLE raw.access_schema_catalog IS
    'Catálogo técnico del Access por snapshot: tipos, tamaños, nulabilidad, índices y claves. '
    'No confundirlo con la estructura canónica de raw.';

CREATE TABLE IF NOT EXISTS raw.snapshot_publication (
    publication_id       bigserial PRIMARY KEY,
    tipo                 text NOT NULL,
    campania             text NOT NULL,
    source_snapshot_id   bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    snapshot_anterior_id bigint REFERENCES raw.source_snapshot(source_snapshot_id),
    accion               text NOT NULL CHECK (accion IN ('publicar', 'rollback')),
    motivo               text,
    autorizado_por       text NOT NULL,
    publicado_en         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE raw.snapshot_publication IS
    'Histórico de promociones y rollback. La vista vigente toma la última acción por tipo y campaña.';

CREATE INDEX IF NOT EXISTS snapshot_publication_vigente_idx
    ON raw.snapshot_publication (tipo, campania, publicado_en DESC, publication_id DESC);

CREATE OR REPLACE VIEW raw.v_snapshot_publicado AS
SELECT DISTINCT ON (tipo, campania)
       tipo,
       campania,
       CASE WHEN accion = 'rollback' THEN snapshot_anterior_id ELSE source_snapshot_id END
           AS source_snapshot_id,
       accion,
       autorizado_por,
       publicado_en
FROM raw.snapshot_publication
ORDER BY tipo, campania, publicado_en DESC, publication_id DESC;

COMMENT ON VIEW raw.v_snapshot_publicado IS
    'Snapshot vigente por tipo y campaña. Un rollback se registra como una nueva acción, nunca borra historia.';
