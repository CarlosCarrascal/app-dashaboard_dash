-- ============================================================================
-- 50_carga_core · 015 · Cargas controladas por bloque
--
-- Estos procedimientos son el camino normal durante la migración incremental. El ejecutor
-- monolítico 090 sigue reservado para una reconstrucción completa autorizada; aquí cada bloque
-- solo toca sus destinos y sus prerequisitos explícitos.
-- ============================================================================

CREATE OR REPLACE PROCEDURE core.sp_cargar_contexto_b02()
LANGUAGE plpgsql
AS $$
DECLARE
    v_campanias integer;
    v_calendario integer;
    v_semanas integer;
    v_evaluadores integer;
    v_poda integer;
    v_muestras integer;
    v_equivalencias integer;
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'B02 bloqueado: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;

    IF to_regclass('stg.m_evaluadores') IS NULL
       OR to_regclass('stg.m_time') IS NULL
       OR to_regclass('stg.m_n_muestra') IS NULL
       OR to_regclass('stg.m_poda') IS NULL THEN
        RAISE EXCEPTION
            'B02 incompleto: materialice m_evaluadores, m_time, m_n_muestra y m_poda antes de cargar core.';
    END IF;

    -- B02 se ejecuta antes de los hechos. Si se intenta reconstruirlo después, se detiene para
    -- no borrar FKs de bloques posteriores; un snapshot/modelo nuevo debe usar una estrategia
    -- de publicación atómica distinta.
    IF coalesce(current_setting('aquanqa.allow_full_core', true), '') <> 'on'
       AND (EXISTS (SELECT 1 FROM core.m_usuario WHERE evaluador_id IS NOT NULL)
            OR EXISTS (SELECT 1 FROM core.op_tareo WHERE evaluador_id IS NOT NULL)
            OR EXISTS (SELECT 1 FROM core.ev_evaluacion_ramas)
            OR EXISTS (SELECT 1 FROM core.ev_flores)
            OR EXISTS (SELECT 1 FROM core.ev_estados)
            OR EXISTS (SELECT 1 FROM core.ev_brotes)
            OR EXISTS (SELECT 1 FROM core.ev_evaluacion_baya)
            OR EXISTS (SELECT 1 FROM core.op_cosecha)
            OR EXISTS (SELECT 1 FROM core.op_packing)
            OR EXISTS (SELECT 1 FROM core.op_forecast_campania)
            OR EXISTS (SELECT 1 FROM core.op_forecast_semanal)) THEN
        RAISE EXCEPTION
            'B02 bloqueado: ya existen hechos dependientes; no se permite reconstruir contexto destruyendo FKs.';
    END IF;

    -- Limpieza idempotente de un intento fallido del mismo bloque. No se usa CASCADE y no se
    -- toca la cadena B01 (empresa/fundo/módulo/turno/variedad/lote).
    DELETE FROM core.cfg_muestra_requerida;
    DELETE FROM core.evt_poda;
    DELETE FROM core.t_semana_evaluacion;
    DELETE FROM core.t_calendario;
    DELETE FROM core.t_campania;
    DELETE FROM core.m_productor_equivalencia;
    DELETE FROM core.m_evaluador;

    ---------------------------------------------------------------- evaluadores
    -- El DNI es la identidad. Si se repite, se conserva la ficha activa y más completa y el
    -- resto se registra en qua mediante el trigger de linaje de cuarentena.
    WITH ordenadas AS (
        SELECT v.*,
               row_number() OVER (
                   PARTITION BY dni
                   ORDER BY activo DESC,
                            (codigo IS NOT NULL) DESC,
                            (zona IS NOT NULL) DESC,
                            (celular IS NOT NULL) DESC,
                            (nombres IS NOT NULL) DESC,
                            (apellidos IS NOT NULL) DESC,
                            inicio_labores DESC NULLS LAST,
                            nacimiento DESC NULLS LAST,
                            codigo NULLS LAST,
                            zona NULLS LAST,
                            celular NULLS LAST
               ) AS orden_dni
        FROM stg.m_evaluadores v
        WHERE dni IS NOT NULL AND dni <> ''
    )
    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'M_Evaluadores', 'core.m_evaluador', 'EVALUADOR_DUPLICADO', 'MIGRACION-DEDUP',
           'DNI repetido en el maestro; se conserva la ficha activa y más completa.',
           jsonb_build_object('orden_conservado', 1, 'orden_descartado', orden_dni,
                              'registro', to_jsonb(ordenadas))
    FROM ordenadas
    WHERE orden_dni > 1;

    INSERT INTO core.m_evaluador (dni, nombres, apellidos, codigo, zona, celular,
                                inicio_labores, nacimiento, activo, en_maestro)
    SELECT dni, nombres, apellidos, codigo, zona, celular,
           inicio_labores, nacimiento, activo, true
    FROM (
        SELECT v.*,
               row_number() OVER (
                   PARTITION BY dni
                   ORDER BY activo DESC,
                            (codigo IS NOT NULL) DESC,
                            (zona IS NOT NULL) DESC,
                            (celular IS NOT NULL) DESC,
                            (nombres IS NOT NULL) DESC,
                            (apellidos IS NOT NULL) DESC,
                            inicio_labores DESC NULLS LAST,
                            nacimiento DESC NULLS LAST,
                            codigo NULLS LAST,
                            zona NULLS LAST,
                            celular NULLS LAST
               ) AS orden_dni
        FROM stg.m_evaluadores v
        WHERE dni IS NOT NULL AND dni <> ''
    ) ordenadas
    WHERE orden_dni = 1;
    GET DIAGNOSTICS v_evaluadores = ROW_COUNT;

    ----------------------------------------------------------------------- tiempo
    -- En B02 la fuente disponible para campañas es M_Poda. B04/B05 pueden ampliar sus fechas
    -- en una reconstrucción posterior, pero no se consulta información de esos bloques aquí.
    INSERT INTO core.t_campania (codigo, fecha_inicio, fecha_fin, origen_fechas)
    SELECT campania, min(fecha_inicio), max(fecha_inicio), 'derivado'
    FROM stg.m_poda
    WHERE campania IS NOT NULL AND campania <> ''
    GROUP BY campania
    ORDER BY campania;
    GET DIAGNOSTICS v_campanias = ROW_COUNT;

    INSERT INTO core.t_calendario (
        fecha, anio, mes, dia, trimestre, semana, dia_semana, mes_abrev,
        anio_mes, anio_semana, sem_ev_conteo, mes_sem, campanias_activas)
    SELECT t.fecha,
           coalesce(t.anio, extract(year FROM t.fecha)::smallint),
           extract(month FROM t.fecha)::smallint,
           extract(day FROM t.fecha)::smallint,
           extract(quarter FROM t.fecha)::smallint,
           coalesce(t.semana, extract(week FROM t.fecha)::smallint),
           extract(isodow FROM t.fecha)::smallint,
           coalesce(nullif(t.mes_abrev, ''), initcap(to_char(t.fecha, 'TMMon'))),
           to_char(t.fecha, 'YYYY-MM'),
           to_char(t.fecha, 'IYYY') || '-' || to_char(t.fecha, 'IW'),
           t.sem_ev_conteo,
           t.mes_sem,
           (SELECT count(*)
              FROM core.t_campania c
             WHERE t.fecha BETWEEN c.fecha_inicio AND c.fecha_fin)::smallint
    FROM (
        SELECT DISTINCT ON (fecha) fecha, anio, semana, mes_abrev, sem_ev_conteo, mes_sem
        FROM stg.m_time
        WHERE fecha IS NOT NULL
        ORDER BY fecha, anio NULLS LAST, sem_ev_conteo NULLS LAST
    ) t
    ORDER BY t.fecha;
    GET DIAGNOSTICS v_calendario = ROW_COUNT;

    INSERT INTO core.t_semana_evaluacion (anio, sem_ev_conteo, fecha_inicio, fecha_fin, dias)
    SELECT anio, sem_ev_conteo, min(fecha), max(fecha), count(*)::smallint
    FROM core.t_calendario
    WHERE sem_ev_conteo IS NOT NULL
    GROUP BY anio, sem_ev_conteo
    ORDER BY anio, sem_ev_conteo;
    GET DIAGNOSTICS v_semanas = ROW_COUNT;

    -------------------------------------------------------------------------- poda
    -- Estos dos procedimientos ya registran la fila completa en qua antes de filtrar el lote.
    CALL core.sp_cargar_poda();
    SELECT count(*) INTO v_poda FROM core.evt_poda;

    ------------------------------------------------------------------------ muestreo
    CALL core.sp_cargar_muestreo();
    SELECT count(*) INTO v_muestras FROM core.cfg_muestra_requerida;

    ---------------------------------------------------------------- equivalencias
    INSERT INTO core.m_productor_equivalencia (productor_norm, productor, empresa_id, origen)
    SELECT DISTINCT ON (stg.fn_norm_texto(e.productor))
           stg.fn_norm_texto(e.productor), btrim(e.productor), em.empresa_id,
           'M_EquivalenciaElifab'
    FROM raw.v_m_equivalencia_elifab_vigente e
    LEFT JOIN core.m_empresa em
           ON stg.fn_norm_texto(em.nombre) = stg.fn_norm_texto(e.empresa)
    WHERE e.productor IS NOT NULL AND btrim(e.productor) <> ''
    ORDER BY stg.fn_norm_texto(e.productor), e.productor;
    GET DIAGNOSTICS v_equivalencias = ROW_COUNT;

    RAISE NOTICE
        'B02 contexto: % evaluadores, % campañas, % días, % semanas, % podas, % muestras, % equivalencias.',
        v_evaluadores, v_campanias, v_calendario, v_semanas, v_poda, v_muestras, v_equivalencias;
