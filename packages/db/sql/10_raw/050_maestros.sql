-- ============================================================================
-- 050 · raw · Maestros del origen (M_*)
--
-- Nota importante: M_Lotes se carga por trazabilidad, NO como maestro vigente. El maestro
-- de referencia es data/entrada/M_Lotes.xlsx (879 lotes, 6 fundos), en 070_maestro_vigente.
-- ============================================================================

-- ── M_Lotes (histórico de Access) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.m_lotes (
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
    fundo_pptom5   text,
    moduloo        text,
    kk             text
);

COMMENT ON TABLE raw.m_lotes IS
    'M_Lotes — 860 filas. Era la tabla central del origen: 33 de las 40 consultas dependen '
    'de ella. Se carga solo por trazabilidad histórica; el maestro vigente es '
    'raw.m_lotes_maestro. Es también el epicentro de H-01: contiene tres de los cuatro '
    'vocabularios de fundo en tres columnas distintas, y ninguno coincide con el que usan '
    'E01_Ramas y E04_Brotes.';
COMMENT ON COLUMN raw.m_lotes.fundo IS
    '[Fundo] — vocabulario A, nombre comercial con ubicación: Aqu Anqa II - Ampliacion, '
    '- Vivadis, - Sta.Teresa, Aqu Anqa - ArenaAzul. El maestro vigente lo sustituye por '
    'fundos físicos numerados Aqu Anqa 1..6 (N-5).';
COMMENT ON COLUMN raw.m_lotes.fundo_ppto IS
    '[FundoPPto] — vocabulario B, agrupación presupuestal = empresa: Aqu Anqa / Aqu Anqa II.';
COMMENT ON COLUMN raw.m_lotes.fundo_pptom5 IS
    '[Fundo_pptom5] — vocabulario C, nombre quechua con prefijo de empresa.';
COMMENT ON COLUMN raw.m_lotes.turno IS
    '[Turno] — la fuente del turno para toda la base: solo M_Lotes, H01 y E05 lo traen de '
    'origen; el resto debe obtenerlo por join, y ese join es el que falla en H-01.';
COMMENT ON COLUMN raw.m_lotes.moduloo IS '[Moduloo] — typo que duplica [Modulo]. Se descarta.';
COMMENT ON COLUMN raw.m_lotes.kk IS
    '[kk] — prefijo de KeyMap hasta la letra L. Derivable, se descarta.';
COMMENT ON COLUMN raw.m_lotes.key_map IS
    '[KeyMap] — clave de ubicación en el mapa. 53 lotes la tienen nula, y de ahí que el '
    'cálculo de kk falle en silencio en la consulta 0106_RaFloYem.';

-- ── M_Time ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.m_time (
    fecha          text,
    sem            text,
    mes            text,
    anio           text,
    sev_conteo     text,
    aqii           text,
    mes_sem        text
);

COMMENT ON TABLE raw.m_time IS
    'M_Time — 2.189 filas, una por día, del 2022-03-01 al 2027-12-31. La única tabla del '
    'origen con PK correcta. 26 de las 40 consultas la usan.';
COMMENT ON COLUMN raw.m_time.sev_conteo IS
    '[SEvConteo] — semana de EVALUACIÓN de conteo, desplazada respecto a la semana '
    'calendario porque el corte de la evaluación agronómica no cae en domingo: difieren en '
    '527 de los 1.224 días poblados. Unir una tabla semanal contra esta columna, que tiene '
    'grano diario, es lo que produce la explosión x54 de H-05.';
COMMENT ON COLUMN raw.m_time.aqii IS '[AQII] — 100% nula. Se descarta.';
-- Faltan CampProAra y Trimestre, y dos consultas las piden: es H-04 caso 5. El trimestre es
-- trivial; la campaña productiva requiere que Planeamiento defina las fechas de corte (D-2).

-- ── M_Poda ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.m_poda (
    campania       text,
    fundo          text,
    variedad       text,
    modulo         text,
    turno          text,
    lote           text,
    area           text,
    fecha_siembra  text,
    fecha_inicio   text
);

COMMENT ON TABLE raw.m_poda IS
    'M_Poda — 2.159 filas, una por lote y campaña. 7 consultas dependen de ella.';
COMMENT ON COLUMN raw.m_poda.fecha_inicio IS
    '[FInicio] — fecha de poda: el origen del tiempo agronómico. En arándano el desarrollo '
    'se mide en días desde poda, no en fechas absolutas, porque dos lotes podados con un mes '
    'de diferencia están en estados fenológicos distintos el mismo día del calendario.';

-- ── M_Evaluadores ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.m_evaluadores (
    dni              text,
    nombres          text,
    apellidos        text,
    cod              text,
    inicio_labores   text,
    nacimiento       text,
    zona             text,
    celular          text,
    estado           text
);

COMMENT ON TABLE raw.m_evaluadores IS
    'M_Evaluadores — 31 filas. Ninguna de las 40 consultas la usa y el enlace se pensó por '
    'un código de 4 letras que no aparece en ninguna tabla de evaluación (H-09). El enlace '
    'correcto es por DNI, que es lo que sí se captura. El informe SEGUIMIENTO DE PERSONAL '
    'ya cruza evaluadores, pero por su cuenta y contra un Excel de tareo (B-5).';
COMMENT ON COLUMN raw.m_evaluadores.cod IS
    '[Cod] — código de 4 letras, 1 vacío de 31. Se conserva como atributo, no como clave.';
COMMENT ON COLUMN raw.m_evaluadores.inicio_labores IS
    '[InicioLabores] — fecha guardada como texto en el origen.';

-- ── M_nMuestra ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.m_n_muestra (
    evaluacion     text,
    fundo          text,
    modulo         text,
    turno          text,
    lote           text,
    cortina        text,
    hilera         text,
    planta         text,
    muestras       text
);

COMMENT ON TABLE raw.m_n_muestra IS
    'M_nMuestra — 681 filas. Define cuántas muestras corresponden por lote y tipo de '
    'evaluación: es la referencia para saber qué evaluaciones se hicieron con muestreo '
    'insuficiente, y por tanto qué estimaciones son poco fiables. Nadie la consulta (H-12). '
    'Conviven dos granos: 255 filas definen el muestreo a nivel de lote y dejan '
    'cortina/hilera/planta nulos.';

-- ── M_EquivalenciaElifab ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.m_equivalencia_elifab (
    productor      text,
    empresa        text
);

COMMENT ON TABLE raw.m_equivalencia_elifab IS
    'M_EquivalenciaElifab — 15 filas. Traduce el nombre de productor que usa la empacadora '
    'al de la empresa. Es la única tabla del origen que resuelve explícitamente un problema '
    'de vocabulario, y por eso es el precedente interno que justifica core.fundo_alias.';
