-- ============================================================================
-- 020 · Control de migración por capa
--
-- `raw.source_table_snapshot` prueba que las 23 tablas de Access llegaron completas
-- a raw. Este segundo control registra el avance de raw → stg → core sin confundir
-- extracción con migración. Una ejecución conserva su historia y una nueva versión
-- de Access genera otra ejecución vinculada a su snapshot.
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw.migracion_plan_access (
    tabla_raw       text PRIMARY KEY,
    orden           smallint NOT NULL,
    stg_objetos     text[] NOT NULL DEFAULT '{}',
    core_objetos    text[] NOT NULL DEFAULT '{}',
    criterio        text NOT NULL,
    activo          boolean NOT NULL DEFAULT true
);

COMMENT ON TABLE raw.migracion_plan_access IS
    'Plan técnico de las 23 tablas base de Access: objetos de staging, destinos core y criterio '
    'de aceptación. No contiene datos de negocio ni reemplaza al catálogo Python del ETL.';

INSERT INTO raw.migracion_plan_access
    (tabla_raw, orden, stg_objetos, core_objetos, criterio)
VALUES
    ('e01_ramas',              1, ARRAY['stg.e01_ramas'],              ARRAY['core.ev_evaluacion_ramas', 'core.ev_rama_medicion'], 'Carga normalizada; cabecera y detalle de rama.'),
    ('e02_conteo_flores',      2, ARRAY['stg.e02_flores'],              ARRAY['core.ev_flores'], 'Carga normalizada; duplicados y negativos quedan explicados.'),
    ('e03_conteo_estados',    3, ARRAY['stg.e03_estados'],              ARRAY['core.ev_estados'], 'Carga normalizada; item forma parte de la clave natural.'),
    ('e04_brotes',             4, ARRAY['stg.e04_brotes'],              ARRAY['core.ev_brotes'], 'Carga normalizada; la fecha forma parte de la identidad.'),
    ('e05_diametros_bayas',   5, ARRAY['stg.e05_bayas'],                ARRAY['core.ev_baya_medicion'], 'Carga normalizada; se numera la muestra porque Access no trae identificador de baya.'),
    ('e05_seguimiento',       6, ARRAY['stg.e05_seguimiento'],          ARRAY['core.ev_evaluacion_baya', 'core.ev_baya_observacion'], 'Desancho de 25 pares diámetro/estado en staging.'),
    ('h00_volumen_campo',     7, ARRAY['stg.h00_cosecha'],              ARRAY['core.op_cosecha'], 'Se unifica con H01; la reconciliación queda en qua.'),
    ('h01_detalle_cosecha',   8, ARRAY[]::text[],                       ARRAY[]::text[], 'Raw únicamente por ahora; requiere definición de grano y destino.'),
    ('h01_prod_historica',    9, ARRAY['stg.h01_cosecha'],              ARRAY['core.op_cosecha'], 'Se unifica con H00; las diferencias quedan en qua.'),
    ('h02_bd_elifab',        10, ARRAY['stg.h02_packing'],              ARRAY['core.op_packing'], 'Packing referencia módulo, no lote de campo.'),
    ('h05_clima',            11, ARRAY['stg.h05_clima'],               ARRAY['core.op_clima'], 'Deduplicación por timestamp con rastro en qua.'),
    ('m_equivalencia_elifab',12, ARRAY[]::text[],                       ARRAY['core.m_productor_equivalencia'], 'Maestro auxiliar consumido por la carga de packing.'),
    ('m_evaluadores',        13, ARRAY['stg.m_evaluadores'],             ARRAY['core.m_evaluador'], 'Resolución por DNI; evaluadores fuera del maestro quedan marcados.'),
    ('m_lotes',              14, ARRAY['stg.maestro_lote'],              ARRAY['core.m_empresa', 'core.m_fundo', 'core.m_modulo', 'core.m_turno', 'core.m_variedad', 'core.m_lote', 'core.m_fundo_alias', 'core.m_variedad_alias'], 'Maestro primario de identidad; Access es la fuente de verdad.'),
    ('m_n_muestra',          15, ARRAY['stg.m_n_muestra'],               ARRAY['core.cfg_muestra_requerida'], 'Muestreo requerido por ubicación.'),
    ('m_poda',               16, ARRAY['stg.m_poda'],                    ARRAY['core.evt_poda'], 'Evento de poda normalizado.'),
    ('m_presupuesto_mo',     17, ARRAY[]::text[],                       ARRAY[]::text[], 'Raw únicamente por ahora; pendiente de definición operativa.'),
    ('m_time',               18, ARRAY['stg.m_time'],                    ARRAY['core.t_campania', 'core.t_calendario', 'core.t_semana_evaluacion'], 'Tiempo se deriva de las fuentes; M_Time se conserva para conciliación.'),
    ('r08_forecast_campania',19, ARRAY['stg.r08_forecast'],              ARRAY['core.op_forecast_campania'], 'Forecast de campaña normalizado y versionado.'),
    ('r08_forecast_campania_24', 20, ARRAY[]::text[],                    ARRAY[]::text[], 'Raw histórico auxiliar; pendiente de decisión de integración.'),
    ('r08_forecast_campania_25', 21, ARRAY[]::text[],                    ARRAY[]::text[], 'Raw histórico auxiliar; pendiente de decisión de integración.'),
    ('r09_forecast_semanal', 22, ARRAY['stg.r09_forecast'],              ARRAY['core.op_forecast_semanal'], 'Forecast semanal normalizado y versionado.'),
    ('r09_forecast_semanal_25', 23, ARRAY[]::text[],                     ARRAY[]::text[], 'Raw histórico auxiliar; pendiente de decisión de integración.')