END;
$$;

COMMENT ON PROCEDURE core.sp_cargar_contexto_b02() IS
    'Carga exclusivamente B02 desde M_Evaluadores, M_Time, M_nMuestra, M_Poda y M_Equiv. '
    'No consulta staging de evaluaciones, operación ni forecast.';

CREATE OR REPLACE PROCEDURE raw.sp_registrar_lineage_contexto_b02()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloque bigint;
    v_modelo text := raw.fn_modelo_version_vigente();
BEGIN
    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
        v_run := nullif(current_setting('aquanqa.migracion_run_id', true), '')::bigint;
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'Linaje B02 bloqueado: faltan GUC de snapshot/run/bloque.';
    END;

    IF v_snapshot IS NULL OR v_run IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'Linaje B02 bloqueado: faltan GUC de snapshot/run/bloque.';
    END IF;

    -- Evaluadores: se incluyen todas las filas del maestro que desembocan en la ficha
    -- deduplicada; así el registro descartado no desaparece del linaje.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_evaluadores', r.source_row_number, r.source_row_hash, 'core', 'evaluador',
           jsonb_build_object('evaluador_id', e.evaluador_id),
           'deduplicada', jsonb_build_object('dni', e.dni)
    FROM core.m_evaluador e
    JOIN raw.m_evaluadores r
      ON r.source_snapshot_id = v_snapshot
     AND btrim(r.dni) = e.dni
    ON CONFLICT DO NOTHING;

    -- M_Time → calendario por fecha.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_time', r.source_row_number, r.source_row_hash, 'core', 'calendario',
           jsonb_build_object('fecha', c.fecha), 'derivada', '{}'::jsonb
    FROM core.t_calendario c
    JOIN raw.m_time r
      ON r.source_snapshot_id = v_snapshot
     AND stg.fn_a_fecha(r.fecha) = c.fecha
    ON CONFLICT DO NOTHING;

    -- M_Poda aporta la existencia y rango observado de cada campaña.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_poda', r.source_row_number, r.source_row_hash, 'core', 'campania',
           jsonb_build_object('campania_id', c.campania_id), 'derivada',
           jsonb_build_object('codigo', c.codigo)
    FROM core.t_campania c
    JOIN raw.m_poda r
      ON r.source_snapshot_id = v_snapshot
     AND upper(btrim(r.campania)) = c.codigo
    ON CONFLICT DO NOTHING;

    -- M_Poda → core.evt_poda por la misma resolución de identidad usada por staging.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_poda', r.source_row_number, r.source_row_hash, 'core', 'poda',
           jsonb_build_object('poda_id', p.poda_id), 'agregada',
           jsonb_build_object('campania_id', p.campania_id, 'lote_id', p.lote_id)
    FROM core.evt_poda p
    JOIN core.t_campania c ON c.campania_id = p.campania_id
    JOIN raw.m_poda r
      ON r.source_snapshot_id = v_snapshot
     AND upper(btrim(r.campania)) = c.codigo
     AND stg.fn_resolver_lote(r.fundo, r.modulo, r.lote) = p.lote_id
    ON CONFLICT DO NOTHING;

    -- M_nMuestra → core.cfg_muestra_requerida. Los duplicados exactos pueden producir más de una
    -- fila de origen para una misma fila de core y se conservan todos.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_n_muestra', r.source_row_number, r.source_row_hash, 'core', 'muestra_requerida',
           jsonb_build_object('muestra_id', m.muestra_id), 'deduplicada',
           jsonb_build_object('evaluacion', m.evaluacion)
    FROM core.cfg_muestra_requerida m
    JOIN raw.m_n_muestra r
      ON r.source_snapshot_id = v_snapshot
     AND btrim(r.evaluacion) = m.evaluacion
     AND stg.fn_resolver_lote(r.fundo, r.modulo, r.lote) = m.lote_id
     AND stg.fn_a_entero(r.cortina) IS NOT DISTINCT FROM m.cortina
     AND stg.fn_a_entero(r.hilera) IS NOT DISTINCT FROM m.hilera
     AND stg.fn_a_entero(r.planta) IS NOT DISTINCT FROM m.planta
     AND stg.fn_a_entero(r.muestras) = m.muestras
    ON CONFLICT DO NOTHING;

    -- M_EquivalenciaElifab se conserva como vocabulario normalizado.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_equivalencia_elifab', r.source_row_number, r.source_row_hash, 'core',
           'productor_equivalencia', jsonb_build_object('productor_norm', p.productor_norm),
           'deduplicada', '{}'::jsonb
    FROM core.m_productor_equivalencia p
    JOIN raw.m_equivalencia_elifab r
      ON r.source_snapshot_id = v_snapshot
     AND stg.fn_norm_texto(r.productor) = p.productor_norm
    ON CONFLICT DO NOTHING;
