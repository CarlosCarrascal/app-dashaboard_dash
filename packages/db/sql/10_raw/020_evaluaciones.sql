-- ============================================================================
-- 020 · raw · Evaluaciones fenológicas (E01–E05)
--
-- Todas las columnas son `text`, deliberadamente: raw es una copia fiel y nada debe fallar
-- al cargar. El casting ocurre en stg, donde un valor inesperado se puede desviar a
-- cuarentena en lugar de abortar la carga. H-10 (34 columnas numéricas guardadas como
-- texto en el origen) es la prueba de que confiar en el tipo del origen no es seguro.
--
-- Los nombres pasan a snake_case ASCII; el nombre original queda en el COMMENT, porque es
-- lo que hay que buscar cuando alguien pregunta por "[# Ramas]" o "[Ramas <5]".
-- ============================================================================

-- ── E01_Ramas ───────────────────────────────────────────────────────────────
-- 94.236 filas. OJO: el grano es la RAMA, no la planta (hallazgo N-1, ADR-0002).
CREATE TABLE IF NOT EXISTS raw.e01_ramas (
    id_origen     text,
    actividad     text,
    evaluador     text,
    fecha         text,
    fundo         text,
    modulo        text,
    lote          text,
    cortina       text,
    hilera        text,
    planta        text,
    ramas_lt5     text,
    ramas_gt5     text,
    num_ramas     text,
    diametro      text
);

COMMENT ON TABLE raw.e01_ramas IS
    'E01_Ramas — 94.236 filas. Una fila = una RAMA medida de una planta, no una planta '
    '(N-1). 23.141 filas son duplicados exactos por recarga (H-03).';
COMMENT ON COLUMN raw.e01_ramas.id_origen IS
    '[Id] — contador del registro de campo, reiniciado por lote y fecha. NO es único: '
    '15.043 valores para 94.236 filas (H-02).';
COMMENT ON COLUMN raw.e01_ramas.actividad IS
    '[Actividad] — un solo valor en toda la tabla: ConteoRamas. Es la columna que rompe '
    'la consulta "E" (H-04 caso 4), porque E02/E03 no la tienen.';
COMMENT ON COLUMN raw.e01_ramas.evaluador IS '[Evaluador] — DNI de 8 dígitos (H-09).';
COMMENT ON COLUMN raw.e01_ramas.fundo IS
    '[Fundo] — vocabulario D: nombre quechua sin prefijo (Kawsay Allpa, Ayllu Allpa, '
    'Quri Allpa, Arena Azul). No enlaza con M_Lotes (H-01).';
COMMENT ON COLUMN raw.e01_ramas.ramas_lt5 IS
    '[Ramas <5] — ramas declaradas de menos de 5 mm. Atributo de la PLANTA: se repite '
    'idéntico en todas las filas del mismo punto y fecha (N-1).';
COMMENT ON COLUMN raw.e01_ramas.ramas_gt5 IS
    '[Ramas >5] — ramas declaradas de más de 5 mm, las productivas. Atributo de la planta.';
COMMENT ON COLUMN raw.e01_ramas.num_ramas IS
    '[# Ramas] — NO es un total: es el número de orden de la rama medida, rango 1-33 '
    '(N-1). SUM sobre esta columna (730.318) no significa nada.';
COMMENT ON COLUMN raw.e01_ramas.diametro IS
    '[Diametro] — diámetro de ESA rama, en mm.';

-- ── E02_ConteoFlores ────────────────────────────────────────────────────────
-- 43.490 filas. Sin clave natural única: ninguna combinación las distingue (N-9).
CREATE TABLE IF NOT EXISTS raw.e02_conteo_flores (
    item        text,
    fecha       text,
    evaluador   text,
    fundo       text,
    modulo      text,
    lote        text,
    cortina     text,
    hilera      text,
    planta      text,
    n_flores    text,
    cuajo       text,
    ya          text,
    yp          text,
    hora        text
);

COMMENT ON TABLE raw.e02_conteo_flores IS
    'E02_ConteoFlores — 43.490 filas. Una fila = una planta evaluada. Sin clave natural '
    'única: la mejor combinación llega a 43.329 (N-9).';
COMMENT ON COLUMN raw.e02_conteo_flores.fundo IS
    '[Fundo] — vocabulario B: empresa (Aqu Anqa / Aqu Anqa II).';
