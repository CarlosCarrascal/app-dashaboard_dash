-- ============================================================================
-- 20_core · 040 · Evaluaciones fenológicas
--
-- La cadena fenológica completa, que es donde está el valor analítico de esta base:
--
--   poda → brotes → ramas → flores y cuajo → estados E1..E5 → diámetro de baya → cosecha
--
-- Cada eslabón predice el siguiente. Aquí se corrigen tres defectos estructurales:
--
--   N-1 · el grano de E01_Ramas es la RAMA, no la planta. Se parte en cabecera y detalle
--         (ADR-0002), porque la clave que proponía el plan original habría rechazado el 94%
--         de las filas.
--   H-02 · la PK de E04_Brotes no incluía la fecha, así que el motor RECHAZABA la segunda
--         evaluación de la misma planta. La clave estaba limitando la captura en lugar de
--         protegerla, y de ahí que la tabla tenga 28 veces menos filas que E01_Ramas.
--   H-02 · la PK de E03_ConteoEstados incluía E1, que es una MEDIDA: corregir un conteo
--         cambiaba la clave y duplicaba el registro en lugar de sustituirlo.
-- ============================================================================

-- ── Ramas: cabecera por planta ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.evaluacion_ramas (
    evaluacion_ramas_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id         integer NOT NULL REFERENCES core.lote(lote_id),
    fecha           date NOT NULL,
    cortina         smallint NOT NULL,
    hilera          smallint NOT NULL,
    planta          smallint NOT NULL,
    evaluador_id    smallint REFERENCES core.evaluador(evaluador_id),
    ramas_menor5    smallint CHECK (ramas_menor5 >= 0),
    ramas_mayor5    smallint CHECK (ramas_mayor5 >= 0),
    creado_en       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (lote_id, fecha, cortina, hilera, planta)
);

COMMENT ON TABLE core.evaluacion_ramas IS
    'Una fila por planta evaluada en una fecha: 5.384 filas. Guarda los conteos DECLARADOS por '
    'el evaluador, que en el origen venían repetidos en cada fila de rama.';
COMMENT ON COLUMN core.evaluacion_ramas.ramas_mayor5 IS
    'Ramas de más de 5 mm declaradas: son las que sostienen producción, frente a las menores, '
    'que son crecimiento vegetativo. La suma declarada (110.095) no coincide con el número de '
    'ramas medidas (71.095) porque se mide una submuestra.';

-- ── Ramas: detalle por rama medida ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.rama_medicion (
    rama_medicion_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evaluacion_ramas_id integer NOT NULL
        REFERENCES core.evaluacion_ramas(evaluacion_ramas_id) ON DELETE CASCADE,
    nro_rama        smallint NOT NULL CHECK (nro_rama BETWEEN 1 AND 99),
    -- numeric(10,4) y no (6,3): el origen tiene diámetros de hasta 8.789 mm, que son
    -- imposibles pero entran igual porque las cifras de control los incluyen (N-13).
    diametro        numeric(10,4) NOT NULL CHECK (diametro > 0),
    sospechoso      boolean NOT NULL DEFAULT false,
    id_origen       text
);

COMMENT ON TABLE core.rama_medicion IS
    'Una fila por RAMA medida: 71.095 tras deduplicar. El origen tenía 94.236 filas, con '
    '23.141 duplicados exactos por una recarga (H-03); la deduplicación se define como fila '
    'de origen idéntica, que es la única definición que reproduce la cifra de aceptación.';
COMMENT ON COLUMN core.rama_medicion.nro_rama IS
    'Número de orden de la rama dentro de la planta, rango observado 1-33. En el origen se '
    'llamaba [# Ramas] y estaba documentado como "total de ramas": sumarlo (730.318) no '
    'significa nada (hallazgo N-1).';
COMMENT ON COLUMN core.rama_medicion.diametro IS
    'Diámetro de ESA rama, en mm. AVG deduplicado = 10,8869 frente a 10,9777 con duplicados.';
