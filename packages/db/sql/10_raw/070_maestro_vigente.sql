-- ============================================================================
-- 070 · raw · Orígenes que no están en Access
--
-- El maestro de lotes vigente y el tareo de personal viven en Excel, fuera de la base. Son
-- los dos orígenes que la auditoría no cubrió y de los que dependen, respectivamente, la
-- identidad de los lotes y el informe SEGUIMIENTO DE PERSONAL.
-- ============================================================================

-- ── Maestro de lotes vigente (M_Lotes.xlsx) ─────────────────────────────────
-- 879 lotes · 6 fundos físicos · 25 módulos (M01–M24) · 13 turnos (T00–T12).
-- Sustituye a raw.m_lotes como fuente de identidad (ADR-0003).
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
    'Maestro de lotes vigente, de M_Lotes.xlsx: 879 filas frente a las 860 de Access, con '
    'módulos nuevos M14-M24. Es la fuente de identidad de lote. Tras normalizar los códigos '
    'cubre el 100% de los (módulo, lote) del M_Lotes histórico y deja ~732 filas de hechos '
    'huérfanas de ~280.000 (N-3).';
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