ON CONFLICT (tabla_raw) DO UPDATE
SET orden = excluded.orden,
    stg_objetos = excluded.stg_objetos,
    core_objetos = excluded.core_objetos,
    criterio = excluded.criterio,
    activo = excluded.activo;

CREATE TABLE IF NOT EXISTS raw.migracion_run (
    migracion_run_id   bigserial PRIMARY KEY,
    source_snapshot_id bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    tipo               text NOT NULL CHECK (tipo = 'access'),
    campania           text NOT NULL,
    capa_origen        text NOT NULL DEFAULT 'raw' CHECK (capa_origen = 'raw'),
    capa_destino       text NOT NULL CHECK (capa_destino IN ('stg', 'core')),
    total_tablas_plan  integer NOT NULL CHECK (total_tablas_plan > 0),
    estado             text NOT NULL DEFAULT 'iniciado'
                       CHECK (estado IN ('iniciado', 'en_proceso', 'completada',
                                         'completada_con_observaciones', 'con_errores',
                                         'cancelada')),
    ejecutado_por      text NOT NULL DEFAULT current_user,
    detalle            text,
    iniciado_en        timestamptz NOT NULL DEFAULT now(),
    finalizado_en      timestamptz
);

COMMENT ON TABLE raw.migracion_run IS
    'Una ejecución de migración por snapshot Access y capa destino. El estado agregado se '
    'actualiza a partir del control de cada tabla; nunca se borra una ejecución anterior.';

CREATE INDEX IF NOT EXISTS migracion_run_snapshot_idx
    ON raw.migracion_run (source_snapshot_id, iniciado_en DESC);

CREATE TABLE IF NOT EXISTS raw.migracion_tabla (
    migracion_run_id   bigint NOT NULL REFERENCES raw.migracion_run(migracion_run_id) ON DELETE CASCADE,
    source_snapshot_id bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    tabla_raw          text NOT NULL REFERENCES raw.migracion_plan_access(tabla_raw),
    objeto_origen      text,
    stg_objetos        text[] NOT NULL DEFAULT '{}',
    core_objetos       text[] NOT NULL DEFAULT '{}',
    criterio           text NOT NULL,
    estado             text NOT NULL DEFAULT 'pendiente'
                       CHECK (estado IN ('pendiente', 'en_proceso', 'migrada',
                                         'migrada_con_observaciones', 'raw_only',
                                         'fallida', 'omitida')),
    filas_raw          bigint,
    filas_stg          bigint,
    filas_core         bigint,
    filas_cuarentena   bigint NOT NULL DEFAULT 0 CHECK (filas_cuarentena >= 0),
    detalle            text,
    iniciada_en        timestamptz,
    finalizada_en      timestamptz,
    PRIMARY KEY (migracion_run_id, tabla_raw)
);