-- Sin UNIQUE (evaluacion_ramas_id, nro_rama) a propósito: hay 4.557 filas donde la misma
-- rama aparece con dos diámetros distintos. Eso no es una recarga, es un conflicto de
-- captura; declarar la restricción obligaría a elegir un valor al azar. Se cargan las dos y
-- se registran en qua.rechazos para que Agronomía decida (ADR-0002).
CREATE INDEX IF NOT EXISTS rama_medicion_cab_idx ON core.rama_medicion (evaluacion_ramas_id);

-- ── Flores, cuajo y yemas ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.flores (
    flores_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id         integer NOT NULL REFERENCES core.lote(lote_id),
    fecha           date NOT NULL,
    cortina         smallint NOT NULL,
    hilera          smallint NOT NULL,
    planta          smallint NOT NULL,
    evaluador_id    smallint REFERENCES core.evaluador(evaluador_id),
    n_flores        smallint CHECK (n_flores >= 0),
    cuajo           smallint CHECK (cuajo >= 0),
    yemas_abiertas  smallint CHECK (yemas_abiertas >= 0),
    yemas_por_abrir smallint CHECK (yemas_por_abrir >= 0),
    hora            time,
    item            text
);

COMMENT ON TABLE core.flores IS
    'Conteo de flores, cuajo y yemas por planta: 43.490 filas. Mide el potencial productivo '
    'antes de que se forme el fruto. Sin clave natural única en el origen — ninguna '
    'combinación distingue las 43.490 filas, la mejor llega a 43.329 (hallazgo N-9) — así que '
    'se usa clave sustituta y los conflictos se registran en cuarentena.';
COMMENT ON COLUMN core.flores.cuajo IS
    'Flores fecundadas que se convertirán en fruto. La tasa de cuajo es el principal predictor '
    'de producción. 87,7% nula en el origen, y no es un defecto: el cuajo solo se evalúa en '
    'ventanas fenológicas concretas. Pero todo promedio sobre esta columna va sobre el 12,3% '
    'de los datos, y el tablero debe decirlo.';

CREATE INDEX IF NOT EXISTS flores_lote_fecha_idx ON core.flores (lote_id, fecha);
CREATE INDEX IF NOT EXISTS flores_evaluador_idx ON core.flores (evaluador_id, fecha);

-- ── Estados de madurez del fruto ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.estados (
    estados_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id         integer NOT NULL REFERENCES core.lote(lote_id),
    fecha           date NOT NULL,
    cortina         smallint NOT NULL,
    hilera          smallint NOT NULL,
    planta          smallint NOT NULL,
    evaluador_id    smallint REFERENCES core.evaluador(evaluador_id),
    e1 smallint NOT NULL DEFAULT 0 CHECK (e1 >= 0),
    e2 smallint NOT NULL DEFAULT 0 CHECK (e2 >= 0),
    e3 smallint NOT NULL DEFAULT 0 CHECK (e3 >= 0),
    e4 smallint NOT NULL DEFAULT 0 CHECK (e4 >= 0),
    e5 smallint NOT NULL DEFAULT 0 CHECK (e5 >= 0),
    total       integer GENERATED ALWAYS AS (e1 + e2 + e3 + e4 + e5) STORED,
    total_origen smallint,
    item        text NOT NULL,
    -- Clave verificada: con `item` da exactamente 18.714 = total de filas (hallazgo N-8).
    -- La clave del plan original, sin `item`, habría rechazado 212 filas.
    UNIQUE (item, lote_id, fecha, cortina, hilera, planta)
);

COMMENT ON TABLE core.estados IS
    'Distribución de frutos por estado de madurez E1 a E5, por planta y fecha: 18.714 filas. '
    'Es la base del pronóstico de cosecha: conociendo cuántos frutos hay en cada estado se '
    'estima cuándo estarán listos. La PK del origen incluía E1, que es una medida, así que '
    'corregir un conteo duplicaba el registro en lugar de sustituirlo (H-02).';
COMMENT ON COLUMN core.estados.total IS
    'Columna GENERADA. En el origen se capturaba aparte y no se recalculaba: SUM(Total) daba '
    '9.060.271 frente a SUM(E1..E5) = 9.057.841, una diferencia de 2.430 frutos que aquí '
    'desaparece por construcción.';