END;
$$;

COMMENT ON PROCEDURE raw.sp_registrar_lineage_contexto_b02() IS
    'Registra el linaje de B02 desde las filas de raw hasta sus objetos core derivados.';

CREATE OR REPLACE PROCEDURE raw.sp_registrar_lineage_b01()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloque bigint;
    v_modelo text := raw.fn_modelo_version_vigente();
BEGIN
    SELECT e.source_snapshot_id, e.migracion_run_id, e.bloque_ejecucion_id
      INTO v_snapshot, v_run, v_bloque
    FROM raw.migracion_bloque_ejecucion e
    WHERE e.modelo_version = v_modelo
      AND e.bloque = 'B01_IDENTIDAD'
      AND e.estado = 'publicado'
    ORDER BY e.bloque_ejecucion_id DESC
    LIMIT 1;

    IF v_snapshot IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'No existe un B01 publicado para registrar linaje.';
    END IF;

    -- Las entidades de ubicación se derivan de M_Lotes, pero cada una queda vinculada a las
    -- filas que la sustentan. La fila centinela no tiene una fuente física y por eso no aparece.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_lotes', r.source_row_number, r.source_row_hash, 'core', 'empresa',
           jsonb_build_object('empresa_id', e.empresa_id), 'derivada',
           jsonb_build_object('empresa', e.nombre)
    FROM raw.m_lotes r
    JOIN core.m_empresa e
      ON NOT e.es_sentinel
     AND stg.fn_norm_texto(r.fundo_ppto) = stg.fn_norm_texto(e.nombre)
    WHERE r.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_lotes', r.source_row_number, r.source_row_hash, 'core', 'fundo',
           jsonb_build_object('fundo_id', f.fundo_id), 'derivada',
           jsonb_build_object('fundo', f.codigo)
    FROM raw.m_lotes r
    JOIN core.m_fundo f
      ON NOT f.es_sentinel
     AND stg.fn_norm_texto(r.fundo) = stg.fn_norm_texto(f.codigo)
    WHERE r.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_lotes', r.source_row_number, r.source_row_hash, 'core', 'modulo',
           jsonb_build_object('modulo_id', m.modulo_id), 'derivada',
           jsonb_build_object('codigo', m.codigo)
    FROM raw.m_lotes r
    JOIN core.m_fundo f
      ON NOT f.es_sentinel
     AND stg.fn_norm_texto(r.fundo) = stg.fn_norm_texto(f.codigo)
    JOIN core.m_modulo m
      ON m.fundo_id = f.fundo_id
     AND stg.fn_norm_modulo(r.modulo) = m.codigo
    WHERE r.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_lotes', r.source_row_number, r.source_row_hash, 'core', 'turno',
           jsonb_build_object('turno_id', t.turno_id), 'derivada',
           jsonb_build_object('codigo', t.codigo)
    FROM raw.m_lotes r
    JOIN core.m_turno t ON stg.fn_norm_turno(r.turno) = t.codigo
    WHERE r.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_lotes', r.source_row_number, r.source_row_hash, 'core', 'variedad',
           jsonb_build_object('variedad_id', v.variedad_id), 'derivada',
           jsonb_build_object('nombre', v.nombre)
    FROM raw.m_lotes r
    JOIN core.m_variedad_alias va ON va.alias_norm = stg.fn_norm_texto(r.variedad)
    JOIN core.m_variedad v ON v.variedad_id = va.variedad_id
    WHERE r.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    -- Lote es el objeto de grano de la fuente y conserva una correspondencia 1:1 en B01.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_lotes', r.source_row_number, r.source_row_hash, 'core', 'lote',
           jsonb_build_object('lote_id', l.lote_id), 'directa',
           jsonb_build_object('codigo', l.codigo)
    FROM raw.m_lotes r
    JOIN core.m_fundo f
      ON NOT f.es_sentinel
     AND stg.fn_norm_texto(r.fundo) = stg.fn_norm_texto(f.codigo)
    JOIN core.m_modulo m
      ON m.fundo_id = f.fundo_id
     AND stg.fn_norm_modulo(r.modulo) = m.codigo
    JOIN core.m_lote l
      ON l.modulo_id = m.modulo_id
     AND stg.fn_norm_lote(r.lote) = l.codigo
    WHERE r.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    -- Los diccionarios también son derivados de la fuente; no se enlaza la fila centinela.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_lotes', r.source_row_number, r.source_row_hash, 'core', 'fundo_alias',
           jsonb_build_object('alias_norm', a.alias_norm), 'derivada', '{}'::jsonb
    FROM raw.m_lotes r
    JOIN core.m_fundo_alias a
      ON a.alias_norm IN (
           stg.fn_norm_texto(r.fundo),
           stg.fn_norm_texto(r.fundo_ppto),
           stg.fn_norm_texto(r.fundo_pptom5)
         )
    WHERE r.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'm_lotes', r.source_row_number, r.source_row_hash, 'core', 'variedad_alias',
           jsonb_build_object('alias_norm', a.alias_norm), 'derivada', '{}'::jsonb
    FROM raw.m_lotes r
    JOIN core.m_variedad_alias a ON a.alias_norm = stg.fn_norm_texto(r.variedad)
    WHERE r.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;
END;
$$;

COMMENT ON PROCEDURE raw.sp_registrar_lineage_b01() IS
    'Completa el linaje de las entidades de identidad publicadas por B01.';

-- ============================================================================
-- B03 · Fenología
-- ============================================================================