-- Evolución compatible del catálogo: raw_only es un cierre explícito para una fuente
-- conservada en raw cuando todavía no existe un modelo core aprobado.
ALTER TABLE raw.migracion_tabla
    DROP CONSTRAINT IF EXISTS migracion_tabla_estado_check;
ALTER TABLE raw.migracion_tabla
    ADD CONSTRAINT migracion_tabla_estado_check
    CHECK (estado IN ('pendiente', 'en_proceso', 'migrada',
                      'migrada_con_observaciones', 'raw_only', 'fallida', 'omitida'));

COMMENT ON TABLE raw.migracion_tabla IS
    'Control check-to-check por tabla Access: raw, staging, core y cuarentena. Una tabla '
    'puede alimentar varios destinos core; por eso los objetos destino se conservan como lista '
    'y filas_core es una cifra de control declarada por la etapa, no una suma ciega.';

CREATE INDEX IF NOT EXISTS migracion_tabla_estado_idx
    ON raw.migracion_tabla (estado, migracion_run_id);

-- Regla dura: nadie puede marcar una tabla como migrada sin dejar las tres
-- mediciones del check-to-check. La igualdad entre capas depende del grano de
-- cada tabla y se valida en el script de cada bloque; aquí se evita el atajo
-- de cambiar el estado sin evidencia mínima.
CREATE OR REPLACE FUNCTION raw.fn_guardar_estado_migracion_tabla()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF coalesce(current_setting('raw.migracion_control', true), '') <> 'on' THEN
        RAISE EXCEPTION
            'Control de migración protegido: use raw.sp_registrar_tabla_migracion o raw.fn_iniciar_migracion.';
    END IF;

    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NULL END;
    END IF;

    IF NEW.estado IN ('migrada', 'migrada_con_observaciones') THEN
        IF NEW.filas_raw IS NULL OR NEW.filas_stg IS NULL OR NEW.filas_core IS NULL THEN
            RAISE EXCEPTION
                'No se puede cerrar %/%: faltan filas_raw, filas_stg o filas_core.',
                NEW.migracion_run_id, NEW.tabla_raw;
        END IF;

        IF NEW.detalle IS NULL OR btrim(NEW.detalle) = '' THEN
            RAISE EXCEPTION
                'No se puede cerrar %/% sin detalle de validación.',
                NEW.migracion_run_id, NEW.tabla_raw;
        END IF;

        IF NEW.estado = 'migrada' AND NEW.filas_cuarentena <> 0 THEN
            RAISE EXCEPTION
                'La tabla % no puede quedar migrada con % filas en cuarentena; use migrada_con_observaciones.',
                NEW.tabla_raw, NEW.filas_cuarentena;
        END IF;
    END IF;

    IF NEW.estado = 'raw_only' THEN
        IF NEW.filas_raw IS NULL THEN
            RAISE EXCEPTION
                'No se puede cerrar %/% como raw_only sin filas_raw.',
                NEW.migracion_run_id, NEW.tabla_raw;
        END IF;

        IF NEW.detalle IS NULL OR btrim(NEW.detalle) = '' THEN
            RAISE EXCEPTION
                'No se puede cerrar %/% como raw_only sin justificación.',
                NEW.migracion_run_id, NEW.tabla_raw;
        END IF;

        IF NEW.filas_stg IS NOT NULL OR NEW.filas_core IS NOT NULL OR NEW.filas_cuarentena <> 0 THEN
            RAISE EXCEPTION
                'La tabla % marcada raw_only no puede presentar staging, core o cuarentena publicados.',
                NEW.tabla_raw;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_guardar_estado_migracion_tabla ON raw.migracion_tabla;
CREATE TRIGGER trg_guardar_estado_migracion_tabla
BEFORE INSERT OR UPDATE OR DELETE ON raw.migracion_tabla
FOR EACH ROW
EXECUTE FUNCTION raw.fn_guardar_estado_migracion_tabla();

DROP TRIGGER IF EXISTS trg_guardar_estado_migracion_tabla_truncate ON raw.migracion_tabla;
CREATE TRIGGER trg_guardar_estado_migracion_tabla_truncate
BEFORE TRUNCATE ON raw.migracion_tabla
FOR EACH STATEMENT
EXECUTE FUNCTION raw.fn_guardar_estado_migracion_tabla();

