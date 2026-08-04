-- ============================================================================
-- 50_carga_core · 010 · Carga de maestros
--
-- Los maestros se reconstruyen enteros en cada ejecución (TRUNCATE + carga): son pequeños y
-- así la carga es idempotente sin necesidad de lógica de diferencias.
--
-- El diccionario de alias de fundo NO se escribe a mano: se deriva de los datos. Si mañana
-- aparece una grafía nueva, basta volver a ejecutar esto.
-- ============================================================================

CREATE OR REPLACE PROCEDURE core.sp_cargar_ubicacion()
LANGUAGE plpgsql
AS $$
DECLARE
    v_lotes bigint;
BEGIN
    -- El orden de borrado es el inverso al de las dependencias.
    TRUNCATE core.fundo_alias, core.lote, core.modulo, core.fundo, core.empresa,
             core.turno, core.variedad_alias, core.variedad RESTART IDENTITY CASCADE;

    ------------------------------------------------------------------ empresa
    INSERT INTO core.empresa (nombre)
    SELECT DISTINCT empresa FROM stg.maestro_lote WHERE empresa IS NOT NULL
    ORDER BY 1;

    -------------------------------------------------------------------- fundo
    INSERT INTO core.fundo (empresa_id, codigo, alias_operativo)
    SELECT e.empresa_id,
           m.fundo,
           -- Alias operativo más frecuente del fundo, solo como etiqueta legible.
           (SELECT mode() WITHIN GROUP (ORDER BY x.alias_operativo)
            FROM stg.maestro_lote x WHERE x.fundo = m.fundo)
    FROM (SELECT DISTINCT fundo, empresa FROM stg.maestro_lote WHERE fundo IS NOT NULL) m
    JOIN core.empresa e ON e.nombre = m.empresa
    ORDER BY m.fundo;

    ------------------------------------------------------------------- módulo
    INSERT INTO core.modulo (fundo_id, codigo)
    SELECT DISTINCT f.fundo_id, m.modulo
    FROM stg.maestro_lote m
    JOIN core.fundo f ON f.codigo = m.fundo
    WHERE m.modulo IS NOT NULL;

    -------------------------------------------------------------------- turno
    INSERT INTO core.turno (codigo)
    SELECT DISTINCT turno FROM stg.maestro_lote WHERE turno IS NOT NULL
    ORDER BY 1;

    ----------------------------------------------------------------- variedad
    -- Del maestro sale una sola variedad; las de verdad están en los hechos (N-6). Se leen
    -- de `raw` y no de `stg` porque este procedimiento corre ANTES de materializar el
    -- staging: la variedad no depende del lote, así que no hace falta esperar.
    INSERT INTO core.variedad (nombre)
    SELECT DISTINCT nombre FROM (
        SELECT initcap(btrim(variedad)) AS nombre FROM stg.maestro_lote WHERE variedad IS NOT NULL
        UNION
        SELECT initcap(btrim(variedad)) FROM raw.h00_volumen_campo WHERE variedad IS NOT NULL
        UNION
        SELECT initcap(btrim(variedad)) FROM raw.m_poda WHERE variedad IS NOT NULL
    ) v WHERE nombre <> '' ORDER BY 1;

    INSERT INTO core.variedad_alias (alias_norm, alias_original, variedad_id, origen)
    SELECT DISTINCT ON (stg.fn_norm_texto(a.nombre))
           stg.fn_norm_texto(a.nombre), a.nombre, v.variedad_id, a.origen
    FROM (
        SELECT btrim(variedad) AS nombre, 'maestro' AS origen FROM stg.maestro_lote
        UNION ALL SELECT btrim(variedad), 'h00' FROM raw.h00_volumen_campo
        UNION ALL SELECT btrim(variedad), 'm_poda' FROM raw.m_poda
    ) a
    JOIN core.variedad v ON stg.fn_norm_texto(v.nombre) = stg.fn_norm_texto(a.nombre)
    WHERE a.nombre IS NOT NULL AND a.nombre <> '';

    -- POP y SEKOYA POP son la misma variedad escrita de dos formas: se unifican apuntando
    -- el alias corto a la variedad completa.
    UPDATE core.variedad_alias a
       SET variedad_id = v.variedad_id
      FROM core.variedad v
     WHERE a.alias_norm = 'POP' AND v.nombre = 'Sekoya Pop';

    --------------------------------------------------------------------- lote
    INSERT INTO core.lote (modulo_id, codigo, turno_id, variedad_id, area_ha, n_plantas,
                           fecha_siembra, maceta, tipo_fibra, key_map, es_ficticio, origen)
    SELECT mo.modulo_id,
           m.lote,
           t.turno_id,
           va.variedad_id,
           coalesce(m.area_ha, 0),
           coalesce(m.n_plantas, 0),
           m.fecha_siembra,
           m.maceta,
           m.tipo_fibra,
           m.key_map,
           m.lote = 'L000',
           'maestro_vigente'
    FROM stg.maestro_lote m
    JOIN core.fundo f  ON f.codigo = m.fundo
    JOIN core.modulo mo ON mo.fundo_id = f.fundo_id AND mo.codigo = m.modulo
    JOIN core.turno t  ON t.codigo = m.turno
    LEFT JOIN core.variedad_alias va ON va.alias_norm = stg.fn_norm_texto(m.variedad);

    GET DIAGNOSTICS v_lotes = ROW_COUNT;

    ---------------------------------------------------------- alias de fundo
    -- 1 · Nombres de empresa (vocabulario B). No determinan el fundo físico.
    INSERT INTO core.fundo_alias (alias_norm, alias_original, tipo, empresa_id, fundo_id, ambiguo, origen, nota)
    SELECT stg.fn_norm_texto(e.nombre), e.nombre, 'empresa', e.empresa_id, NULL, true,
           'maestro.FundoPPto',
           'Nombre de empresa: identifica la razón social, no el fundo.'
    FROM core.empresa e;

    -- 2 · Fundos físicos (la nomenclatura vigente, que R08 y R09 ya usan).
    INSERT INTO core.fundo_alias (alias_norm, alias_original, tipo, empresa_id, fundo_id, ambiguo, origen, nota)
    SELECT stg.fn_norm_texto(f.codigo), f.codigo, 'fisico', f.empresa_id, f.fundo_id, false,
           'maestro.Fundo', NULL
    FROM core.fundo f
    ON CONFLICT (alias_norm) DO NOTHING;

    -- 3 · Alias operativos con prefijo (vocabulario C), y el mismo alias sin prefijo
    --     (vocabulario D, el que usan E01_Ramas y E04_Brotes). Un alias que aparece en más
    --     de un fundo se marca ambiguo y NO resuelve fundo: es el caso de Kawsay Allpa.
    INSERT INTO core.fundo_alias (alias_norm, alias_original, tipo, empresa_id, fundo_id, ambiguo, origen, nota)
    WITH alias_fundo AS (
        SELECT m.alias_operativo,
               count(DISTINCT f.fundo_id) AS n_fundos,
               min(f.fundo_id)            AS fundo_id,
               min(f.empresa_id)          AS empresa_id
        FROM stg.maestro_lote m
        JOIN core.fundo f ON f.codigo = m.fundo
        WHERE m.alias_operativo IS NOT NULL
        GROUP BY m.alias_operativo
    ), con_variantes AS (
        SELECT alias_operativo AS texto, 'operativo' AS tipo, n_fundos, fundo_id, empresa_id
        FROM alias_fundo
        UNION ALL
        -- Vocabulario D: el mismo nombre sin el prefijo de empresa.
        SELECT btrim(regexp_replace(alias_operativo, '^Aqu Anqa( II)?\s*-\s*', '')),
               'operativo', n_fundos, fundo_id, empresa_id
        FROM alias_fundo
        WHERE alias_operativo ~ '^Aqu Anqa( II)?\s*-\s*'
    )
    SELECT DISTINCT ON (stg.fn_norm_texto(texto))
           stg.fn_norm_texto(texto),
           texto,
           tipo,
           empresa_id,
           CASE WHEN n_fundos = 1 THEN fundo_id END,
           n_fundos > 1,
           'maestro.Fundo_pptom5',
           CASE WHEN n_fundos > 1
                THEN 'Alias presente en ' || n_fundos || ' fundos físicos: no puede resolverlos.'
           END
    FROM con_variantes
    WHERE texto IS NOT NULL AND texto <> ''
    ON CONFLICT (alias_norm) DO NOTHING;

    -- 4 · Vocabulario comercial antiguo (M_Lotes.Fundo). Resuelve empresa por su prefijo y
    --     nunca el fundo: se verificó que `Aqu Anqa II - Ampliacion` abarca tres fundos
    --     físicos distintos, así que la correspondencia que la auditoría daba por inferida
    --     (decisión D-4) es efectivamente irrecuperable.
    INSERT INTO core.fundo_alias (alias_norm, alias_original, tipo, empresa_id, fundo_id, ambiguo, origen, nota)
    SELECT DISTINCT ON (stg.fn_norm_texto(v.fundo))
           stg.fn_norm_texto(v.fundo),
           v.fundo,
           'comercial',
           e.empresa_id,
           NULL,
           true,
           'M_Lotes.Fundo (histórico)',
           'Vocabulario comercial retirado. Verificado que abarca varios fundos físicos: la '
           'identidad se resuelve por empresa, módulo y lote.'
    FROM (SELECT DISTINCT btrim(fundo) AS fundo FROM raw.m_lotes WHERE fundo IS NOT NULL) v
    JOIN core.empresa e
      ON e.nombre = CASE WHEN v.fundo LIKE 'Aqu Anqa II%' THEN 'Aqu Anqa II' ELSE 'Aqu Anqa' END
    ON CONFLICT (alias_norm) DO NOTHING;

    RAISE NOTICE 'Ubicación: % empresas, % fundos, % módulos, % lotes, % alias',
        (SELECT count(*) FROM core.empresa), (SELECT count(*) FROM core.fundo),
        (SELECT count(*) FROM core.modulo), v_lotes, (SELECT count(*) FROM core.fundo_alias);