CREATE OR REPLACE PROCEDURE core.sp_cargar_fenologia_b03()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloque bigint;
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'B03 bloqueado: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;

    IF to_regclass('stg.e01_ramas') IS NULL
       OR to_regclass('stg.e02_flores') IS NULL
       OR to_regclass('stg.e03_estados') IS NULL
       OR to_regclass('stg.e04_brotes') IS NULL
       OR to_regclass('stg.e05_bayas') IS NULL
       OR to_regclass('stg.e05_seguimiento') IS NULL THEN
        RAISE EXCEPTION
            'B03 incompleto: materialice E01, E02, E03, E04, E05_Diametros y E05_Seguimiento antes de cargar core.';
    END IF;

    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
        v_run := nullif(current_setting('aquanqa.migracion_run_id', true), '')::bigint;
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'B03 bloqueado: faltan GUC de snapshot/run/bloque.';
    END;

    IF v_snapshot IS NULL OR v_run IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'B03 bloqueado: faltan GUC de snapshot/run/bloque.';
    END IF;

    -- B03 puede reintentarse si falló antes de publicar, pero no después de que un bloque
    -- posterior dependa de sus claves. La única excepción es la señal transaccional que el
    -- orquestador antepone durante una reconstrucción completa autorizada; B04/B05 se
    -- ejecutarán después dentro de la misma transacción y reemplazarán esos destinos.
    IF coalesce(current_setting('aquanqa.allow_full_core', true), '') <> 'on'
       AND (EXISTS (SELECT 1 FROM core.op_cosecha)
            OR EXISTS (SELECT 1 FROM core.op_clima)
            OR EXISTS (SELECT 1 FROM core.op_packing)
            OR EXISTS (SELECT 1 FROM core.op_forecast_campania)
            OR EXISTS (SELECT 1 FROM core.op_forecast_semanal)
            OR EXISTS (SELECT 1 FROM core.op_tareo)) THEN
        RAISE EXCEPTION
            'B03 bloqueado: ya existen hechos de bloques posteriores; no se reconstruye fenología sobre dependencias publicadas.';
    END IF;

    DELETE FROM qua.rechazos
    WHERE bloque_ejecucion_id = v_bloque
      AND tabla_origen IN ('E01_Ramas', 'E02_ConteoFlores', 'E03_ConteoEstados',
                           'E04_Brotes', 'E05_DiametrosBayas', 'E05_Seguimiento');

    TRUNCATE core.ev_baya_observacion, core.ev_evaluacion_baya,
             core.ev_baya_medicion, core.ev_brotes, core.ev_estados, core.ev_flores,
             core.ev_rama_medicion, core.ev_evaluacion_ramas
        RESTART IDENTITY;

    -- Los evaluadores desconocidos se incorporan como identidades incompletas para no perder
    -- el hecho capturado. Cada aparición por fuente se explica en qua con el mismo contexto de
    -- ejecución; no se vuelve a borrar el maestro M_Evaluadores cargado en B02.
    DELETE FROM core.m_evaluador WHERE NOT en_maestro;

    WITH capturas AS (
        SELECT 'E01_Ramas'::text AS tabla_origen, btrim(dni) AS dni
        FROM stg.e01_ramas
        WHERE dni IS NOT NULL AND btrim(dni) <> ''
        UNION ALL
        SELECT 'E02_ConteoFlores', btrim(dni)
        FROM stg.e02_flores
        WHERE dni IS NOT NULL AND btrim(dni) <> ''
        UNION ALL
        SELECT 'E03_ConteoEstados', btrim(dni)
        FROM stg.e03_estados
        WHERE dni IS NOT NULL AND btrim(dni) <> ''
        UNION ALL
        SELECT 'E04_Brotes', btrim(dni)
        FROM stg.e04_brotes
        WHERE dni IS NOT NULL AND btrim(dni) <> ''
        UNION ALL
        SELECT 'E05_Seguimiento', btrim(dni)
        FROM stg.e05_seguimiento
        WHERE dni IS NOT NULL AND btrim(dni) <> ''
    ),
    desconocidos AS (
        SELECT DISTINCT dni
        FROM capturas c
        WHERE NOT EXISTS (SELECT 1 FROM core.m_evaluador e WHERE e.dni = c.dni)
    )
    INSERT INTO core.m_evaluador (dni, activo, en_maestro)
    SELECT dni, true, false
    FROM desconocidos;

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT c.tabla_origen, 'core.m_evaluador', 'EVALUADOR_SIN_MAESTRO', 'H-09',
           'El DNI aparece en una captura fenológica, pero no existe en M_Evaluadores. '
           'Se crea una identidad incompleta para conservar el hecho.',
           jsonb_build_object('dni', c.dni, 'apariciones', count(*))
    FROM (
        SELECT 'E01_Ramas'::text AS tabla_origen, btrim(dni) AS dni FROM stg.e01_ramas
        WHERE dni IS NOT NULL AND btrim(dni) <> ''
        UNION ALL
        SELECT 'E02_ConteoFlores', btrim(dni) FROM stg.e02_flores
        WHERE dni IS NOT NULL AND btrim(dni) <> ''
        UNION ALL
        SELECT 'E03_ConteoEstados', btrim(dni) FROM stg.e03_estados
        WHERE dni IS NOT NULL AND btrim(dni) <> ''
        UNION ALL
        SELECT 'E04_Brotes', btrim(dni) FROM stg.e04_brotes
        WHERE dni IS NOT NULL AND btrim(dni) <> ''
        UNION ALL
        SELECT 'E05_Seguimiento', btrim(dni) FROM stg.e05_seguimiento
        WHERE dni IS NOT NULL AND btrim(dni) <> ''
    ) c
    WHERE NOT EXISTS (
        SELECT 1 FROM stg.m_evaluadores m WHERE btrim(m.dni) = c.dni
    )
    GROUP BY c.tabla_origen, c.dni;

    CALL core.sp_cargar_ramas();
    CALL core.sp_cargar_flores();
    CALL core.sp_cargar_estados();
    CALL core.sp_cargar_brotes();
    CALL core.sp_cargar_bayas();
    CALL core.sp_cargar_evaluaciones_baya();
END;
$$;

COMMENT ON PROCEDURE core.sp_cargar_fenologia_b03() IS
    'Carga únicamente el bloque fenológico E01-E05. Reintenta de forma controlada si no '
    'existen hechos posteriores y conserva evaluadores fuera del maestro como identidades '
    'incompletas documentadas en qua.';

CREATE OR REPLACE PROCEDURE raw.sp_registrar_lineage_fenologia_b03()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloque bigint;
    v_modelo text := raw.fn_modelo_version_vigente();
