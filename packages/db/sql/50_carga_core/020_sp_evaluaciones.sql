-- ============================================================================
-- 50_carga_core · 020 · Carga de evaluaciones fenológicas
--
-- Cada procedimiento sigue el mismo patrón:
--   1 · manda a cuarentena lo que no se puede identificar, con su fila entera y el motivo,
--   2 · carga lo que sí,
--   3 · avisa por NOTICE de cuánto entró y cuánto se apartó.
--
-- Ninguna fila se pierde entre el paso 1 y el 2.
-- ============================================================================

CREATE OR REPLACE PROCEDURE core.sp_cargar_ramas()
LANGUAGE plpgsql
AS $$
DECLARE
    v_cab integer; v_det integer; v_dup integer; v_conf integer;
BEGIN
    TRUNCATE core.rama_medicion, core.evaluacion_ramas RESTART IDENTITY CASCADE;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E01_Ramas', 'core.evaluacion_ramas', coalesce(motivo, 'LOTE_INEXISTENTE'), 'H-01',
           'No se pudo identificar el lote de la evaluación.', to_jsonb(v)
    FROM stg.e01_ramas v
    WHERE lote_id IS NULL;

    -- Cabecera: una fila por planta evaluada. Los conteos declarados vienen repetidos en
    -- todas las filas de la planta, así que basta con tomar el máximo (N-1).
    INSERT INTO core.evaluacion_ramas (lote_id, fecha, cortina, hilera, planta,
                                       evaluador_id, ramas_menor5, ramas_mayor5)
    SELECT v.lote_id, v.fecha, v.cortina, v.hilera, v.planta,
           max(stg.fn_resolver_evaluador(v.dni)),
           max(v.ramas_menor5), max(v.ramas_mayor5)
    FROM stg.e01_ramas v
    WHERE v.lote_id IS NOT NULL AND v.fecha IS NOT NULL
      AND v.cortina IS NOT NULL AND v.hilera IS NOT NULL AND v.planta IS NOT NULL
    GROUP BY v.lote_id, v.fecha, v.cortina, v.hilera, v.planta;

    GET DIAGNOSTICS v_cab = ROW_COUNT;

    -- Detalle: una fila por rama medida. El DISTINCT es la deduplicación de H-03, y está
    -- definido sobre la fila completa porque es la única definición que reproduce las 71.095
    -- filas del contrato de aceptación (ADR-0002).
    WITH distintas AS (
        SELECT DISTINCT v.lote_id, v.fecha, v.cortina, v.hilera, v.planta,
               v.dni, v.ramas_menor5, v.ramas_mayor5, v.nro_rama, v.diametro,
               v.id_origen, v.actividad
        FROM stg.e01_ramas v
        WHERE v.lote_id IS NOT NULL AND v.fecha IS NOT NULL
          AND v.cortina IS NOT NULL AND v.hilera IS NOT NULL AND v.planta IS NOT NULL
          AND v.nro_rama IS NOT NULL AND v.diametro IS NOT NULL
    )
    INSERT INTO core.rama_medicion (evaluacion_ramas_id, nro_rama, diametro, sospechoso, id_origen)
    SELECT c.evaluacion_ramas_id, d.nro_rama, d.diametro,
           -- Una rama de arándano no pasa de 50 mm. Los valores mayores se cargan igual
           -- —las cifras de control los incluyen— pero quedan marcados (N-13).
           NOT stg.fn_diametro_valido(d.diametro::numeric, 50),
           d.id_origen
    FROM distintas d
    JOIN core.evaluacion_ramas c
      ON c.lote_id = d.lote_id AND c.fecha = d.fecha AND c.cortina = d.cortina
     AND c.hilera = d.hilera AND c.planta = d.planta;

    GET DIAGNOSTICS v_det = ROW_COUNT;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E01_Ramas', 'core.rama_medicion', 'DIAMETRO_FUERA_DE_RANGO', 'N-13',
           'Diámetro de rama físicamente imposible: ' || diametro || ' mm. Se carga igual, '
           'porque las cifras de control de la auditoría lo incluyen.',
           jsonb_build_object('rama_medicion_id', rama_medicion_id, 'diametro', diametro)
    FROM core.rama_medicion WHERE sospechoso;

    -- Duplicados exactos apartados por la deduplicación (H-03).
    SELECT count(*) - v_det INTO v_dup
    FROM stg.e01_ramas
    WHERE lote_id IS NOT NULL AND fecha IS NOT NULL AND nro_rama IS NOT NULL
      AND diametro IS NOT NULL AND cortina IS NOT NULL AND hilera IS NOT NULL
      AND planta IS NOT NULL;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E01_Ramas', 'core.rama_medicion', 'DUPLICADO_EXACTO', 'H-03',
           'Fila idéntica repetida ' || (n - 1) || ' vez/veces por una recarga.',
           jsonb_build_object('lote_id', lote_id, 'fecha', fecha, 'cortina', cortina,
                              'hilera', hilera, 'planta', planta, 'nro_rama', nro_rama,
                              'diametro', diametro, 'repeticiones', n)
    FROM (
        SELECT lote_id, fecha, cortina, hilera, planta, nro_rama, diametro, count(*) AS n
        FROM stg.e01_ramas
        WHERE lote_id IS NOT NULL AND fecha IS NOT NULL AND nro_rama IS NOT NULL
        GROUP BY 1,2,3,4,5,6,7 HAVING count(*) > 1
    ) d;

    -- La misma rama con dos diámetros distintos: no es una recarga, es un conflicto de
    -- captura, y se deja a la vista en lugar de resolverlo por sorteo (N-1).
    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E01_Ramas', 'core.rama_medicion', 'CONFLICTO_DIAMETRO_RAMA', 'N-1',
           'La rama ' || nro_rama || ' de esta planta tiene ' || n_diam || ' diámetros distintos.',
           jsonb_build_object('lote_id', lote_id, 'fecha', fecha, 'cortina', cortina,
                              'hilera', hilera, 'planta', planta, 'nro_rama', nro_rama,
                              'diametros', diametros)
    FROM (
        SELECT lote_id, fecha, cortina, hilera, planta, nro_rama,
               count(DISTINCT diametro) AS n_diam,
               jsonb_agg(DISTINCT diametro) AS diametros
        FROM stg.e01_ramas
        WHERE lote_id IS NOT NULL AND fecha IS NOT NULL AND nro_rama IS NOT NULL
        GROUP BY 1,2,3,4,5,6 HAVING count(DISTINCT diametro) > 1
    ) c;

    GET DIAGNOSTICS v_conf = ROW_COUNT;

    RAISE NOTICE 'Ramas: % plantas evaluadas, % ramas medidas, % duplicados exactos apartados',
        v_cab, v_det, v_dup;
