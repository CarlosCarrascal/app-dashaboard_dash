-- ============================================================================
-- Auditoria de la linea base core_baseline_v1.
--
-- Solo lectura: valida el DER fisico del esquema core en
-- aquanqa_migracion. No crea tablas, no cambia datos y no aprueba relaciones
-- candidatas del perfilado Access.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

DO $core_baseline_guard$
DECLARE
    v_tablas_core integer;
    v_tablas_sin_pk integer;
    v_fks_core integer;
    v_fks_core_internas integer;
    v_fks_core_linaje integer;
    v_prefijos_invalidos integer;
    v_aisladas integer;
    v_aisladas_no_esperadas integer;
    v_orphans bigint := 0;
    v_fk_orphans bigint;
    v_join text;
    v_not_null text;
    v_probe_column text;
    r record;
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'BASELINE BLOQUEADA: la BD actual es %, se exige aquanqa_migracion.',
            current_database();
    END IF;

    SELECT count(*)
      INTO v_tablas_core
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'core'
      AND c.relkind = 'r';

    IF v_tablas_core <> 34 THEN
        RAISE EXCEPTION
            'BASELINE BLOQUEADA: core debe tener 34 tablas; existen %.',
            v_tablas_core;
    END IF;

    SELECT count(*)
      INTO v_tablas_sin_pk
    FROM pg_class t
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'core'
      AND t.relkind = 'r'
      AND NOT EXISTS (
          SELECT 1
          FROM pg_constraint pk
          WHERE pk.conrelid = t.oid
            AND pk.contype = 'p'
      );

    IF v_tablas_sin_pk <> 0 THEN
        RAISE EXCEPTION
            'BASELINE BLOQUEADA: existen % tablas core sin PK.',
            v_tablas_sin_pk;
    END IF;

    SELECT count(*)
      INTO v_prefijos_invalidos
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'core'
      AND c.relkind = 'r'
      AND c.relname !~ '^(m_|t_|evt_|ev_|op_|cfg_)';

    IF v_prefijos_invalidos <> 0 THEN
        RAISE EXCEPTION
            'BASELINE BLOQUEADA: existen % tablas core con prefijo no clasificado.',
            v_prefijos_invalidos;
    END IF;

    SELECT count(*)
      INTO v_fks_core
    FROM pg_constraint fk
    JOIN pg_class child ON child.oid = fk.conrelid
    JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
    WHERE fk.contype = 'f'
      AND child_ns.nspname = 'core';

    SELECT count(*)
      INTO v_fks_core_internas
    FROM pg_constraint fk
    JOIN pg_class child ON child.oid = fk.conrelid
    JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
    JOIN pg_class parent ON parent.oid = fk.confrelid
    JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
    WHERE fk.contype = 'f'
      AND child_ns.nspname = 'core'
      AND parent_ns.nspname = 'core';

    SELECT count(*)
      INTO v_fks_core_linaje
    FROM pg_constraint fk
    JOIN pg_class child ON child.oid = fk.conrelid
    JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
    JOIN pg_class parent ON parent.oid = fk.confrelid
    JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
    WHERE fk.contype = 'f'
      AND child_ns.nspname = 'core'
      AND parent_ns.nspname <> 'core';

    IF v_fks_core <> 46 OR v_fks_core_internas <> 45 OR v_fks_core_linaje <> 1 THEN
        RAISE EXCEPTION
            'BASELINE BLOQUEADA: FK core inesperadas (total %, internas %, externas %).',
            v_fks_core, v_fks_core_internas, v_fks_core_linaje;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint fk
        JOIN pg_class child ON child.oid = fk.conrelid
        JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
        JOIN pg_class parent ON parent.oid = fk.confrelid
        JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
        WHERE fk.contype = 'f'
          AND child_ns.nspname = 'core'
          AND parent_ns.nspname = 'raw'
          AND child.relname = 'ev_evaluacion_baya'
          AND parent.relname = 'source_snapshot'
    ) THEN
        RAISE EXCEPTION
            'BASELINE BLOQUEADA: falta la FK de linaje core.ev_evaluacion_baya -> raw.source_snapshot.';
    END IF;

    -- Las tablas sin ninguna FK son esperadas: se unen por fecha, semana o
    -- timestamp y no mediante una FK de negocio.
    SELECT count(*)
      INTO v_aisladas
    FROM pg_class t
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'core'
      AND t.relkind = 'r'
      AND NOT EXISTS (
          SELECT 1 FROM pg_constraint fk
          WHERE fk.contype = 'f'
            AND (fk.conrelid = t.oid OR fk.confrelid = t.oid)
      );

    SELECT count(*)
      INTO v_aisladas_no_esperadas
    FROM pg_class t
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'core'
      AND t.relkind = 'r'
      AND t.relname NOT IN ('op_clima', 't_calendario', 't_semana_evaluacion')
      AND NOT EXISTS (
          SELECT 1 FROM pg_constraint fk
          WHERE fk.contype = 'f'
            AND (fk.conrelid = t.oid OR fk.confrelid = t.oid)
      );

    IF v_aisladas <> 3 OR v_aisladas_no_esperadas <> 0 THEN
        RAISE EXCEPTION
            'BASELINE BLOQUEADA: tablas core aisladas inesperadas (total %, inesperadas %).',
            v_aisladas, v_aisladas_no_esperadas;
    END IF;

    -- Comprueba cada FK core con un anti-join dinamico. Si la FK es nullable,
    -- solo se revisan las filas que tienen una clave informada.
    FOR r IN
        SELECT fk.oid AS constraint_oid,
               fk.conrelid AS child_oid,
               child_ns.nspname AS child_schema,
               child.relname AS child_table,
               fk.confrelid AS parent_oid,
               parent_ns.nspname AS parent_schema,
               parent.relname AS parent_table
        FROM pg_constraint fk
        JOIN pg_class child ON child.oid = fk.conrelid
        JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
        JOIN pg_class parent ON parent.oid = fk.confrelid
        JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
        WHERE fk.contype = 'f'
          AND child_ns.nspname = 'core'
          AND parent_ns.nspname = 'core'
        ORDER BY child.relname, fk.conname
    LOOP
        SELECT string_agg(
                   format('child.%I = parent.%I', child_col.attname, parent_col.attname),
                   ' AND ' ORDER BY child_key.ord
               ),
               string_agg(
                   format('child.%I IS NOT NULL', child_col.attname),
                   ' AND ' ORDER BY child_key.ord
               ),
               (array_agg(parent_col.attname ORDER BY child_key.ord))[1]
          INTO v_join, v_not_null, v_probe_column
        FROM unnest((SELECT conkey FROM pg_constraint WHERE oid = r.constraint_oid))
                 WITH ORDINALITY AS child_key(attnum, ord)
        JOIN unnest((SELECT confkey FROM pg_constraint WHERE oid = r.constraint_oid))
                 WITH ORDINALITY AS parent_key(attnum, ord)
          ON parent_key.ord = child_key.ord
        JOIN pg_attribute child_col
          ON child_col.attrelid = r.child_oid
         AND child_col.attnum = child_key.attnum
        JOIN pg_attribute parent_col
          ON parent_col.attrelid = r.parent_oid
         AND parent_col.attnum = parent_key.attnum
        ;

        EXECUTE format(
            'SELECT count(*)
             FROM %I.%I AS child
             LEFT JOIN %I.%I AS parent ON %s
             WHERE %s AND parent.%I IS NULL',
            r.child_schema, r.child_table,
            r.parent_schema, r.parent_table,
            v_join, v_not_null, v_probe_column
        ) INTO v_fk_orphans;

        v_orphans := v_orphans + v_fk_orphans;

        IF v_fk_orphans <> 0 THEN
            RAISE EXCEPTION
                'BASELINE BLOQUEADA: FK % -> % tiene % huerfanos.',
                r.child_schema || '.' || r.child_table,
                r.parent_schema || '.' || r.parent_table,
                v_fk_orphans;
        END IF;
    END LOOP;

    -- Las relaciones del perfilado siguen siendo candidatas. Esta auditoria
    -- no permite que una evidencia se convierta silenciosamente en FK.
    IF EXISTS (
        SELECT 1 FROM raw.migracion_modelo_relacion
        WHERE estado <> 'candidata'
    ) THEN
        RAISE EXCEPTION
            'BASELINE BLOQUEADA: existe una relacion candidata con estado distinto de candidata.';
    END IF;

    RAISE NOTICE
        'OK core_baseline_v1: % tablas, % FK (% internas + % linaje), % huerfanos.',
        v_tablas_core, v_fks_core, v_fks_core_internas, v_fks_core_linaje, v_orphans;
END
$core_baseline_guard$;

SELECT
    current_database() AS base_validada,
    'core_baseline_v1' AS baseline,
    (SELECT count(*)
     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'core' AND c.relkind = 'r') AS tablas_core,
    (SELECT count(*)
     FROM pg_constraint fk
     JOIN pg_class c ON c.oid = fk.conrelid
     JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE fk.contype = 'f' AND n.nspname = 'core') AS fk_core,
    raw.fn_snapshot_access_publicado(NULL, 'C2026') AS snapshot_access,
    raw.fn_modelo_version_vigente() AS modelo_version,
    'OK: DER core validado' AS resultado;

SELECT relname AS tabla_sin_ninguna_fk
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'core'
  AND c.relkind = 'r'
  AND NOT EXISTS (
      SELECT 1 FROM pg_constraint fk
      WHERE fk.contype = 'f'
        AND (fk.conrelid = c.oid OR fk.confrelid = c.oid)
  )
ORDER BY relname;