BEGIN
    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
        v_run := nullif(current_setting('aquanqa.migracion_run_id', true), '')::bigint;
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'Linaje B03 bloqueado: faltan GUC de snapshot/run/bloque.';
    END;

    IF v_snapshot IS NULL OR v_run IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'Linaje B03 bloqueado: faltan GUC de snapshot/run/bloque.';
    END IF;

    -- E01: una fila de origen aporta a la cabecera de planta y, cuando trae una rama válida,
    -- a una medición de detalle. Los duplicados exactos apuntan al mismo detalle deduplicado.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'e01_ramas', s.source_row_number, s.source_row_hash, 'core',
           'evaluacion_ramas', jsonb_build_object('evaluacion_ramas_id', c.evaluacion_ramas_id),
           'agregada', jsonb_build_object('grano_origen', 'rama', 'grano_core', 'planta')
    FROM stg.e01_ramas s
    JOIN core.ev_evaluacion_ramas c
      ON c.lote_id = s.lote_id
     AND c.fecha = s.fecha
     AND c.cortina = s.cortina
     AND c.hilera = s.hilera
     AND c.planta = s.planta
    WHERE s.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'e01_ramas', s.source_row_number, s.source_row_hash, 'core', 'rama_medicion',
           jsonb_build_object('rama_medicion_id', rm.rama_medicion_id),
           CASE WHEN count(*) OVER (
                    PARTITION BY s.lote_id, s.fecha, s.cortina, s.hilera, s.planta,
                                 s.nro_rama, s.diametro, s.id_origen
                ) > 1 THEN 'deduplicada' ELSE 'directa' END,
           jsonb_build_object('grano_origen', 'rama', 'grano_core', 'rama_medida')
    FROM stg.e01_ramas s
    JOIN core.ev_evaluacion_ramas c
      ON c.lote_id = s.lote_id
     AND c.fecha = s.fecha
     AND c.cortina = s.cortina
     AND c.hilera = s.hilera
     AND c.planta = s.planta
    JOIN LATERAL (
        SELECT x.rama_medicion_id
        FROM core.ev_rama_medicion x
        WHERE x.evaluacion_ramas_id = c.evaluacion_ramas_id
          AND x.nro_rama = s.nro_rama
          AND x.diametro = round(s.diametro::numeric, 4)
          AND x.id_origen IS NOT DISTINCT FROM s.id_origen
        ORDER BY x.rama_medicion_id
        LIMIT 1
    ) rm ON true
    WHERE s.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    -- E02: conserva todas las filas válidas; si el origen repite una fila se enlaza a todas
    -- las filas core equivalentes, sin inventar una identidad que Access no traía.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'e02_conteo_flores', s.source_row_number, s.source_row_hash, 'core', 'flores',
           jsonb_build_object('flores_id', c.flores_id),
           CASE WHEN count(*) OVER (
                    PARTITION BY s.lote_id, s.fecha, s.cortina, s.hilera, s.planta,
                                 s.dni, s.n_flores, s.cuajo, s.yemas_abiertas,
                                 s.yemas_por_abrir, s.hora, s.item
                ) > 1 THEN 'deduplicada' ELSE 'directa' END,
           jsonb_build_object('grano_origen', 'planta-fecha-item', 'clave_core', 'surrogate')
    FROM stg.e02_flores s
    JOIN core.ev_flores c
      ON c.lote_id = s.lote_id
     AND c.fecha = s.fecha
     AND c.cortina = coalesce(s.cortina, 0)
     AND c.hilera = coalesce(s.hilera, 0)
     AND c.planta = coalesce(s.planta, 0)
     AND c.evaluador_id IS NOT DISTINCT FROM stg.fn_resolver_evaluador(s.dni)
     AND c.n_flores IS NOT DISTINCT FROM s.n_flores
     AND c.cuajo IS NOT DISTINCT FROM s.cuajo
     AND c.yemas_abiertas IS NOT DISTINCT FROM s.yemas_abiertas
     AND c.yemas_por_abrir IS NOT DISTINCT FROM s.yemas_por_abrir
     AND c.hora IS NOT DISTINCT FROM s.hora
     AND c.item IS NOT DISTINCT FROM s.item
    WHERE s.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    -- E03: item es parte de la clave natural validada; una fila que chocó con esa clave se
    -- encontrará después en la reconciliación como no representada y se conservará en qua.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'e03_conteo_estados', s.source_row_number, s.source_row_hash, 'core', 'estados',
           jsonb_build_object('estados_id', c.estados_id), 'directa',
           jsonb_build_object('grano_origen', 'planta-fecha-item')
    FROM stg.e03_estados s
    JOIN core.ev_estados c
      ON c.lote_id = s.lote_id
     AND c.fecha = s.fecha
     AND c.cortina = coalesce(s.cortina, 0)
     AND c.hilera = coalesce(s.hilera, 0)
     AND c.planta = coalesce(s.planta, 0)
     AND c.evaluador_id IS NOT DISTINCT FROM stg.fn_resolver_evaluador(s.dni)
     AND c.e1 = s.e1 AND c.e2 = s.e2 AND c.e3 = s.e3 AND c.e4 = s.e4 AND c.e5 = s.e5
     AND c.total_origen IS NOT DISTINCT FROM s.total_origen
     AND c.hora IS NOT DISTINCT FROM s.hora
     AND c.item = s.item
    WHERE s.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    -- E04: la fecha forma parte de la identidad de la captura.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'e04_brotes', s.source_row_number, s.source_row_hash, 'core', 'brotes',
           jsonb_build_object('brotes_id', c.brotes_id), 'directa',
           jsonb_build_object('grano_origen', 'planta-fecha-piso')
    FROM stg.e04_brotes s
    JOIN core.ev_brotes c
      ON c.lote_id = s.lote_id
     AND c.fecha = s.fecha
     AND c.piso = coalesce(s.piso, '(sin piso)')
     AND c.cortina = coalesce(s.cortina, 0)
     AND c.hilera = coalesce(s.hilera, 0)
     AND c.planta = coalesce(s.planta, 0)
     AND c.evaluador_id IS NOT DISTINCT FROM stg.fn_resolver_evaluador(s.dni)
     AND c.brotes = coalesce(s.brotes, 0)
     AND c.des1 IS NOT DISTINCT FROM s.des1
     AND c.des2 IS NOT DISTINCT FROM s.des2
     AND c.des3 IS NOT DISTINCT FROM s.des3
     AND c.hora IS NOT DISTINCT FROM s.hora
    WHERE s.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    -- E05_DiametrosBayas: nro_muestra se deriva en staging por grupo y queda incluido en el
    -- enlace, de modo que el orden estable queda auditable.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'e05_diametros_bayas', s.source_row_number, s.source_row_hash, 'core',
           'baya_medicion', jsonb_build_object('baya_medicion_id', c.baya_medicion_id),
           'derivada', jsonb_build_object('nro_muestra', s.nro_muestra,
                                          'regla', 'orden diámetro + source_row_number')
    FROM stg.e05_bayas s
    JOIN core.ev_baya_medicion c
      ON c.lote_id = s.lote_id
     AND c.fecha = s.fecha
     AND c.cortina = coalesce(s.cortina, 0)
     AND c.hilera = coalesce(s.hilera, 0)
     AND c.nro_muestra = s.nro_muestra
     AND c.diametro = round(s.diametro::numeric, 4)
    WHERE s.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    -- E05_Seguimiento: una fila física de Access se desancha en hasta 25 observaciones. Cada
    -- observación conserva source_row_number + numero_muestra; la cabecera conserva la misma
    -- clave idempotente para futuras cargas de la app.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'e05_seguimiento', s.source_row_number, s.source_row_hash, 'core',
           'evaluacion_baya', jsonb_build_object('evaluacion_baya_id', e.evaluacion_baya_id),
           'desancho', jsonb_build_object('numero_muestra', s.numero_muestra,
                                          'grano_origen', 'registro Access',
                                          'grano_logico', 'baya')
    FROM stg.e05_seguimiento s
    JOIN core.ev_evaluacion_baya e
      ON e.origen = 'access'
     AND e.idempotency_key = 'access:' || s.source_snapshot_id::text || ':'
                             || s.source_row_number::text
    WHERE s.source_snapshot_id = v_snapshot
      AND (s.estado_codigo IS NOT NULL OR s.diametro_mm > 0)
    ON CONFLICT DO NOTHING;

    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'e05_seguimiento', s.source_row_number, s.source_row_hash, 'core',
           'baya_observacion', jsonb_build_object('baya_observacion_id', o.baya_observacion_id),
           'desancho', jsonb_build_object('numero_muestra', s.numero_muestra,
                                          'diametro_mm', s.diametro_mm,
                                          'estado_codigo', s.estado_codigo)
    FROM stg.e05_seguimiento s
    JOIN core.ev_evaluacion_baya e
      ON e.origen = 'access'
     AND e.idempotency_key = 'access:' || s.source_snapshot_id::text || ':'
                             || s.source_row_number::text
    JOIN core.ev_baya_observacion o
      ON o.evaluacion_baya_id = e.evaluacion_baya_id
     AND o.numero_muestra = s.numero_muestra
     AND o.numero_medicion = 1
    WHERE s.source_snapshot_id = v_snapshot
      AND (s.estado_codigo IS NOT NULL OR s.diametro_mm > 0)
    ON CONFLICT DO NOTHING;