COMMENT ON COLUMN raw.e02_conteo_flores.cuajo IS
    '[Cuajo] — flores fecundadas; principal predictor de producción. 87,7% nulo: solo se '
    'evalúa en ventanas fenológicas concretas, así que todo promedio va sobre el 12,3%.';
COMMENT ON COLUMN raw.e02_conteo_flores.ya IS '[YA] — yemas abiertas. 72,6% nulo.';
COMMENT ON COLUMN raw.e02_conteo_flores.yp IS '[YP] — yemas por abrir. 73,5% nulo.';

-- ── E03_ConteoEstados ───────────────────────────────────────────────────────
-- 18.714 filas. Clave natural válida: (item, fecha, modulo, lote, cortina, hilera, planta) (N-8).
CREATE TABLE IF NOT EXISTS raw.e03_conteo_estados (
    item        text,
    fecha       text,
    evaluador   text,
    fundo       text,
    modulo      text,
    lote        text,
    cortina     text,
    hilera      text,
    planta      text,
    e1          text,
    e2          text,
    e3          text,
    e4          text,
    e5          text,
    total       text,
    f16         text
);

COMMENT ON TABLE raw.e03_conteo_estados IS
    'E03_ConteoEstados — 18.714 filas. Distribución de frutos por estado de madurez E1-E5; '
    'base del pronóstico de cosecha. Sin ningún duplicado exacto (N-8).';
COMMENT ON COLUMN raw.e03_conteo_estados.total IS
    '[Total] — capturado aparte y NO recalculado: SUM(Total)=9.060.271 frente a '
    'SUM(E1..E5)=9.057.841, 2.430 frutos de diferencia. En core es columna generada.';
COMMENT ON COLUMN raw.e03_conteo_estados.f16 IS
    '[F16] — columna sin nombre real, residuo de importación. 5.484 nulos.';

-- ── E04_Brotes ──────────────────────────────────────────────────────────────
-- 3.385 filas, y son tan pocas porque la PK del origen no incluye la fecha (H-02).
CREATE TABLE IF NOT EXISTS raw.e04_brotes (
    piso        text,
    fecha       text,
    evaluador   text,
    fundo       text,
    modulo      text,
    lote        text,
    cortina     text,
    hilera      text,
    planta      text,
    brotes      text,
    des1        text,
    des2        text,
    des3        text,
    des4        text,
    des5        text,
    hora        text
);

COMMENT ON TABLE raw.e04_brotes IS
    'E04_Brotes — 3.385 filas. Primera evaluación del ciclo, tras la poda. Tiene 28 veces '
    'menos filas que E01_Ramas porque su PK no incluye Fecha y el motor RECHAZA una segunda '
    'evaluación de la misma planta: la clave estaba limitando la captura, no protegiéndola '
    '(H-02).';
COMMENT ON COLUMN raw.e04_brotes.piso IS '[Piso] — nivel dentro de la planta.';
COMMENT ON COLUMN raw.e04_brotes.des4 IS '[Des4] — 100% nula.';
COMMENT ON COLUMN raw.e04_brotes.des5 IS '[Des5] — 100% nula.';

-- ── E05_DiametrosBayas ──────────────────────────────────────────────────────
-- 4.193 filas. Una fila = UNA BAYA medida, ~97 por hilera y fecha (N-7).
CREATE TABLE IF NOT EXISTS raw.e05_diametros_bayas (
    modulo      text,
    turno       text,
    lote        text,
    cortina     text,
    hilera      text,
    diametro    text,
    fecha       text
);

COMMENT ON TABLE raw.e05_diametros_bayas IS
    'E05_DiametrosBayas — 4.193 filas. Una fila = una baya medida: hay 43 combinaciones de '
    '(fecha, módulo, turno, lote, cortina, hilera) para 4.193 filas, ~97 bayas cada una '
    '(N-7). Sin un solo nulo: la tabla más limpia del origen. Ninguna consulta de Access la '
    'usa, pero el informe SEGUIMIENTO DE PERSONAL sí la lee (B-5).';
COMMENT ON COLUMN raw.e05_diametros_bayas.turno IS
    '[Turno] — único caso en las evaluaciones donde el turno viene de origen y no hace '
    'falta el join que falla en H-01.';
COMMENT ON COLUMN raw.e05_diametros_bayas.diametro IS
    '[Diametro] — calibre comercial de la baya, en mm. AVG = 19,885.';
