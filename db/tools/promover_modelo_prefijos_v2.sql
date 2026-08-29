-- ============================================================================
-- Promoción administrativa del contrato tras el renombrado semántico de core
--
-- v1 describe el modelo que se ejecutó con los nombres históricos.
-- v2 describe el mismo modelo con nombres semánticos en core.
-- Se conserva v1 como histórico; la corrida y el linaje actualmente publicados pasan a v2.
-- No recarga ni transforma filas de negocio.
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

    IF NOT EXISTS (
        SELECT 1
        FROM raw.migracion_modelo_version
        WHERE modelo_version = 'access-c2026-2026-08-28.v2'
          AND estado = 'aprobado'
    ) THEN
        RAISE EXCEPTION 'No existe el modelo aprobado access-c2026-2026-08-28.v2.';
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

-- El v1 queda como registro histórico con su contrato original.
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT viejo, nuevo FROM _core_prefijo_map LOOP
        UPDATE raw.migracion_modelo_tabla
           SET core_objetos = array_replace(core_objetos, 'core.' || r.nuevo, 'core.' || r.viejo)
         WHERE modelo_version = 'access-c2026-2026-08-28.v1'
           AND 'core.' || r.nuevo = ANY (core_objetos);
    END LOOP;
END
$$;

-- El run, los intentos de bloque y el linaje de los datos presentes describen ahora v2.
-- migracion_tabla está protegida por trigger: se habilita solo dentro de esta transacción.
SET LOCAL raw.migracion_control = 'on';

UPDATE raw.migracion_run
   SET modelo_version = 'access-c2026-2026-08-28.v2'
 WHERE modelo_version = 'access-c2026-2026-08-28.v1'
   AND source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
   AND capa_destino = 'core';

UPDATE raw.migracion_tabla
   SET modelo_version = 'access-c2026-2026-08-28.v2'
 WHERE modelo_version = 'access-c2026-2026-08-28.v1'
   AND migracion_run_id IN (
       SELECT migracion_run_id
       FROM raw.migracion_run
       WHERE modelo_version = 'access-c2026-2026-08-28.v2'
         AND source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
         AND capa_destino = 'core'
   );

UPDATE raw.migracion_bloque_ejecucion
   SET modelo_version = 'access-c2026-2026-08-28.v2'
 WHERE modelo_version = 'access-c2026-2026-08-28.v1'
   AND migracion_run_id IN (
       SELECT migracion_run_id
       FROM raw.migracion_run
       WHERE modelo_version = 'access-c2026-2026-08-28.v2'
         AND source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
         AND capa_destino = 'core'
   );

UPDATE raw.migracion_lineage_core
   SET modelo_version = 'access-c2026-2026-08-28.v2'
 WHERE modelo_version = 'access-c2026-2026-08-28.v1'
   AND migracion_run_id IN (
       SELECT migracion_run_id
       FROM raw.migracion_run
       WHERE modelo_version = 'access-c2026-2026-08-28.v2'
         AND source_snapshot_id = raw.fn_snapshot_access_publicado(NULL, 'C2026')
         AND capa_destino = 'core'
   );

COMMIT;

\echo 'Contrato v2 promovido; v1 conservado como histórico.'