END;
$$;

COMMENT ON PROCEDURE core.sp_cargar_ubicacion() IS
    'Reconstruye empresa, fundo, módulo, turno, variedad, lote y el diccionario de alias '
    'desde el maestro vigente. El diccionario se DERIVA de los datos, incluida la variante '
    'sin prefijo que usan E01_Ramas y E04_Brotes.';

-- ── Tiempo ──────────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE core.sp_cargar_tiempo()
LANGUAGE plpgsql
AS $$
BEGIN
    TRUNCATE core.semana_evaluacion;
    DELETE FROM core.calendario;
    DELETE FROM core.campania;

    ------------------------------------------------------------------ campaña
    -- Fechas derivadas del rango real observado, mientras Planeamiento no entregue el
    -- calendario oficial (decisión D-2, en core.config_decision).
    INSERT INTO core.campania (codigo, fecha_inicio, fecha_fin, origen_fechas)
    SELECT codigo, min(fecha), max(fecha),
           CASE WHEN core.fn_config('campania.origen_fechas') = 'declarado'
                THEN 'declarado' ELSE 'derivado' END
    FROM (
        SELECT campania AS codigo, fecha FROM stg.h00_cosecha
        UNION ALL SELECT campania, fecha FROM stg.h01_cosecha
        UNION ALL SELECT campania, fecha_inicio FROM stg.m_poda
        UNION ALL SELECT campania, fecha_cos FROM stg.r09_forecast
        UNION ALL SELECT campania, NULL::date FROM stg.r08_forecast
    ) t
    WHERE codigo IS NOT NULL AND codigo <> ''
    GROUP BY codigo
    ORDER BY codigo;

    --------------------------------------------------------------- calendario
    -- generate_series en lugar de copiar M_Time: así el calendario es continuo por
    -- construcción y no hereda huecos.
    INSERT INTO core.calendario (
        fecha, anio, mes, dia, trimestre, semana, dia_semana, mes_abrev,
        anio_mes, anio_semana, sem_ev_conteo, mes_sem, campanias_activas)
    SELECT d.fecha,
           extract(year  FROM d.fecha)::smallint,
           extract(month FROM d.fecha)::smallint,
           extract(day   FROM d.fecha)::smallint,
           extract(quarter FROM d.fecha)::smallint,   -- lo que a M_Time le faltaba (H-04 caso 5)
           extract(week  FROM d.fecha)::smallint,
           extract(isodow FROM d.fecha)::smallint,
           initcap(to_char(d.fecha, 'TMMon')),
           to_char(d.fecha, 'YYYY-MM'),
           to_char(d.fecha, 'IYYY') || '-' || to_char(d.fecha, 'IW'),
           t.sem_ev_conteo,
           t.mes_sem,
           -- Cuántas campañas hay activas ese día. Suele ser más de una: se solapan hasta
           -- 354 días, y por eso el calendario NO asigna campaña (N-11).
           (SELECT count(*) FROM core.campania c
             WHERE d.fecha BETWEEN c.fecha_inicio AND c.fecha_fin)::smallint
    FROM (
        SELECT generate_series(
                   (SELECT min(fecha) FROM stg.m_time),
                   (SELECT max(fecha) FROM stg.m_time),
                   INTERVAL '1 day')::date AS fecha
    ) d
    LEFT JOIN stg.m_time t ON t.fecha = d.fecha;

    ------------------------------------------------- semana de evaluación
    -- Grano SEMANAL explícito: es la corrección estructural de H-05. Unir una tabla semanal
    -- contra el calendario diario es lo que multiplicó por 54 las filas de 01_Flores_C2025.
    INSERT INTO core.semana_evaluacion (anio, sem_ev_conteo, fecha_inicio, fecha_fin, dias)
    SELECT anio, sem_ev_conteo, min(fecha), max(fecha), count(*)::smallint
    FROM core.calendario
    WHERE sem_ev_conteo IS NOT NULL
    GROUP BY anio, sem_ev_conteo;

    RAISE NOTICE 'Tiempo: % campañas, % días, % semanas de evaluación, % días con más de una campaña activa',
        (SELECT count(*) FROM core.campania),
        (SELECT count(*) FROM core.calendario),
        (SELECT count(*) FROM core.semana_evaluacion),
        (SELECT count(*) FROM core.calendario WHERE campanias_activas > 1);