END;
$$;

COMMENT ON PROCEDURE raw.sp_registrar_lineage_fenologia_b03() IS
    'Registra el vínculo E01-E05 desde filas Access hasta core, incluyendo agregación de '
    'planta, deduplicación y desancho de E05_Seguimiento.';

CREATE OR REPLACE PROCEDURE raw.sp_registrar_filas_no_lineage_b03()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloque bigint;
BEGIN
    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
        v_run := nullif(current_setting('aquanqa.migracion_run_id', true), '')::bigint;
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'Reconciliación B03 bloqueada: faltan GUC de snapshot/run/bloque.';
    END;

    IF v_snapshot IS NULL OR v_run IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'Reconciliación B03 bloqueada: faltan GUC de snapshot/run/bloque.';
    END IF;

    -- Las filas que no llegan a ningún destino core se conservan completas en qua. Esto cubre
    -- claves incompletas, conflictos rechazados por una UNIQUE y conversiones no representadas
    -- por los cargadores heredados.
    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E01_Ramas', 'core.ev_evaluacion_ramas/core.ev_rama_medicion', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila E01 no quedó vinculada a ningún objeto core después de aplicar las reglas '
           'de cabecera/detalle; se conserva para reproceso.', to_jsonb(s)
    FROM stg.e01_ramas s
    WHERE s.source_snapshot_id = v_snapshot
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'e01_ramas'
            AND l.source_row_number = s.source_row_number
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'E01_Ramas'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E02_ConteoFlores', 'core.ev_flores', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila E02 no quedó representada en core; se conserva para reproceso.', to_jsonb(s)
    FROM stg.e02_flores s
    WHERE s.source_snapshot_id = v_snapshot
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'e02_conteo_flores'
            AND l.source_row_number = s.source_row_number
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'E02_ConteoFlores'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E03_ConteoEstados', 'core.ev_estados', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila E03 no quedó representada en core, normalmente por conflicto de clave; '
           'se conserva para reproceso.', to_jsonb(s)
    FROM stg.e03_estados s
    WHERE s.source_snapshot_id = v_snapshot
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'e03_conteo_estados'
            AND l.source_row_number = s.source_row_number
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'E03_ConteoEstados'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E04_Brotes', 'core.ev_brotes', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila E04 no quedó representada en core, normalmente por conflicto de clave; '
           'se conserva para reproceso.', to_jsonb(s)
    FROM stg.e04_brotes s
    WHERE s.source_snapshot_id = v_snapshot
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'e04_brotes'
            AND l.source_row_number = s.source_row_number
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'E04_Brotes'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E05_DiametrosBayas', 'core.ev_baya_medicion', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila E05_DiametrosBayas no quedó representada en core; se conserva para '
           'reproceso.', to_jsonb(s)
    FROM stg.e05_bayas s
    WHERE s.source_snapshot_id = v_snapshot
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'e05_diametros_bayas'
            AND l.source_row_number = s.source_row_number
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'E05_DiametrosBayas'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E05_Seguimiento', 'core.ev_evaluacion_baya/core.ev_baya_observacion',
           'FILA_NO_REPRESENTADA', 'MIGRACION-RECONCILIACION',
           'La combinación E05 (fila física + número de muestra) no quedó representada en '
           'core; se conserva para reproceso.', to_jsonb(s)
    FROM stg.e05_seguimiento s
    WHERE s.source_snapshot_id = v_snapshot
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'e05_seguimiento'
            AND l.source_row_number = s.source_row_number
            AND l.detalle->>'numero_muestra' = s.numero_muestra::text
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'E05_Seguimiento'
            AND q.fila->>'source_row_number' = s.source_row_number::text
            AND q.fila->>'numero_muestra' = s.numero_muestra::text
      );
END;
$$;

COMMENT ON PROCEDURE raw.sp_registrar_filas_no_lineage_b03() IS
    'Crea rechazos explícitos para filas fenológicas sin vínculo a core después de la carga.';

-- ============================================================================
-- B04 · Operación
-- ============================================================================

CREATE OR REPLACE PROCEDURE core.sp_cargar_operacion_b04()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloque bigint;
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'B04 bloqueado: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;

    IF to_regclass('stg.h00_cosecha') IS NULL
       OR to_regclass('stg.h01_cosecha') IS NULL
       OR to_regclass('stg.h02_packing') IS NULL
       OR to_regclass('stg.h05_clima') IS NULL THEN
        RAISE EXCEPTION
            'B04 incompleto: materialice H00, H01, H02 y H05 antes de cargar core.';
    END IF;

    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
        v_run := nullif(current_setting('aquanqa.migracion_run_id', true), '')::bigint;
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'B04 bloqueado: faltan GUC de snapshot/run/bloque.';
    END;

    IF v_snapshot IS NULL OR v_run IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'B04 bloqueado: faltan GUC de snapshot/run/bloque.';
    END IF;

    -- Forecast es posterior y no se reconstruye implícitamente al repetir B04. Si ya existe,
    -- un nuevo snapshot/modelo debe publicar una nueva versión en vez de borrar operación.
    IF coalesce(current_setting('aquanqa.allow_full_core', true), '') <> 'on'
       AND (EXISTS (SELECT 1 FROM core.op_forecast_campania)
            OR EXISTS (SELECT 1 FROM core.op_forecast_semanal)) THEN
        RAISE EXCEPTION
            'B04 bloqueado: ya existen proyecciones posteriores; no se reconstruye operación sobre dependencias publicadas.';
    END IF;

    DELETE FROM qua.rechazos
    WHERE bloque_ejecucion_id = v_bloque
      AND tabla_origen IN ('H00_VolumenCampo', 'H01_ProdHistorica',
                           'H02_BDElifab', 'H05_Clima');

    CALL core.sp_cargar_cosecha();
    CALL core.sp_cargar_clima();
    CALL core.sp_cargar_packing();
END;
$$;

COMMENT ON PROCEDURE core.sp_cargar_operacion_b04() IS
    'Carga H00/H01 como cosecha reconciliada, H02 como packing y H05 como clima. No toca '
    'fenología ni forecast, y solo puede repetirse antes de publicar bloques posteriores.';

CREATE OR REPLACE PROCEDURE raw.sp_registrar_lineage_operacion_b04()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloque bigint;
    v_modelo text := raw.fn_modelo_version_vigente();