CREATE OR REPLACE FUNCTION raw.fn_snapshot_access_publicado(
    p_source_snapshot_id bigint DEFAULT NULL,
    p_campania text DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_snapshot bigint;
BEGIN
    IF p_source_snapshot_id IS NOT NULL THEN
        SELECT s.source_snapshot_id
          INTO v_snapshot
        FROM raw.source_snapshot s
        JOIN raw.v_snapshot_publicado p
          ON p.tipo = s.tipo
         AND p.campania = s.campania
         AND p.source_snapshot_id = s.source_snapshot_id
        WHERE s.source_snapshot_id = p_source_snapshot_id
          AND s.tipo = 'access'
          AND (p_campania IS NULL OR s.campania = p_campania);
    ELSE
        SELECT p.source_snapshot_id
          INTO v_snapshot
        FROM raw.v_snapshot_publicado p
        WHERE p.tipo = 'access'
          AND (p_campania IS NULL OR p.campania = p_campania)
        ORDER BY p.publicado_en DESC
        LIMIT 1;
    END IF;

    IF v_snapshot IS NULL THEN
        RAISE EXCEPTION 'No existe un snapshot Access publicado para la campaña solicitada.';
    END IF;
    RETURN v_snapshot;
END;
$$;

COMMENT ON FUNCTION raw.fn_snapshot_access_publicado(bigint, text) IS
    'Resuelve únicamente un snapshot Access publicado; impide iniciar core contra un snapshot '
    'aprobado pero no publicado, o contra Excel.';

CREATE OR REPLACE FUNCTION raw.fn_refrescar_estado_migracion(p_migracion_run_id bigint)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_total integer;
    v_terminal integer;
    v_fallidas integer;
    v_observaciones integer;
    v_estado text;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE estado IN ('migrada', 'migrada_con_observaciones', 'raw_only', 'omitida')),
           count(*) FILTER (WHERE estado = 'fallida'),
           count(*) FILTER (WHERE estado IN ('migrada_con_observaciones', 'raw_only'))
      INTO v_total, v_terminal, v_fallidas, v_observaciones
    FROM raw.migracion_tabla
    WHERE migracion_run_id = p_migracion_run_id;

    IF v_total = 0 THEN
        RAISE EXCEPTION 'La ejecución de migración % no tiene tablas planificadas.', p_migracion_run_id;
    END IF;

    v_estado := CASE
        WHEN v_fallidas > 0 THEN 'con_errores'
        WHEN v_terminal = v_total AND v_observaciones > 0 THEN 'completada_con_observaciones'
        WHEN v_terminal = v_total THEN 'completada'
        WHEN v_terminal > 0 OR EXISTS (
            SELECT 1 FROM raw.migracion_tabla
             WHERE migracion_run_id = p_migracion_run_id AND estado = 'en_proceso'
        ) THEN 'en_proceso'
        ELSE 'iniciado'
    END;

    UPDATE raw.migracion_run
       SET estado = v_estado,
           finalizado_en = CASE
               WHEN v_terminal = v_total OR v_fallidas > 0 THEN coalesce(finalizado_en, now())
               ELSE NULL
           END
     WHERE migracion_run_id = p_migracion_run_id;

    RETURN v_estado;
END;
$$;

COMMENT ON FUNCTION raw.fn_refrescar_estado_migracion(bigint) IS
    'Calcula el estado agregado de una ejecución desde sus 23 controles por tabla.';

