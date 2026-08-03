-- ============================================================================
-- 010 · Control de carga
--
-- Cada extracción deja constancia: cuántas filas trajo, de dónde y cuándo. Sin esto no se
-- puede distinguir "la tabla está vacía" de "la extracción se truncó" — y una extracción
-- truncada que pasa desapercibida es exactamente cómo nacieron H-03 y H-08.
-- ============================================================================

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

CREATE INDEX IF NOT EXISTS carga_log_tabla_idx
    ON raw.carga_log (tabla_destino, cargado_en DESC);

COMMENT ON TABLE raw.carga_log IS
    'Bitácora de cargas a raw. estado=desviacion cuando filas_cargadas <> filas_esperadas.';
COMMENT ON COLUMN raw.carga_log.filas_esperadas IS
    'Cifra publicada en docs/auditoria/evidencia/04_metricas_validacion.txt §1. '
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