BEGIN
    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
        v_run := nullif(current_setting('aquanqa.migracion_run_id', true), '')::bigint;
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'Linaje B04 bloqueado: faltan GUC de snapshot/run/bloque.';
    END;

    IF v_snapshot IS NULL OR v_run IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'Linaje B04 bloqueado: faltan GUC de snapshot/run/bloque.';
    END IF;

    -- H00 y H01 se unifican en core.op_cosecha por lote + fecha + campaña. Por eso varias filas
    -- de ambas fuentes pueden apuntar a la misma fila core y la diferencia queda en qua.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'h00_volumen_campo', s.source_row_number, s.source_row_hash, 'core',
           'cosecha', jsonb_build_object('cosecha_id', c.cosecha_id), 'agregada',
           jsonb_build_object('fuente', 'H00', 'grano_core', 'lote-fecha-campania')
    FROM stg.h00_cosecha s
    JOIN core.t_campania ca ON ca.codigo = s.campania
    JOIN core.op_cosecha c
      ON c.lote_id = s.lote_id
     AND c.fecha = s.fecha
     AND c.campania_id = ca.campania_id
    WHERE s.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'h01_prod_historica', s.source_row_number, s.source_row_hash, 'core',
           'cosecha', jsonb_build_object('cosecha_id', c.cosecha_id), 'agregada',
           jsonb_build_object('fuente', 'H01', 'grano_core', 'lote-fecha-campania')
    FROM stg.h01_cosecha s
    JOIN core.t_campania ca ON ca.codigo = s.campania
    JOIN core.op_cosecha c
      ON c.lote_id = s.lote_id
     AND c.fecha = s.fecha
     AND c.campania_id = ca.campania_id
    WHERE s.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    -- H02 no tiene un lote de campo confiable. Se enlaza al módulo y al resto de atributos
    -- normalizados; si hay filas idénticas se conserva la relación 1:N sin inventar una PK de
    -- negocio que Access no proporciona.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    WITH normalizada AS (
        SELECT p.*,
               row_number() OVER (ORDER BY p.source_row_number) AS orden_carga,
               m.modulo_id AS modulo_id_resuelto,
               pe.empresa_id AS empresa_id_resuelto,
               va.variedad_id AS variedad_id_resuelto,
               ca.calibre_id AS calibre_id_resuelto
        FROM stg.h02_packing p
        LEFT JOIN LATERAL (
            SELECT mo.modulo_id
            FROM core.m_modulo mo
            WHERE mo.codigo = p.modulo
            ORDER BY mo.modulo_id
            LIMIT 1
        ) m ON true
        LEFT JOIN core.m_productor_equivalencia pe
          ON pe.productor_norm = stg.fn_norm_texto(p.productor)
        LEFT JOIN core.m_variedad_alias va
          ON va.alias_norm = stg.fn_norm_texto(p.variedad)
        LEFT JOIN core.m_calibre ca
          ON stg.fn_norm_texto(ca.etiqueta) = stg.fn_norm_texto(p.calibre)
        WHERE p.fecha_proceso IS NOT NULL
    ), destino AS (
        SELECT c.*, row_number() OVER (ORDER BY c.packing_id) AS orden_carga
        FROM core.op_packing c
    )
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'h02_bd_elifab', s.source_row_number, s.source_row_hash, 'core', 'packing',
           jsonb_build_object('packing_id', c.packing_id), 'directa',
           jsonb_build_object('grano_origen', 'registro de packing',
                              'modulo_sin_fundo', s.modulo_id_resuelto IS NULL)
    FROM normalizada s
    JOIN destino c ON c.orden_carga = s.orden_carga
    WHERE s.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;

    -- H05: el timestamp es la identidad de la medición; los duplicados exactos apuntan al
    -- mismo registro core y quedan explicados por el rechazo agregado.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'h05_clima', s.source_row_number, s.source_row_hash, 'core', 'clima',
           jsonb_build_object('fecha_hora', c.fecha_hora), 'deduplicada',
           jsonb_build_object('regla', 'timestamp')
    FROM stg.h05_clima s
    JOIN core.op_clima c ON c.fecha_hora = s.fecha_hora
    WHERE s.source_snapshot_id = v_snapshot
    ON CONFLICT DO NOTHING;
END;
$$;

COMMENT ON PROCEDURE raw.sp_registrar_lineage_operacion_b04() IS
    'Registra el linaje de H00/H01/H02/H05 hasta cosecha, packing y clima, incluyendo '
    'unificación, deduplicación y limitación de identidad de módulo en H02.';

CREATE OR REPLACE PROCEDURE raw.sp_registrar_filas_no_lineage_b04()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_bloque bigint;
BEGIN
    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'Reconciliación B04 bloqueada: faltan GUC de snapshot/bloque.';
    END;

    IF v_snapshot IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'Reconciliación B04 bloqueada: faltan GUC de snapshot/bloque.';
    END IF;

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'H00_VolumenCampo', 'core.op_cosecha', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila H00 no quedó representada en la cosecha unificada; se conserva para '
           'reproceso.', to_jsonb(s)
    FROM stg.h00_cosecha s
    WHERE s.source_snapshot_id = v_snapshot
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'h00_volumen_campo'
            AND l.source_row_number = s.source_row_number
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'H00_VolumenCampo'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'H01_ProdHistorica', 'core.op_cosecha', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila H01 no quedó representada en la cosecha unificada; se conserva para '
           'reproceso.', to_jsonb(s)
    FROM stg.h01_cosecha s
    WHERE s.source_snapshot_id = v_snapshot
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'h01_prod_historica'
            AND l.source_row_number = s.source_row_number
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'H01_ProdHistorica'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'H02_BDElifab', 'core.op_packing', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila H02 no quedó representada en packing; se conserva para reproceso.', to_jsonb(s)
    FROM stg.h02_packing s
    WHERE s.source_snapshot_id = v_snapshot
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'h02_bd_elifab'
            AND l.source_row_number = s.source_row_number
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'H02_BDElifab'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'H05_Clima', 'core.op_clima', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila H05 no quedó representada en clima, normalmente por timestamp nulo; se '
           'conserva para reproceso.', to_jsonb(s)
    FROM stg.h05_clima s
    WHERE s.source_snapshot_id = v_snapshot
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'h05_clima'
            AND l.source_row_number = s.source_row_number
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'H05_Clima'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );
END;
$$;

COMMENT ON PROCEDURE raw.sp_registrar_filas_no_lineage_b04() IS
    'Crea rechazos explícitos para filas de operación sin vínculo a core después de la carga.';

-- ============================================================================
-- B05 · Pronóstico
-- ============================================================================

CREATE OR REPLACE PROCEDURE core.sp_cargar_pronostico_b05()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloque bigint;
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'B05 bloqueado: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;

    IF to_regclass('stg.r08_forecast') IS NULL
       OR to_regclass('stg.r09_forecast') IS NULL THEN
        RAISE EXCEPTION
            'B05 incompleto: materialice R08 y R09 antes de cargar core.';
    END IF;

    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
        v_run := nullif(current_setting('aquanqa.migracion_run_id', true), '')::bigint;
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'B05 bloqueado: faltan GUC de snapshot/run/bloque.';
    END;

    IF v_snapshot IS NULL OR v_run IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'B05 bloqueado: faltan GUC de snapshot/run/bloque.';
    END IF;

    DELETE FROM qua.rechazos
    WHERE bloque_ejecucion_id = v_bloque
      AND tabla_origen IN ('R08_Forecast_Campaña', 'R09_Forecast_Semanal');

    CALL core.sp_cargar_forecast();