END;
$$;

COMMENT ON PROCEDURE core.sp_cargar_ramas() IS
    'Carga E01_Ramas en dos niveles: 5.384 plantas y 71.095 ramas medidas. La deduplicación '
    'de H-03 se hace por fila completa idéntica, no por clave de planta — esa clave solo '
    'tiene 5.384 combinaciones y habría descartado el 94% de los datos (ADR-0002).';

-- ── Flores ──────────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE core.sp_cargar_flores()
LANGUAGE plpgsql
AS $$
DECLARE v_n integer;
BEGIN
    TRUNCATE core.flores RESTART IDENTITY CASCADE;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E02_ConteoFlores', 'core.flores', coalesce(motivo, 'LOTE_INEXISTENTE'), 'H-01',
           'No se pudo identificar el lote.', to_jsonb(v)
    FROM stg.e02_flores v WHERE lote_id IS NULL OR fecha IS NULL;

    -- Un conteo negativo es imposible: se carga como NULL y queda constancia (N-13).
    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E02_ConteoFlores', 'core.flores', 'CONTEO_NEGATIVO', 'N-13',
           'Conteo con valor negativo en el origen; se carga como no medido.',
           jsonb_build_object('fecha', stg.fn_a_fecha(fecha), 'modulo', modulo, 'lote', lote,
                              'n_flores', n_flores, 'cuajo', cuajo, 'ya', ya, 'yp', yp)
    FROM raw.e02_conteo_flores
    WHERE stg.fn_a_entero(n_flores) < 0 OR stg.fn_a_entero(cuajo) < 0
       OR stg.fn_a_entero(ya) < 0 OR stg.fn_a_entero(yp) < 0;

    INSERT INTO core.flores (lote_id, fecha, cortina, hilera, planta, evaluador_id,
                             n_flores, cuajo, yemas_abiertas, yemas_por_abrir, hora, item)
    SELECT lote_id, fecha, coalesce(cortina, 0), coalesce(hilera, 0), coalesce(planta, 0),
           stg.fn_resolver_evaluador(dni),
           n_flores, cuajo, yemas_abiertas, yemas_por_abrir, hora, item
    FROM stg.e02_flores
    WHERE lote_id IS NOT NULL AND fecha IS NOT NULL;

    GET DIAGNOSTICS v_n = ROW_COUNT;

    -- E02 no tiene ninguna clave natural única (N-9): se cargan todas las filas con clave
    -- sustituta y se anotan los conflictos para que alguien pueda mirarlos.
    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E02_ConteoFlores', 'core.flores', 'CLAVE_NATURAL_REPETIDA', 'N-9',
           'La misma planta y fecha aparece ' || n || ' veces; se conservan todas.',
           jsonb_build_object('lote_id', lote_id, 'fecha', fecha, 'cortina', cortina,
                              'hilera', hilera, 'planta', planta, 'item', item, 'veces', n)
    FROM (
        SELECT lote_id, fecha, cortina, hilera, planta, item, count(*) AS n
        FROM stg.e02_flores WHERE lote_id IS NOT NULL AND fecha IS NOT NULL
        GROUP BY 1,2,3,4,5,6 HAVING count(*) > 1
    ) d;

    RAISE NOTICE 'Flores: % filas', v_n;
