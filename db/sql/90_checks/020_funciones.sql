-- ============================================================================
-- 90_checks · 020 · Pruebas de las funciones de normalización
--
-- Las funciones de stg deciden la identidad de cada fila: si una cambia de comportamiento,
-- miles de hechos pueden acabar en cuarentena sin que nadie lo note hasta ver un tablero
-- vacío. Estas pruebas fallan ruidosamente en su lugar.
-- ============================================================================

DROP FUNCTION IF EXISTS qua.fn_probar_funciones();

CREATE FUNCTION qua.fn_probar_funciones()
RETURNS TABLE (funcion text, entrada text, esperado text, obtenido text, estado text)
LANGUAGE plpgsql
AS $$
DECLARE
    caso record;
BEGIN
    FOR caso IN
        SELECT * FROM (VALUES
            -- fn_norm_lote · el origen escribe el mismo lote de varias formas (N-3)
            ('fn_norm_lote', 'L11B',       'L011B'),
            ('fn_norm_lote', '11B',        'L011B'),
            ('fn_norm_lote', 'l011b',      'L011B'),
            ('fn_norm_lote', 'L001',       'L001'),
            ('fn_norm_lote', '1',          'L001'),
            ('fn_norm_lote', 'L000',       'L000'),
            ('fn_norm_lote', '  L25b  ',   'L025B'),
            ('fn_norm_lote', '',           NULL),
            ('fn_norm_lote', NULL,         NULL),

            -- fn_norm_modulo · cuatro grafías conviven entre el maestro y H02 (N-2)
            ('fn_norm_modulo', 'M02',       'M02'),
            ('fn_norm_modulo', '2',         'M02'),
            ('fn_norm_modulo', 'Módulo 02', 'M02'),
            ('fn_norm_modulo', 'Modulo 2',  'M02'),
            ('fn_norm_modulo', '10b',       'M10B'),
            ('fn_norm_modulo', 'M10A',      'M10A'),
            ('fn_norm_modulo', ' m10a ',    'M10A'),
            ('fn_norm_modulo', '15',        'M15'),
            ('fn_norm_modulo', NULL,        NULL),

            -- fn_norm_turno · turno de riego
            ('fn_norm_turno', 'T01',  'T01'),
            ('fn_norm_turno', '1',    'T01'),
            ('fn_norm_turno', 'T00',  'T00'),
            ('fn_norm_turno', '',     NULL),

            -- fn_norm_turno_packing · dominio distinto, mismo nombre de columna (N-2)
            ('fn_norm_turno_packing', 'DÍA',   'DIA'),
            ('fn_norm_turno_packing', 'Noche', 'NOCHE'),
            ('fn_norm_turno_packing', 'NOCHE', 'NOCHE'),
            ('fn_norm_turno_packing', 'T01',   NULL),

            -- fn_norm_texto · comparar vocabularios con y sin acento
            ('fn_norm_texto', 'Aqu Anqa II - Ampliación', 'AQU ANQA II - AMPLIACION'),
            ('fn_norm_texto', 'aqu  anqa   ii',           'AQU ANQA II'),

            -- fn_semana · H02 escribe 'Sem 33'
            ('fn_semana', 'Sem 33', '33'),
            ('fn_semana', '7',      '7'),

            -- fn_mes_abrev · el origen usa Set por setiembre
            ('fn_mes_abrev', 'Set', '9'),
            ('fn_mes_abrev', 'Sep', '9'),
            ('fn_mes_abrev', 'Ene', '1'),
            ('fn_mes_abrev', 'Dic', '12'),

            -- fn_calibre_mm · milímetros solo cuando el valor es un calibre (H-10)
            ('fn_calibre_mm', '12 mm',    '12'),
            ('fn_calibre_mm', '26 mm+',   '26'),
            ('fn_calibre_mm', 'DESCARTE', NULL),
            ('fn_calibre_mm', '-',        NULL),

            -- fn_a_fecha · 1899-12-30 es la fecha cero de Access: es una hora, no una fecha
            ('fn_a_fecha', '2026-02-26 00:00:00', '2026-02-26'),
            ('fn_a_fecha', '1899-12-30 07:52:39', NULL),
            ('fn_a_fecha', 'no es fecha',         NULL),

            ('fn_a_hora', '1899-12-30 07:52:39', '07:52:39'),

            -- fn_a_fecha_dmy · M_Evaluadores guarda las fechas como texto d/mm/aaaa
            ('fn_a_fecha_dmy', '5/08/1977',  '1977-08-05'),
            ('fn_a_fecha_dmy', '17/02/1983', '1983-02-17'),
            ('fn_a_fecha_dmy', '',           NULL),

            -- Conversión tolerante: la basura da NULL, no un error
            ('fn_a_entero', '55.0',  '55'),
            ('fn_a_entero', 'abc',   NULL),
            ('fn_a_numero', '12,5',  NULL)
        ) AS t(fn, entrada, esperado)
    LOOP
        funcion  := caso.fn;
        entrada  := coalesce(caso.entrada, '(null)');
        esperado := coalesce(caso.esperado, '(null)');
        EXECUTE format('SELECT stg.%I(%L)::text', caso.fn, caso.entrada) INTO obtenido;
        obtenido := coalesce(obtenido, '(null)');
        estado   := CASE WHEN obtenido = esperado THEN 'ok' ELSE 'FALLA' END;
        RETURN NEXT;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION qua.fn_probar_funciones() IS
    'Casos de prueba de las funciones de normalización, tomados de valores reales del origen.';
