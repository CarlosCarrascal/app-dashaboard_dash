-- ============================================================================
-- 10_raw · 080 · Riego y nutrición 2025 (fuente externa, no Access)
--
-- Origen: 4 libros Excel entregados por Riego/Operaciones el 2026-08-06 —
-- "AQ 1..4. Registros de riego y nutrición 2025.xlsx", hoja "BASE DATOS". Grano:
-- fecha × módulo local del archivo × turno, un registro por día de 2025.
--
-- Cada archivo es UN fundo físico completo (verificado por área, no por el número del
-- archivo — los 4 reinician su numeración de módulo desde 1, así que "módulo 1" del
-- archivo 1 y "módulo 1" del archivo 2 son módulos distintos):
--
--   archivo 1 → Aqu Anqa 1 (módulos locales 1-4  = M01-M04)
--   archivo 2 → Aqu Anqa 2 (módulos locales 1-5  = M01-M05)
--   archivo 3 → Aqu Anqa 3 (módulos locales 6-9  = M06-M09; 10 y 11 son casos
--               especiales, resueltos en stg.v_riego_diario, no aquí)
--   archivo 4 → Aqu Anqa 4 (módulos locales 12-15 = M12-M15)
--
-- Solo se cargan las columnas de RIEGO (hasta "l/planta" en el origen, columnas 2-19).
-- Las columnas 20-55 (kg de fertilizante aplicado, unidades de fertilizante, y la
-- concentración iónica de 9 fertilizantes) NO se cargan en esta pasada: son la
-- dimensión de nutrición, no de riego, y quedan fuera del alcance de este análisis.
-- No es una pérdida silenciosa — está documentado aquí y en el script de carga.
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw.riego_diario (
    archivo         smallint NOT NULL,     -- 1-4, el número del libro de origen
    anio            text,
    mes             text,
    semana_origen   text,                  -- [SEMANA] del origen: semana calendario simple
                                            -- (1-52/53), NO la semana ISO. No se usa para
                                            -- agregar — eso lo hace core.calendario.anio_semana
                                            -- a partir de la fecha, igual que el resto del modelo.
    fecha           text,
    modulo_local    text,                  -- número de módulo TAL COMO está en el archivo
    turno_local     text,                  -- 1-12, sin resolver contra core.turno todavía
    area_ha         text,
    agua_m3         text,
    lamina_mm       text,
    reposicion_pct  text,
    m3_ha           text,
    l_planta        text
);

COMMENT ON TABLE raw.riego_diario IS
    'Copia fiel de los 4 Excel de riego 2025 (hoja BASE DATOS, columnas 2-19). Un archivo '
    'por fundo físico completo — ver el mapeo en la cabecera de este script. Sin resolver '
    'ni tipar: eso ocurre en stg.v_riego_diario.';
COMMENT ON COLUMN raw.riego_diario.archivo IS
    '1=Aqu Anqa 1, 2=Aqu Anqa 2, 3=Aqu Anqa 3, 4=Aqu Anqa 4. No hay archivo para Aqu Anqa 5 '
    '(salvo el módulo 11, ver stg) ni para Aqu Anqa 6: no hay riego cargado para esos.';
COMMENT ON COLUMN raw.riego_diario.modulo_local IS
    'El número de módulo tal como aparece en el archivo de origen. NO es directamente '
    'core.modulo.codigo: cada archivo reinicia su numeración desde 1 o continúa la global '
    'según el fundo. La resolución completa, verificada por área, está en '
    'stg.mapa_modulo_riego.';
COMMENT ON COLUMN raw.riego_diario.lamina_mm IS
    '[LAMINA (mm)] — milímetros de agua aplicados en ese turno, ese día. Es la variable de '
    'riego que la base de Access nunca tuvo.';
