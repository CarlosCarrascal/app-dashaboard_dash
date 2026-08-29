-- ============================================================================
-- 090 · raw · Objetos Access presentes en copias nuevas
--
-- Estas tablas no estaban en el catálogo histórico, pero existen en
-- BD_AQUANQA_26.accdb. Se mantienen con tipos text: raw conserva el origen y
-- el tipado/normalización ocurre después en stg.
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw.e05_seguimiento (
    id_origen text,
    fecha text,
    evaluador text,
    fundo text,
    modulo text,
    lote text,
    hora text,
    cortina text,
    hilera text,
    planta text,
    d01 text,
    e01 text,
    d02 text,
    e02 text,
    d03 text,
    e03 text,
    d04 text,
    e04 text,
    d05 text,
    e05 text,
    d06 text,
    e06 text,
    d07 text,
    e07 text,
    d08 text,
    e08 text,
    d09 text,
    e09 text,
    d10 text,
    e10 text,
    d11 text,
    e11 text,
    d12 text,
    e12 text,
    d13 text,
    e13 text,
    d14 text,
    e14 text,
    d15 text,
    e15 text,
    d16 text,
    e16 text,
    d17 text,
    e17 text,
    d18 text,
    e18 text,
    d19 text,
    e19 text,
    d20 text,
    e20 text,
    d21 text,
    e21 text,
    d22 text,
    e22 text,
    d23 text,
    e23 text,
    d24 text,
    e24 text,
    d25 text,
    e25 text
);

COMMENT ON TABLE raw.e05_seguimiento IS
    'E05_Seguimiento — seguimiento por planta con 25 pares diámetro/estado. Se conserva ancho en raw y se normaliza en stg.';

CREATE TABLE IF NOT EXISTS raw.h01_detalle_cosecha (
    fecha_cosecha text,
    fundo_campo text,
    fundo_planta text,
    grupo text,
    modulo_planta text,
    turno_planta text,
    modulo text,
    turno text,
    lote text,
    variedad text,
    area text,
    kg_cosechados text,
    kg_entierro text,
    kg_ingreso_planta text,
    kg_descarte text,
    kg_descarte_congelado text,
    kg_exportable text,
    jarras text
);

COMMENT ON TABLE raw.h01_detalle_cosecha IS
    'H01_Detalle_Cosecha — detalle operativo de cosecha que no estaba en el catálogo histórico.';

CREATE TABLE IF NOT EXISTS raw.m_presupuesto_mo (
    anio text,
    semana text,
    fundo text,
    evaluacion text,
    mo_sem text
);

COMMENT ON TABLE raw.m_presupuesto_mo IS
    'M_PresupuestoMO — presupuesto semanal de mano de obra.';

CREATE TABLE IF NOT EXISTS raw.r08_forecast_campania_24 (
    version text,
    fundo_ppto text,
    modulo text,
    anio text,
    semana text,
    kg text
);

COMMENT ON TABLE raw.r08_forecast_campania_24 IS
    'R08_Forecast_Campaña_24 — variante histórica de forecast.';

CREATE TABLE IF NOT EXISTS raw.r08_forecast_campania_25 (
    version text,
    fundo text,
    modulo text,
    pln_fundo text,
    plnt_mod text,
    turno text,
    plantas text,
    camp text,
    anio text,
    sem text,
    "desc" text,
    kg text,
    frt_total text
);

COMMENT ON TABLE raw.r08_forecast_campania_25 IS
    'R08_Forecast_Campaña_25 — variante histórica de forecast.';

CREATE TABLE IF NOT EXISTS raw.r09_forecast_semanal_25 (
    campania text,
    fundo text,
    modulo text,
    turno text,
    lote text,
    area text,
    fecha_cos_ant text,
    fecha_cos text,
    sem text,
    frt_cos text,
    rend text,
    kg text,
    dr text,
    version text,
    fund_ppto text
);

COMMENT ON TABLE raw.r09_forecast_semanal_25 IS
    'R09_Forecast_Semanal_25 — variante histórica de forecast.';

CREATE TABLE IF NOT EXISTS raw.access_query_catalog (
    query_catalog_id bigserial PRIMARY KEY,
    source_snapshot_id bigint REFERENCES raw.source_snapshot(source_snapshot_id),
    nombre text NOT NULL,
    tipo_objeto text NOT NULL,
    definicion_sql text,
    dependencias jsonb NOT NULL DEFAULT '[]'::jsonb,
    proposito text,
    estado text NOT NULL CHECK (estado IN ('catalogada', 'ejecutable', 'rota', 'no_disponible')),
    detalle text,
    catalogada_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_snapshot_id, nombre)
);

COMMENT ON TABLE raw.access_query_catalog IS
    'Inventario de consultas guardadas de Access. Conserva lógica y estado sin materializar sus resultados como tablas raw.';

ALTER TABLE raw.access_query_catalog
    ADD COLUMN IF NOT EXISTS proposito text;