END;
$$;

COMMENT ON PROCEDURE core.sp_cargar_pronostico_b05() IS
    'Carga únicamente R08 y R09 vigentes como forecast versionado. No integra los históricos '
    'R08/R09 _24/_25 hasta aprobar su regla de consolidación.';

CREATE OR REPLACE PROCEDURE raw.sp_registrar_lineage_pronostico_b05()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_run bigint;
    v_bloque bigint;
    v_modelo text := raw.fn_modelo_version_vigente();
BEGIN
    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
        v_run := nullif(current_setting('aquanqa.migracion_run_id', true), '')::bigint;
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'Linaje B05 bloqueado: faltan GUC de snapshot/run/bloque.';
    END;

    IF v_snapshot IS NULL OR v_run IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'Linaje B05 bloqueado: faltan GUC de snapshot/run/bloque.';
    END IF;

    -- Versiones: cada fila fuente que trae código queda vinculada al catálogo de versiones.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'r08_forecast_campania', s.source_row_number, s.source_row_hash, 'core',
           'version_forecast', jsonb_build_object('version_id', v.version_id), 'derivada',
           jsonb_build_object('sistema', 'campania', 'codigo', s.version)
    FROM stg.r08_forecast s
    JOIN core.m_version_forecast v
      ON v.sistema = 'campania' AND v.codigo = s.version
    WHERE s.source_snapshot_id = v_snapshot
      AND s.version IS NOT NULL AND s.version <> ''
    ON CONFLICT DO NOTHING;

    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'r09_forecast_semanal', s.source_row_number, s.source_row_hash, 'core',
           'version_forecast', jsonb_build_object('version_id', v.version_id), 'derivada',
           jsonb_build_object('sistema', 'semanal', 'codigo', s.version)
    FROM stg.r09_forecast s
    JOIN core.m_version_forecast v
      ON v.sistema = 'semanal' AND v.codigo = s.version
    WHERE s.source_snapshot_id = v_snapshot
      AND s.version IS NOT NULL AND s.version <> ''
    ON CONFLICT DO NOTHING;

    -- Las cargas de hechos ordenan por source_row_number. El pairing ordinal evita un join
    -- de 20 columnas y mantiene una correspondencia reproducible aun cuando el origen no trae
    -- clave primaria funcional.
    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    WITH fuente AS (
        SELECT s.*, row_number() OVER (ORDER BY s.source_row_number) AS orden_carga
        FROM stg.r08_forecast s
        WHERE s.source_snapshot_id = v_snapshot
          AND s.version IS NOT NULL AND s.version <> ''
    ), destino AS (
        SELECT c.*, row_number() OVER (ORDER BY c.forecast_campania_id) AS orden_carga
        FROM core.op_forecast_campania c
    )
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'r08_forecast_campania', s.source_row_number, s.source_row_hash, 'core',
           'forecast_campania', jsonb_build_object('forecast_campania_id', c.forecast_campania_id),
           'directa', jsonb_build_object('orden_tecnico', s.orden_carga)
    FROM fuente s
    JOIN destino c ON c.orden_carga = s.orden_carga
    ON CONFLICT DO NOTHING;

    INSERT INTO raw.migracion_lineage_core (
        modelo_version, migracion_run_id, bloque_ejecucion_id, source_snapshot_id,
        source_table, source_row_number, source_row_hash, destino_schema, destino_tabla,
        destino_pk, tipo, detalle)
    WITH fuente AS (
        SELECT s.*, row_number() OVER (ORDER BY s.source_row_number) AS orden_carga
        FROM stg.r09_forecast s
        WHERE s.source_snapshot_id = v_snapshot
          AND s.version IS NOT NULL AND s.version <> ''
    ), destino AS (
        SELECT c.*, row_number() OVER (ORDER BY c.forecast_semanal_id) AS orden_carga
        FROM core.op_forecast_semanal c
    )
    SELECT v_modelo, v_run, v_bloque, v_snapshot,
           'r09_forecast_semanal', s.source_row_number, s.source_row_hash, 'core',
           'forecast_semanal', jsonb_build_object('forecast_semanal_id', c.forecast_semanal_id),
           'directa', jsonb_build_object('orden_tecnico', s.orden_carga)
    FROM fuente s
    JOIN destino c ON c.orden_carga = s.orden_carga
    ON CONFLICT DO NOTHING;
END;
$$;

COMMENT ON PROCEDURE raw.sp_registrar_lineage_pronostico_b05() IS
    'Registra R08/R09 hasta las versiones y hechos forecast; el pairing técnico usa el orden '
    'estable del snapshot y de la carga.';

CREATE OR REPLACE PROCEDURE raw.sp_registrar_filas_no_lineage_b05()
LANGUAGE plpgsql
AS $$
DECLARE
    v_snapshot bigint;
    v_bloque bigint;
BEGIN
    BEGIN
        v_snapshot := nullif(current_setting('aquanqa.source_snapshot_id', true), '')::bigint;
        v_bloque := nullif(current_setting('aquanqa.bloque_ejecucion_id', true), '')::bigint;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'Reconciliación B05 bloqueada: faltan GUC de snapshot/bloque.';
    END;

    IF v_snapshot IS NULL OR v_bloque IS NULL THEN
        RAISE EXCEPTION 'Reconciliación B05 bloqueada: faltan GUC de snapshot/bloque.';
    END IF;

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'R08_Forecast_Campaña', 'core.op_forecast_campania', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila R08 con versión no quedó representada en forecast; se conserva para '
           'reproceso.', to_jsonb(s)
    FROM stg.r08_forecast s
    WHERE s.source_snapshot_id = v_snapshot
      AND s.version IS NOT NULL AND s.version <> ''
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'r08_forecast_campania'
            AND l.source_row_number = s.source_row_number
            AND l.destino_tabla = 'forecast_campania'
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'R08_Forecast_Campaña'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'R09_Forecast_Semanal', 'core.op_forecast_semanal', 'FILA_NO_REPRESENTADA',
           'MIGRACION-RECONCILIACION',
           'La fila R09 con versión no quedó representada en forecast; se conserva para '
           'reproceso.', to_jsonb(s)
    FROM stg.r09_forecast s
    WHERE s.source_snapshot_id = v_snapshot
      AND s.version IS NOT NULL AND s.version <> ''
      AND NOT EXISTS (
          SELECT 1 FROM raw.migracion_lineage_core l
          WHERE l.source_snapshot_id = v_snapshot
            AND l.source_table = 'r09_forecast_semanal'
            AND l.source_row_number = s.source_row_number
            AND l.destino_tabla = 'forecast_semanal'
      )
      AND NOT EXISTS (
          SELECT 1 FROM qua.rechazos q
          WHERE q.bloque_ejecucion_id = v_bloque
            AND q.tabla_origen = 'R09_Forecast_Semanal'
            AND q.fila->>'source_row_number' = s.source_row_number::text
      );
END;
$$;

COMMENT ON PROCEDURE raw.sp_registrar_filas_no_lineage_b05() IS
    'Crea rechazos explícitos para filas de forecast sin vínculo al hecho core.';
