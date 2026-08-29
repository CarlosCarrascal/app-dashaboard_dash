-- ============================================================================
-- 070 · raw · Orígenes externos de contraste (no están en Access)
--
-- M_Lotes.xlsx y el tareo viven en Excel, fuera de Access. El primero se conserva como
-- contraste del maestro primario de Access; el segundo es un insumo externo de personal.
-- ============================================================================

-- ── Contraste externo de lotes (M_Lotes.xlsx) ───────────────────────────────
-- 879 lotes · 6 fundos físicos · 25 módulos (M01–M24) · 13 turnos (T00–T12).
-- No sustituye a raw.m_lotes; se compara contra él según ADR-0012.
CREATE TABLE IF NOT EXISTS raw.m_lotes_maestro (
    fundo          text,
    fundo_ppto     text,
    variedad       text,
    modulo         text,
    turno          text,
    lote           text,
    area           text,
    n_plantas      text,
    fecha_siembra  text,
    maceta         text,
    tipo_fibra     text,
    key_map        text,
    fundo_pptom5   text
);

COMMENT ON TABLE raw.m_lotes_maestro IS
    'Fuente externa de contraste, de M_Lotes.xlsx: 879 filas frente a las 882 del Access '
    'actual. Sus claves están contenidas en el Access actual; no sustituye al maestro primario '
    'raw.m_lotes (ADR-0012).';
COMMENT ON COLUMN raw.m_lotes_maestro.fundo IS
    'Fundo FÍSICO: Aqu Anqa 1 a Aqu Anqa 6. Es la nomenclatura que sustituye al vocabulario '
    'comercial antiguo (Ampliacion, Vivadis, Sta.Teresa).';
COMMENT ON COLUMN raw.m_lotes_maestro.fundo_ppto IS
    'EMPRESA: Aqu Anqa (89 lotes) / Aqu Anqa II (790). Junto con módulo y lote forma la clave '
    'de negocio del lote, porque (módulo, lote) por sí solo no identifica: hay 9 pares '
    'compartidos por las dos empresas y los módulos M01-M04 pertenecen a ambas (N-4).';
COMMENT ON COLUMN raw.m_lotes_maestro.fundo_pptom5 IS
    'Alias operativo o comercial. NO identifica el fundo: Aqu Anqa II - Kawsay Allpa '
    'corresponde a Aqu Anqa 3 en 211 lotes y a Aqu Anqa 5 en 44 (N-4). Solo sirve para '
    'reconocer nombres de origen.';
COMMENT ON COLUMN raw.m_lotes_maestro.variedad IS
    'Una sola variedad, Sekoya pop, en las 879 filas. La variedad real de cada cosecha está '
    'en los hechos (N-6).';

-- ── Tareo de personal (Query Tareo 2026.xlsx) ───────────────────────────────
-- Origen del informe SEGUIMIENTO DE PERSONAL. Estructura provisional: se ajustará cuando el
-- archivo esté disponible (hoy vive en una biblioteca SharePoint ajena a este equipo).
CREATE TABLE IF NOT EXISTS raw.tareo (
    documento      text,
    nombre         text,
    fecha          text,
    horas          text,
    labor          text,
    fundo          text,
    modulo         text,
    lote           text,
    origen_fila    text
);

COMMENT ON TABLE raw.tareo IS
    'Tareo de personal, de Query Tareo 2026.xlsx. Aporta las horas-hombre por documento y '
    'fecha que el informe SEGUIMIENTO DE PERSONAL cruza contra las evaluaciones para calcular '
    'Flores por Hora, Frutos por Hora y Jornadas Evaluador (B-5). Sin este origen, ese '
    'informe no puede migrar y sigue dependiendo de un Excel en el equipo de un usuario '
    '(B-1). Estructura provisional hasta poder inspeccionar el archivo.';
COMMENT ON COLUMN raw.tareo.documento IS
    'DNI. Es la única vía de enlace con las evaluaciones y con M_Evaluadores (H-09).';
COMMENT ON COLUMN raw.tareo.origen_fila IS
    'Número de fila del Excel, para poder rastrear un dato hasta su celda.';
