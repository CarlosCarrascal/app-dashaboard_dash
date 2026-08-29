-- ============================================================================
-- Renombrado semántico de las tablas de core
--
-- Alcance: únicamente aquanqa_migracion.
-- No recarga datos de negocio ni modifica tablas físicas de raw/stg/qua; solo actualiza
-- las referencias administrativas de core en el ledger, el linaje y la cuarentena.
-- No toca la base aquanqa del dashboard.
-- ALTER TABLE ... RENAME conserva filas, columnas, claves, índices, secuencias y FKs.
-- Las rutinas se reaplican desde sus archivos fuente después de ejecutar este script.
-- ============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'Guardia de seguridad: este script solo puede ejecutarse en aquanqa_migracion; base actual=%',
            current_database();
    END IF;
END
$$;

CREATE TEMP TABLE _core_prefijo_map (
    viejo text PRIMARY KEY,
    nuevo text NOT NULL UNIQUE
) ON COMMIT DROP;

INSERT INTO _core_prefijo_map (viejo, nuevo) VALUES
    ('empresa',                 'm_empresa'),
    ('fundo',                   'm_fundo'),
    ('fundo_alias',             'm_fundo_alias'),
    ('modulo',                  'm_modulo'),
    ('turno',                  'm_turno'),
    ('variedad',                'm_variedad'),
    ('variedad_alias',          'm_variedad_alias'),
    ('lote',                    'm_lote'),
    ('calendario',              't_calendario'),
    ('campania',                't_campania'),
    ('semana_evaluacion',       't_semana_evaluacion'),
    ('poda',                    'evt_poda'),
    ('evaluador',               'm_evaluador'),
    ('tareo',                   'op_tareo'),
    ('rol',                     'm_rol'),
    ('usuario',                 'm_usuario'),
    ('evaluacion_ramas',        'ev_evaluacion_ramas'),
    ('rama_medicion',           'ev_rama_medicion'),
    ('flores',                  'ev_flores'),
    ('estados',                 'ev_estados'),
    ('brotes',                  'ev_brotes'),
    ('baya_medicion',           'ev_baya_medicion'),
    ('evaluacion_baya',         'ev_evaluacion_baya'),
    ('baya_observacion',        'ev_baya_observacion'),
    ('muestra_requerida',       'cfg_muestra_requerida'),
    ('cosecha',                 'op_cosecha'),
    ('clima',                   'op_clima'),
    ('calibre',                 'm_calibre'),
    ('productor_equivalencia',  'm_productor_equivalencia'),
    ('packing',                 'op_packing'),
    ('version_forecast',        'm_version_forecast'),
    ('forecast_campania',       'op_forecast_campania'),
    ('forecast_semanal',        'op_forecast_semanal'),
    ('riego_semanal',           'op_riego_semanal');

DO $$
DECLARE
    r record;
    v_viejo regclass;
    v_nuevo regclass;
BEGIN
    FOR r IN SELECT viejo, nuevo FROM _core_prefijo_map ORDER BY viejo LOOP
        v_viejo := to_regclass(format('core.%I', r.viejo));
        v_nuevo := to_regclass(format('core.%I', r.nuevo));

        IF v_viejo IS NOT NULL AND v_nuevo IS NOT NULL THEN
            RAISE EXCEPTION 'Colisión: existen core.% y core.%', r.viejo, r.nuevo;
        ELSIF v_viejo IS NOT NULL THEN
            EXECUTE format('ALTER TABLE core.%I RENAME TO %I', r.viejo, r.nuevo);
        ELSIF v_nuevo IS NULL THEN
            RAISE EXCEPTION 'Falta la tabla esperada: core.%', r.viejo;
        END IF;
    END LOOP;
END
$$;

-- El nombre de la tabla destino forma parte de la trazabilidad estructurada.
-- Se actualizan solo referencias a core; nombres físicos de Access en raw no se tocan.
-- El trigger de migración exige una operación explícita; esta es una actualización
-- administrativa controlada, dentro de la misma transacción y con alcance local.
SET LOCAL raw.migracion_control = 'on';

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT viejo, nuevo FROM _core_prefijo_map LOOP
        UPDATE raw.migracion_plan_access
           SET core_objetos = array_replace(core_objetos, 'core.' || r.viejo, 'core.' || r.nuevo)
         WHERE 'core.' || r.viejo = ANY (core_objetos);

        UPDATE raw.migracion_tabla
           SET core_objetos = array_replace(core_objetos, 'core.' || r.viejo, 'core.' || r.nuevo)
         WHERE 'core.' || r.viejo = ANY (core_objetos);

        UPDATE raw.migracion_modelo_tabla
           SET core_objetos = array_replace(core_objetos, 'core.' || r.viejo, 'core.' || r.nuevo)
         WHERE 'core.' || r.viejo = ANY (core_objetos);

        UPDATE raw.migracion_lineage_core
           SET destino_tabla = r.nuevo
         WHERE destino_schema = 'core' AND destino_tabla = r.viejo;

        UPDATE qua.rechazos
           SET tabla_destino = CASE
               WHEN tabla_destino = 'core.' || r.viejo THEN 'core.' || r.nuevo
               WHEN tabla_destino = r.viejo THEN r.nuevo
               ELSE tabla_destino
           END
         WHERE tabla_destino IN ('core.' || r.viejo, r.viejo);
    END LOOP;
END
$$;

COMMIT;

\echo 'Renombrado aplicado en aquanqa_migracion. Reaplicar DDL de core, catálogo y rutinas desde db/sql.'
