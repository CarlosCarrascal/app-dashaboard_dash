-- ============================================================================
-- 20_core · 045 · Soporte de captura interna desde la API
--
-- Este archivo es aditivo. No modifica ni reconstruye las evaluaciones históricas.
-- La tabla técnica permite que Flutter reintente una captura offline sin duplicar E02,
-- E01 u otras tablas que no tienen una clave idempotente común.
-- ============================================================================

ALTER TABLE core.ev_flores
    ADD COLUMN IF NOT EXISTS yemas_muertas smallint CHECK (yemas_muertas >= 0);

COMMENT ON COLUMN core.ev_flores.yemas_muertas IS
    'Yemas muertas capturadas por la aplicación móvil. Se incorpora de forma aditiva para que '
    'el formulario actual no pierda ese valor al pasar de Flutter a core.';

CREATE TABLE IF NOT EXISTS core.api_evaluacion_ingesta (
    client_id       text PRIMARY KEY,
    module_key      text NOT NULL CHECK (module_key IN
                    ('estadios', 'flores', 'baya', 'pesos', 'brotes', 'ramas')),
    payload_hash    text NOT NULL,
    resource_table  text,
    resource_id     bigint,
    status          text NOT NULL DEFAULT 'processing'
                    CHECK (status IN ('processing', 'accepted')),
    creado_en       timestamptz NOT NULL DEFAULT now(),
    actualizado_en  timestamptz NOT NULL DEFAULT now()
);

-- Copia canónica del contrato móvil. Las tablas ev_* siguen siendo el modelo
-- analítico; este JSON permite reconstruir la captura exactamente como la ve
-- Flutter (incluidas las claves m1_*, m2_*, etc.) para sincronizar historial.
ALTER TABLE core.api_evaluacion_ingesta
    ADD COLUMN IF NOT EXISTS payload jsonb,
    ADD COLUMN IF NOT EXISTS evaluador_id bigint,
    ADD COLUMN IF NOT EXISTS evaluador_dni text,
    ADD COLUMN IF NOT EXISTS fecha date,
    ADD COLUMN IF NOT EXISTS captured_at timestamptz;

COMMENT ON TABLE core.api_evaluacion_ingesta IS
    'Idempotencia técnica de capturas recibidas por la API. No es una evaluación ni una tabla '
    'de interfaz: relaciona el UUID local de Flutter con el recurso core creado y su huella. '
    'Evita duplicados en reintentos offline, especialmente en tablas sin clave natural.';

CREATE INDEX IF NOT EXISTS api_evaluacion_ingesta_recurso_idx
    ON core.api_evaluacion_ingesta (resource_table, resource_id);

CREATE INDEX IF NOT EXISTS api_evaluacion_ingesta_historial_evaluador_idx
    ON core.api_evaluacion_ingesta
       (evaluador_id, COALESCE(captured_at, creado_en) DESC)
    WHERE status = 'accepted' AND payload IS NOT NULL;

CREATE INDEX IF NOT EXISTS api_evaluacion_ingesta_historial_dni_idx
    ON core.api_evaluacion_ingesta
       (evaluador_dni, COALESCE(captured_at, creado_en) DESC)
    WHERE status = 'accepted' AND payload IS NOT NULL;

-- Permisos mínimos para una instalación incremental. En la base actual el rol existía, pero
-- no tenía estos grants efectivos porque varias tablas core fueron creadas después del
-- bootstrap. La API necesita leer el catálogo y resolver lotes; para hechos solo requiere
-- escribir/upsertar las tablas que atienden a los seis módulos.
GRANT USAGE ON SCHEMA core TO aquanqa_app;

GRANT SELECT ON
    core.m_empresa,
    core.m_fundo,
    core.m_modulo,
    core.m_lote,
    core.m_turno,
    core.m_variedad,
    core.m_evaluador
TO aquanqa_app;

GRANT SELECT, INSERT, UPDATE ON
    core.ev_estados,
    core.ev_flores,
    core.ev_brotes,
    core.ev_evaluacion_baya,
    core.ev_baya_observacion,
    core.ev_evaluacion_ramas
TO aquanqa_app;

GRANT SELECT, INSERT, DELETE ON core.ev_rama_medicion TO aquanqa_app;
GRANT SELECT, INSERT, UPDATE ON core.api_evaluacion_ingesta TO aquanqa_app;

GRANT USAGE, SELECT ON
    SEQUENCE core.estados_estados_id_seq,
             core.flores_flores_id_seq,
             core.brotes_brotes_id_seq,
             core.evaluacion_baya_evaluacion_baya_id_seq,
             core.baya_observacion_baya_observacion_id_seq,
             core.evaluacion_ramas_evaluacion_ramas_id_seq,
             core.rama_medicion_rama_medicion_id_seq
TO aquanqa_app;