END;
$$;

-- ── Evaluadores ─────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE core.sp_cargar_evaluadores()
LANGUAGE plpgsql
AS $$
DECLARE
    v_sin_maestro integer;
BEGIN
    DELETE FROM core.evaluador;

    INSERT INTO core.evaluador (dni, nombres, apellidos, codigo, zona, celular,
                                inicio_labores, nacimiento, activo, en_maestro)
    SELECT dni, nombres, apellidos, codigo, zona, celular,
           inicio_labores, nacimiento, activo, true
    FROM stg.m_evaluadores
    WHERE dni IS NOT NULL AND dni <> '';

    -- Los DNI que capturan datos pero no están en el maestro se crean igualmente: perder la
    -- evaluación sería peor que tener una ficha incompleta (H-09).
    INSERT INTO core.evaluador (dni, activo, en_maestro)
    SELECT DISTINCT dni, true, false
    FROM (
        SELECT dni FROM stg.e01_ramas
        UNION SELECT dni FROM stg.e02_flores
        UNION SELECT dni FROM stg.e03_estados
        UNION SELECT dni FROM stg.e04_brotes
    ) t
    WHERE dni IS NOT NULL AND dni <> ''
      AND NOT EXISTS (SELECT 1 FROM core.evaluador e WHERE e.dni = t.dni);

    GET DIAGNOSTICS v_sin_maestro = ROW_COUNT;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'M_Evaluadores', 'core.evaluador', 'EVALUADOR_SIN_MAESTRO', 'H-09',
           'DNI que aparece capturando evaluaciones y no está en el maestro de evaluadores.',
           jsonb_build_object('dni', dni)
    FROM core.evaluador WHERE NOT en_maestro;

    RAISE NOTICE 'Evaluadores: % en total, % sin ficha en el maestro',
        (SELECT count(*) FROM core.evaluador), v_sin_maestro;
END;
$$;