CREATE OR REPLACE FUNCTION raw.fn_iniciar_migracion(
    p_source_snapshot_id bigint DEFAULT NULL,
    p_campania text DEFAULT NULL,
    p_capa_destino text DEFAULT 'core',
    p_ejecutado_por text DEFAULT current_user,
    p_detalle text DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_tipo text;
    v_campania text;
    v_run bigint;
    v_total integer;
    v_tablas_raw integer;
    v_tablas_raw_cargadas integer;
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'Migración bloqueada: la BD actual es %, se exige aquanqa_migracion.',
            current_database();
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_namespace
        WHERE nspname IN ('dim', 'fact', 'reporting', 'analytics', 'mlflow')
    ) THEN
        RAISE EXCEPTION
            'Migración bloqueada: la fase incremental no permite los esquemas dim/fact/reporting/analytics/mlflow.';
    END IF;

    IF p_capa_destino NOT IN ('stg', 'core') THEN
        RAISE EXCEPTION 'Capa destino no permitida: %', p_capa_destino;
    END IF;

    v_snapshot := raw.fn_snapshot_access_publicado(p_source_snapshot_id, p_campania);
    SELECT tipo, campania INTO v_tipo, v_campania
    FROM raw.source_snapshot WHERE source_snapshot_id = v_snapshot;

    SELECT count(*) INTO v_total FROM raw.migracion_plan_access WHERE activo;

    IF v_total <> 23 THEN
        RAISE EXCEPTION
            'Plan Access inválido: se esperaban 23 tablas activas y existen %.', v_total;
    END IF;

    SELECT count(*), count(*) FILTER (WHERE estado = 'cargado')
      INTO v_tablas_raw, v_tablas_raw_cargadas
    FROM raw.source_table_snapshot
    WHERE source_snapshot_id = v_snapshot;

    IF v_tablas_raw <> 23 OR v_tablas_raw_cargadas <> 23 THEN
        RAISE EXCEPTION
            'Snapshot Access % incompleto en raw: % tablas, % cargadas; se requieren 23/23.',
            v_snapshot, v_tablas_raw, v_tablas_raw_cargadas;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM raw.migracion_run
        WHERE source_snapshot_id = v_snapshot
          AND capa_destino = p_capa_destino
          AND estado IN ('iniciado', 'en_proceso')
    ) THEN
        RAISE EXCEPTION
            'Ya existe una ejecución activa para snapshot % y destino %; no se permite duplicarla.',
            v_snapshot, p_capa_destino;
    END IF;

    PERFORM set_config('raw.migracion_control', 'on', true);

    INSERT INTO raw.migracion_run
        (source_snapshot_id, tipo, campania, capa_destino, total_tablas_plan,
         ejecutado_por, detalle)
    VALUES
        (v_snapshot, v_tipo, v_campania, p_capa_destino, v_total,
         coalesce(nullif(p_ejecutado_por, ''), current_user), p_detalle)
    RETURNING migracion_run_id INTO v_run;

    INSERT INTO raw.migracion_tabla
        (migracion_run_id, source_snapshot_id, tabla_raw, objeto_origen,
         stg_objetos, core_objetos, criterio, filas_raw, detalle)
    SELECT v_run,
           v_snapshot,
           p.tabla_raw,
           ts.objeto_origen,
           p.stg_objetos,
           p.core_objetos,
           p.criterio,
           ts.filas_csv,
           CASE WHEN ts.source_snapshot_id IS NULL
                THEN 'No existe control raw.source_table_snapshot para esta tabla.' END
    FROM raw.migracion_plan_access p
    LEFT JOIN raw.source_table_snapshot ts
      ON ts.source_snapshot_id = v_snapshot
     AND ts.tabla_destino = p.tabla_raw
    WHERE p.activo
    ORDER BY p.orden;

    RETURN v_run;
END;
$$;

COMMENT ON FUNCTION raw.fn_iniciar_migracion(bigint, text, text, text, text) IS
    'Abre una ejecución contra el snapshot Access publicado y siembra el control de las 23 '
    'tablas como pendientes. No carga datos por sí sola.';