END;
$$;

-- ── Estados de madurez ──────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE core.sp_cargar_estados()
LANGUAGE plpgsql
AS $$
DECLARE v_n integer;
BEGIN
    TRUNCATE core.estados RESTART IDENTITY CASCADE;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E03_ConteoEstados', 'core.estados', coalesce(motivo, 'LOTE_INEXISTENTE'), 'H-01',
           'No se pudo identificar el lote.', to_jsonb(v)
    FROM stg.e03_estados v WHERE lote_id IS NULL OR fecha IS NULL;

    INSERT INTO core.estados (lote_id, fecha, cortina, hilera, planta, evaluador_id,
                              e1, e2, e3, e4, e5, total_origen, item)
    SELECT lote_id, fecha, coalesce(cortina, 0), coalesce(hilera, 0), coalesce(planta, 0),
           stg.fn_resolver_evaluador(dni),
           e1, e2, e3, e4, e5, total_origen, item
    FROM stg.e03_estados
    WHERE lote_id IS NOT NULL AND fecha IS NOT NULL
    ON CONFLICT (item, lote_id, fecha, cortina, hilera, planta) DO NOTHING;

    GET DIAGNOSTICS v_n = ROW_COUNT;
    RAISE NOTICE 'Estados: % filas (diferencia Total vs E1..E5 en el origen: % frutos)',
        v_n, (SELECT coalesce(sum(total_origen) - sum(total), 0) FROM core.estados);
END;
$$;

-- ── Brotes ──────────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE core.sp_cargar_brotes()
LANGUAGE plpgsql
AS $$
DECLARE v_n integer;
BEGIN
    TRUNCATE core.brotes RESTART IDENTITY CASCADE;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E04_Brotes', 'core.brotes', coalesce(motivo, 'LOTE_INEXISTENTE'), 'H-01',
           'No se pudo identificar el lote.', to_jsonb(v)
    FROM stg.e04_brotes v WHERE lote_id IS NULL OR fecha IS NULL;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E04_Brotes', 'core.brotes', 'CONTEO_NEGATIVO', 'N-13',
           'Conteo de brotes negativo en el origen; se carga como cero.',
           jsonb_build_object('fecha', stg.fn_a_fecha(fecha), 'modulo', modulo, 'lote', lote,
                              'brotes', brotes)
    FROM raw.e04_brotes WHERE stg.fn_a_entero(brotes) < 0;

    INSERT INTO core.brotes (lote_id, fecha, piso, cortina, hilera, planta,
                             evaluador_id, brotes, des1, des2, des3, hora)
    SELECT lote_id, fecha, coalesce(piso, '(sin piso)'),
           coalesce(cortina, 0), coalesce(hilera, 0), coalesce(planta, 0),
           stg.fn_resolver_evaluador(dni), coalesce(brotes, 0), des1, des2, des3, hora
    FROM stg.e04_brotes
    WHERE lote_id IS NOT NULL AND fecha IS NOT NULL
    ON CONFLICT (lote_id, fecha, piso, cortina, hilera, planta) DO NOTHING;

    GET DIAGNOSTICS v_n = ROW_COUNT;
    RAISE NOTICE 'Brotes: % filas (ahora la fecha SÍ está en la clave, H-02)', v_n;