COMMENT ON COLUMN core.estados.total_origen IS
    'El Total tal como venía del origen, para poder auditar esa diferencia de 2.430 frutos.';

CREATE INDEX IF NOT EXISTS estados_lote_fecha_idx ON core.estados (lote_id, fecha);
CREATE INDEX IF NOT EXISTS estados_evaluador_idx ON core.estados (evaluador_id, fecha);

-- ── Brotes ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.brotes (
    brotes_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id         integer NOT NULL REFERENCES core.lote(lote_id),
    fecha           date NOT NULL,
    piso            text NOT NULL,
    cortina         smallint NOT NULL,
    hilera          smallint NOT NULL,
    planta          smallint NOT NULL,
    evaluador_id    smallint REFERENCES core.evaluador(evaluador_id),
    brotes          smallint NOT NULL CHECK (brotes >= 0),
    des1            text,
    des2            text,
    des3            text,
    hora            time,
    -- La fecha SÍ está en la clave. En el origen no estaba, y por eso el motor rechazaba la
    -- segunda evaluación de la misma planta: la clave limitaba la captura (H-02).
    UNIQUE (lote_id, fecha, piso, cortina, hilera, planta)
);

COMMENT ON TABLE core.brotes IS
    'Conteo de brotes nuevos por planta: la primera evaluación del ciclo, posterior a la poda. '
    '3.385 filas en el origen, y son tan pocas porque su clave primaria no incluía la fecha '
    '(H-02). Con la fecha en la clave, la captura deja de estar limitada.';
-- Des4 y Des5 no se migran: 100% nulas en el origen.

CREATE INDEX IF NOT EXISTS brotes_lote_fecha_idx ON core.brotes (lote_id, fecha);

-- ── Diámetro de baya ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.baya_medicion (
    baya_medicion_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id         integer NOT NULL REFERENCES core.lote(lote_id),
    fecha           date NOT NULL,
    cortina         smallint NOT NULL,
    hilera          smallint NOT NULL,
    nro_muestra     smallint NOT NULL,
    diametro        numeric(10,4) NOT NULL CHECK (diametro > 0),
    sospechoso      boolean NOT NULL DEFAULT false,
    UNIQUE (lote_id, fecha, cortina, hilera, nro_muestra)
);

COMMENT ON TABLE core.baya_medicion IS
    'Una fila por BAYA medida: 4.193 filas en 43 combinaciones de hilera y fecha, unas 97 '
    'bayas cada una (hallazgo N-7). El origen no identifica la baya, así que nro_muestra se '
    'asigna en la carga por orden estable. Es la tabla más limpia del origen — sin un solo '
    'nulo — y la única evaluación que trae el turno de origen, así que no depende del join '
    'que falla en H-01.';
COMMENT ON COLUMN core.baya_medicion.diametro IS
    'Calibre comercial de la baya en mm, AVG 19,885. Es el indicador que conecta la evaluación '
    'de campo con el resultado de packing: permitiría anticipar a qué mercado irá la fruta '
    'semanas antes de cosechar, y hoy ningún tablero lo cruza.';

CREATE INDEX IF NOT EXISTS baya_lote_fecha_idx ON core.baya_medicion (lote_id, fecha);

-- ── Muestreo requerido ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.muestra_requerida (
    muestra_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id         integer NOT NULL REFERENCES core.lote(lote_id),
    evaluacion      text NOT NULL,
    cortina         smallint,
    hilera          smallint,
    planta          smallint,
    muestras        smallint NOT NULL CHECK (muestras > 0),
    UNIQUE (lote_id, evaluacion, cortina, hilera, planta)
);

COMMENT ON TABLE core.muestra_requerida IS
    'Cuántas muestras corresponden por lote y tipo de evaluación: 681 filas. Es la referencia '
    'para saber qué evaluaciones se hicieron con muestreo insuficiente, y por tanto qué '
    'estimaciones son poco fiables. Ninguna consulta del origen la usaba (H-12). Conviven dos '
    'granos: 255 filas definen el muestreo a nivel de lote y dejan cortina, hilera y planta '
    'nulos.';