CREATE OR REPLACE PROCEDURE raw.sp_registrar_tabla_migracion(
    p_migracion_run_id bigint,
    p_tabla_raw text,
    p_estado text,
    p_filas_stg bigint DEFAULT NULL,
    p_filas_core bigint DEFAULT NULL,
    p_filas_cuarentena bigint DEFAULT 0,
    p_detalle text DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_estado NOT IN ('pendiente', 'en_proceso', 'migrada',
                        'migrada_con_observaciones', 'raw_only', 'fallida', 'omitida') THEN
        RAISE EXCEPTION 'Estado de tabla no permitido: %', p_estado;
    END IF;

    PERFORM set_config('raw.migracion_control', 'on', true);

    UPDATE raw.migracion_tabla
       SET estado = p_estado,
           filas_stg = p_filas_stg,
           filas_core = p_filas_core,
           filas_cuarentena = coalesce(p_filas_cuarentena, 0),
           detalle = p_detalle,
           iniciada_en = coalesce(iniciada_en, CASE WHEN p_estado <> 'pendiente' THEN now() END),
           finalizada_en = CASE
               WHEN p_estado IN ('migrada', 'migrada_con_observaciones', 'raw_only', 'fallida', 'omitida')
               THEN now() ELSE NULL END
     WHERE migracion_run_id = p_migracion_run_id
       AND tabla_raw = p_tabla_raw;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No existe la tabla % en la ejecución %.', p_tabla_raw, p_migracion_run_id;
    END IF;

    PERFORM raw.fn_refrescar_estado_migracion(p_migracion_run_id);
END;
$$;

COMMENT ON PROCEDURE raw.sp_registrar_tabla_migracion(bigint, text, text, bigint, bigint, bigint, text) IS
    'Actualiza una tabla del check-to-check y recalcula el estado agregado de la ejecución.';

-- Estas columnas se consumen por la vista de control que se crea en este mismo archivo.
-- 025_modelo_migracion.sql las completa semánticamente, pero deben existir desde 020 para
-- que una reconstrucción limpia respete el orden lexicográfico de las capas.
ALTER TABLE raw.migracion_tabla
    ADD COLUMN IF NOT EXISTS modelo_version text,
    ADD COLUMN IF NOT EXISTS bloque text,
    ADD COLUMN IF NOT EXISTS decision_modelo text;

CREATE OR REPLACE VIEW raw.v_migracion_resumen AS
SELECT r.migracion_run_id,
       r.source_snapshot_id,
       r.tipo,
       r.campania,
       r.capa_origen,
       r.capa_destino,
       r.estado,
       r.total_tablas_plan,
       count(mt.tabla_raw) AS tablas_registradas,
       count(*) FILTER (WHERE mt.estado IN ('migrada', 'migrada_con_observaciones')) AS tablas_migradas,
       count(*) FILTER (WHERE mt.estado = 'migrada_con_observaciones') AS tablas_con_observaciones,
       count(*) FILTER (WHERE mt.estado = 'pendiente') AS tablas_pendientes,
       count(*) FILTER (WHERE mt.estado = 'en_proceso') AS tablas_en_proceso,
       count(*) FILTER (WHERE mt.estado = 'fallida') AS tablas_fallidas,
       count(*) FILTER (WHERE mt.estado = 'omitida') AS tablas_omitidas,
       round(100.0 * count(*) FILTER (WHERE mt.estado IN ('migrada', 'migrada_con_observaciones'))
             / nullif(r.total_tablas_plan, 0), 2) AS porcentaje_migrado,
       r.ejecutado_por,
       r.iniciado_en,
       r.finalizado_en,
       r.detalle,
       count(*) FILTER (WHERE mt.estado = 'raw_only') AS tablas_raw_only
FROM raw.migracion_run r
LEFT JOIN raw.migracion_tabla mt USING (migracion_run_id)
GROUP BY r.migracion_run_id;

COMMENT ON VIEW raw.v_migracion_resumen IS
    'Resumen ejecutivo del avance: por ejemplo 1 de 23 tablas migradas, 22 pendientes.';

CREATE OR REPLACE VIEW raw.v_migracion_tablas AS
SELECT mt.migracion_run_id,
       mt.source_snapshot_id,
       mt.tabla_raw,
       mt.objeto_origen,
       mt.stg_objetos,
       mt.core_objetos,
       mt.criterio,
       mt.estado,
       mt.filas_raw,
       mt.filas_stg,
       mt.filas_core,
       mt.filas_cuarentena,
       mt.detalle,
       mt.iniciada_en,
       mt.finalizada_en,
       mt.modelo_version,
       mt.bloque,
       mt.decision_modelo
FROM raw.migracion_tabla mt
ORDER BY mt.migracion_run_id DESC, mt.tabla_raw;

COMMENT ON VIEW raw.v_migracion_tablas IS
    'Detalle auditable de cada tabla de Access dentro de cada ejecución de migración.';