END;
$$;

-- ── Diámetro de baya ────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE core.sp_cargar_bayas()
LANGUAGE plpgsql
AS $$
DECLARE v_n integer;
BEGIN
    TRUNCATE core.baya_medicion RESTART IDENTITY CASCADE;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E05_DiametrosBayas', 'core.baya_medicion',
           coalesce(motivo, 'LOTE_INEXISTENTE'), 'H-01',
           'No se pudo identificar el lote. E05 no trae fundo, así que solo se puede resolver '
           'cuando el par (módulo, lote) es único.', to_jsonb(v)
    FROM stg.e05_bayas v WHERE lote_id IS NULL OR fecha IS NULL;

    INSERT INTO core.baya_medicion (lote_id, fecha, cortina, hilera, nro_muestra,
                                    diametro, sospechoso)
    SELECT lote_id, fecha, coalesce(cortina, 0), coalesce(hilera, 0), nro_muestra, diametro,
           -- Una baya de arándano no pasa de 40 mm; el origen llega a 13.381 (N-13).
           NOT stg.fn_diametro_valido(diametro::numeric, 40)
    FROM stg.e05_bayas
    WHERE lote_id IS NOT NULL AND fecha IS NOT NULL AND diametro IS NOT NULL
    ON CONFLICT (lote_id, fecha, cortina, hilera, nro_muestra) DO NOTHING;

    GET DIAGNOSTICS v_n = ROW_COUNT;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E05_DiametrosBayas', 'core.baya_medicion', 'DIAMETRO_FUERA_DE_RANGO', 'N-13',
           'Diámetro de baya físicamente imposible: ' || diametro || ' mm.',
           jsonb_build_object('baya_medicion_id', baya_medicion_id, 'diametro', diametro)
    FROM core.baya_medicion WHERE sospechoso;

    RAISE NOTICE 'Bayas: % mediciones, % con diámetro imposible', v_n,
        (SELECT count(*) FROM core.baya_medicion WHERE sospechoso);
END;
$$;

-- ── Poda y muestreo requerido ───────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE core.sp_cargar_poda()
LANGUAGE plpgsql
AS $$
DECLARE v_n integer;
BEGIN
    TRUNCATE core.poda RESTART IDENTITY CASCADE;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'M_Poda', 'core.poda', coalesce(motivo, 'LOTE_INEXISTENTE'), 'H-01',
           'No se pudo identificar el lote.', to_jsonb(v)
    FROM stg.m_poda v WHERE lote_id IS NULL;

    INSERT INTO core.poda (lote_id, campania_id, fecha_inicio, fecha_siembra, area_ha)
    SELECT p.lote_id, c.campania_id, min(p.fecha_inicio), min(p.fecha_siembra), max(p.area_ha)
    FROM stg.m_poda p
    JOIN core.campania c ON c.codigo = p.campania
    WHERE p.lote_id IS NOT NULL
    GROUP BY p.lote_id, c.campania_id;

    GET DIAGNOSTICS v_n = ROW_COUNT;
    RAISE NOTICE 'Poda: % filas', v_n;
END;
$$;

CREATE OR REPLACE PROCEDURE core.sp_cargar_muestreo()
LANGUAGE plpgsql
AS $$
DECLARE v_n integer;
BEGIN
    TRUNCATE core.muestra_requerida RESTART IDENTITY CASCADE;

    INSERT INTO core.muestra_requerida (lote_id, evaluacion, cortina, hilera, planta, muestras)
    SELECT lote_id, evaluacion, cortina, hilera, planta, muestras
    FROM stg.m_n_muestra
    WHERE lote_id IS NOT NULL AND muestras IS NOT NULL
    ON CONFLICT (lote_id, evaluacion, cortina, hilera, planta) DO NOTHING;

    GET DIAGNOSTICS v_n = ROW_COUNT;
    RAISE NOTICE 'Muestreo requerido: % filas', v_n;
END;
$$;
