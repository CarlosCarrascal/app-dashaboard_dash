-- ============================================================================
-- Preflight obligatorio antes de cualquier bloque raw -> stg -> core.
-- Este archivo debe fallar ante cualquier condición insegura.
-- ============================================================================

\set ON_ERROR_STOP on

DO $$
DECLARE
    v_missing text;
    v_forbidden text;
    v_extra text;
    v_plan integer;
    v_snapshot bigint;
    v_tablas_raw integer;
    v_tablas_cargadas integer;
    v_excel_publicado integer;
    v_runs_activos integer;
    v_run_id bigint;
    v_tablas_control integer;
    v_modelos_actual integer;
    v_modelo_version text;
    v_modelo_tablas integer;
    v_modelo_fuera_plan integer;
    v_core_sin_prefijo text;
    v_core_sin_catalogo integer;
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: BD actual = %, se exige aquanqa_migracion.',
            current_database();
    END IF;

    SELECT string_agg(x.nombre, ', ' ORDER BY x.nombre)
      INTO v_missing
    FROM (VALUES ('raw'), ('stg'), ('qua'), ('core')) AS x(nombre)
    WHERE NOT EXISTS (
        SELECT 1 FROM pg_namespace n WHERE n.nspname = x.nombre
    );

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: faltan esquemas obligatorios: %.', v_missing;
    END IF;

    SELECT string_agg(n.nspname, ', ' ORDER BY n.nspname)
      INTO v_forbidden
    FROM pg_namespace n
    WHERE n.nspname IN ('dim', 'fact', 'reporting', 'analytics', 'mlflow');

    IF v_forbidden IS NOT NULL THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: esquemas fuera de fase presentes: %.', v_forbidden;
    END IF;

    SELECT string_agg(n.nspname, ', ' ORDER BY n.nspname)
      INTO v_extra
    FROM pg_namespace n
    WHERE n.nspname NOT IN ('information_schema', 'public', 'raw', 'stg', 'qua', 'core')
      AND n.nspname NOT LIKE 'pg\_%' ESCAPE E'\\';

    IF v_extra IS NOT NULL THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: existen esquemas de aplicación no autorizados: %.', v_extra;
    END IF;

    -- El nombre semántico es parte del contrato de core. raw conserva los nombres de
    -- Access; core no debe volver a llenarse con nombres físicos sin clasificar.
    SELECT string_agg(c.relname, ', ' ORDER BY c.relname)
      INTO v_core_sin_prefijo
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'core'
      AND c.relkind = 'r'
      AND c.relname !~ '^(m_|t_|ev_|evt_|op_|cfg_)';

    IF v_core_sin_prefijo IS NOT NULL THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: tablas core sin prefijo semántico: %.', v_core_sin_prefijo;
    END IF;

    IF to_regclass('core.v_catalogo') IS NULL THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: falta core.v_catalogo, catálogo obligatorio de core.';
    END IF;

    SELECT count(*) INTO v_core_sin_catalogo
    FROM core.v_catalogo
    WHERE tipo = '(sin clasificar)' OR dominio = '(sin clasificar)';

    IF v_core_sin_catalogo <> 0 THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: existen % tablas core sin clasificación en core.v_catalogo.',
            v_core_sin_catalogo;
    END IF;

    SELECT count(*) INTO v_plan
    FROM raw.migracion_plan_access
    WHERE activo;

    IF v_plan <> 23 THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: el plan Access debe tener 23 tablas activas; tiene %.',
            v_plan;
    END IF;

    IF to_regclass('raw.migracion_modelo_version') IS NULL
       OR to_regclass('raw.migracion_modelo_tabla') IS NULL THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: falta registrar el catálogo semántico versionado de la migración.';
    END IF;

    SELECT count(*) INTO v_modelos_actual
    FROM raw.migracion_modelo_version
    WHERE vigente AND estado = 'aprobado';

    IF v_modelos_actual <> 1 THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: debe existir exactamente un modelo semántico aprobado y vigente; existen %.',
            v_modelos_actual;
    END IF;

    v_modelo_version := raw.fn_modelo_version_vigente();

    SELECT count(*) INTO v_modelo_tablas
    FROM raw.migracion_modelo_tabla
    WHERE modelo_version = v_modelo_version;

    IF v_modelo_tablas <> 23 THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: el modelo % debe cubrir 23 fuentes Access; cubre %.',
            v_modelo_version, v_modelo_tablas;
    END IF;

    -- La cobertura del modelo debe coincidir exactamente con el plan de fuentes.
    -- Que una fuente termine en raw_only no la excluye del modelo.
    SELECT count(*) INTO v_modelo_fuera_plan
    FROM (
        SELECT mt.tabla_raw
        FROM raw.migracion_modelo_tabla mt
        WHERE mt.modelo_version = v_modelo_version
          AND NOT EXISTS (
              SELECT 1
              FROM raw.migracion_plan_access p
              WHERE p.activo AND p.tabla_raw = mt.tabla_raw
          )
        UNION ALL
        SELECT p.tabla_raw
        FROM raw.migracion_plan_access p
        WHERE p.activo
          AND NOT EXISTS (
              SELECT 1
              FROM raw.migracion_modelo_tabla mt
              WHERE mt.modelo_version = v_modelo_version
                AND mt.tabla_raw = p.tabla_raw
          )
    ) diferencia;

    IF v_modelo_fuera_plan <> 0 THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: el modelo semántico no coincide exactamente con las 23 fuentes activas (diferencias: %).',
            v_modelo_fuera_plan;
    END IF;

    -- Access es la única fuente primaria autorizada para iniciar esta campaña.
    v_snapshot := raw.fn_snapshot_access_publicado(NULL, 'C2026');

    SELECT count(*), count(*) FILTER (WHERE estado = 'cargado')
      INTO v_tablas_raw, v_tablas_cargadas
    FROM raw.source_table_snapshot
    WHERE source_snapshot_id = v_snapshot;

    IF v_tablas_raw <> 23 OR v_tablas_cargadas <> 23 THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: snapshot Access % en raw tiene % tablas y % cargadas; se requieren 23/23.',
            v_snapshot, v_tablas_raw, v_tablas_cargadas;
    END IF;

    SELECT count(*) INTO v_excel_publicado
    FROM raw.v_snapshot_publicado
    WHERE tipo = 'xlsx' AND campania = 'C2026';

    IF v_excel_publicado <> 0 THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: Excel aparece publicado como fuente primaria de C2026.';
    END IF;

    SELECT count(*), min(migracion_run_id)
      INTO v_runs_activos, v_run_id
    FROM raw.migracion_run
    WHERE source_snapshot_id = v_snapshot
      AND campania = 'C2026'
      AND capa_destino = 'core'
      AND estado IN ('iniciado', 'en_proceso');

    IF v_runs_activos > 1 THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: existen % ejecuciones activas para el mismo snapshot Access.',
            v_runs_activos;
    END IF;

    IF v_runs_activos = 1 THEN
        IF EXISTS (
            SELECT 1
            FROM raw.migracion_run
            WHERE migracion_run_id = v_run_id
              AND modelo_version IS DISTINCT FROM v_modelo_version
        ) THEN
            RAISE EXCEPTION
                'PREFLIGHT BLOQUEADO: la ejecución % no está enlazada al modelo semántico vigente %.',
                v_run_id, v_modelo_version;
        END IF;

        SELECT count(*) INTO v_tablas_control
        FROM raw.migracion_tabla
        WHERE migracion_run_id = v_run_id;

        IF v_tablas_control <> 23 THEN
            RAISE EXCEPTION
                'PREFLIGHT BLOQUEADO: la ejecución % no tiene 23 controles por tabla; tiene %.',
                v_run_id, v_tablas_control;
        END IF;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_views
        WHERE schemaname = 'raw'
          AND viewname = 'v_m_lotes_principal_vigente'
    ) THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: no existe la vista de M_Lotes Access principal.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM raw.v_m_lotes_principal_vigente) THEN
        RAISE EXCEPTION
            'PREFLIGHT BLOQUEADO: M_Lotes Access principal no contiene filas.';
    END IF;
END;
$$;

SELECT current_database() AS base_validada,
       raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_access_validado,
       (SELECT count(*) FROM raw.migracion_plan_access WHERE activo) AS tablas_plan,
       (SELECT count(*) FROM raw.v_m_lotes_principal_vigente) AS lotes_access_principales,
       'OK: preflight obligatorio superado' AS resultado;
