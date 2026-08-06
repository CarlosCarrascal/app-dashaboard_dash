-- ============================================================================
-- 30_stg · 010 · Normalización de códigos y conversión de tipos
--
-- `raw` es todo texto a propósito. Aquí es donde ese texto se convierte en datos, y donde se
-- absorben las formas en que cada fuente escribe lo mismo de manera distinta:
--
--   lote     L11B  vs  L011B           (hallazgo N-3)
--   módulo   M02  vs  2  vs  Módulo 02  vs  10b   (hallazgo N-2)
--   turno    T01 de riego  vs  DÍA/Noche/NOCHE de packing   (hallazgo N-2)
--   semana   33  vs  'Sem 33'
--   fecha    ISO en casi todo  vs  '5/08/1977' en M_Evaluadores
--   hora     '1899-12-30 07:52:39', que es como Access guarda una hora sin fecha
--
-- Todas las conversiones son TOLERANTES: ante un valor que no encaja devuelven NULL en lugar
-- de abortar. Lo que no se puede convertir se detecta después con las vistas de perfilado y
-- va a cuarentena con su fila entera, nunca se pierde.
-- ============================================================================

-- ── Texto ───────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION stg.fn_norm_texto(p_texto text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    -- unaccent(regdictionary, text) es IMMUTABLE; unaccent(text) a secas es solo STABLE y no
    -- podría usarse en un índice ni en una columna generada.
    SELECT nullif(
             upper(regexp_replace(unaccent('unaccent'::regdictionary, btrim(p_texto)), '\s+', ' ', 'g')),
             ''
           );
$$;

COMMENT ON FUNCTION stg.fn_norm_texto(text) IS
    'Forma canónica para COMPARAR textos: sin acentos, en mayúsculas, sin espacios repetidos. '
    'Es lo que hace que Ampliación y Ampliacion caigan en la misma entrada de fundo_alias. '
    'No sustituye al valor original, que siempre se conserva.';

-- ── Códigos de ubicación ────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION stg.fn_norm_lote(p_lote text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE
             WHEN nullif(btrim(coalesce(p_lote, '')), '') IS NULL THEN NULL
             WHEN upper(btrim(p_lote)) ~ '^L?0*([0-9]+)([A-Z]*)$' THEN
                 'L'
                 || lpad((regexp_match(upper(btrim(p_lote)), '^L?0*([0-9]+)([A-Z]*)$'))[1], 3, '0')
                 || (regexp_match(upper(btrim(p_lote)), '^L?0*([0-9]+)([A-Z]*)$'))[2]
             -- Lo que no encaja se devuelve en mayúsculas para que quede huérfano y visible,
             -- en lugar de convertirse en NULL y desaparecer.
             ELSE upper(btrim(p_lote))
           END;
$$;

COMMENT ON FUNCTION stg.fn_norm_lote(text) IS
    'Código canónico de lote: L + 3 dígitos + sufijo. L11B, 11B y l011b dan todos L011B. '
    'Sin esto, esas filas quedan huérfanas aunque el lote exista: normalizar baja los '
    'huérfanos de ~1.300 a ~732 filas y lleva el maestro histórico a cobertura total (N-3).';

CREATE OR REPLACE FUNCTION stg.fn_norm_modulo(p_modulo text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    WITH limpio AS (
        -- Quita el prefijo "Módulo"/"MODULO" que usa H02_BDElifab y deja solo el código.
        SELECT btrim(regexp_replace(
                   unaccent('unaccent'::regdictionary, upper(btrim(coalesce(p_modulo, '')))),
                   '^M[O0]DULO\s*', '')) AS v
    )
    SELECT CASE
             WHEN nullif(v, '') IS NULL THEN NULL
             WHEN v ~ '^M?0*([0-9]+)([A-Z]*)$' THEN
                 'M'
                 || lpad((regexp_match(v, '^M?0*([0-9]+)([A-Z]*)$'))[1], 2, '0')
                 || (regexp_match(v, '^M?0*([0-9]+)([A-Z]*)$'))[2]
             ELSE v
           END
    FROM limpio;
$$;

COMMENT ON FUNCTION stg.fn_norm_modulo(text) IS
    'Código canónico de módulo: M + 2 dígitos + sufijo. Absorbe las cuatro formas observadas '
    '— M02, 2, "Módulo 02" y 10b — que conviven porque H02_BDElifab escribe el módulo de dos '
    'maneras distintas y ninguna coincide con la del maestro (N-2).';

CREATE OR REPLACE FUNCTION stg.fn_norm_turno(p_turno text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE
             WHEN nullif(btrim(coalesce(p_turno, '')), '') IS NULL THEN NULL
             WHEN upper(btrim(p_turno)) ~ '^T?0*([0-9]+)$' THEN
                 'T' || lpad((regexp_match(upper(btrim(p_turno)), '^T?0*([0-9]+)$'))[1], 2, '0')
             ELSE upper(btrim(p_turno))
           END;
$$;

COMMENT ON FUNCTION stg.fn_norm_turno(text) IS
    'Turno de riego canónico: T00 a T12. Ojo, NO sirve para el turno de H02_BDElifab, que es '
    'DÍA/NOCHE y designa otra cosa: para ese está fn_norm_turno_packing (N-2).';

CREATE OR REPLACE FUNCTION stg.fn_norm_turno_packing(p_turno text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE stg.fn_norm_texto(p_turno)
             WHEN 'DIA' THEN 'DIA'
             WHEN 'NOCHE' THEN 'NOCHE'
             ELSE NULL
           END;
$$;

COMMENT ON FUNCTION stg.fn_norm_turno_packing(text) IS
    'Turno de proceso de la empacadora: DIA o NOCHE. El origen escribe DÍA, Noche y NOCHE. '
    'Es un dominio distinto del turno de riego aunque la columna se llame igual (N-2).';

CREATE OR REPLACE FUNCTION stg.fn_clave_ubicacion(p_fundo text, p_modulo text, p_lote text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    -- Clave única de ubicación en una sola columna. Existe por rendimiento: unir por tres
    -- columnas que admiten NULL obliga a IS NOT DISTINCT FROM, que impide el hash join y
    -- convierte la resolución de 300.000 filas en un nested loop.
    SELECT coalesce(stg.fn_norm_texto(p_fundo), '') || '|'
        || coalesce(stg.fn_norm_modulo(p_modulo), '') || '|'
        || coalesce(stg.fn_norm_lote(p_lote), '');
$$;

COMMENT ON FUNCTION stg.fn_clave_ubicacion(text, text, text) IS
    'Clave de ubicación normalizada, para unir los hechos contra stg.mapa_lote con un hash '
    'join en lugar de comparar tres columnas nulables.';

-- ── Conversión de tipos, tolerante ──────────────────────────────────────────
--
-- Todas validan con una expresión regular ANTES de convertir, en SQL puro.
--
-- La versión anterior era plpgsql con `EXCEPTION WHEN others THEN RETURN NULL`, que parece la
-- forma natural de hacer un cast tolerante. Es una trampa: un bloque EXCEPTION abre una
-- subtransacción, y eso NO se puede hacer en un worker paralelo. Al estar declaradas
-- PARALLEL SAFE, PostgreSQL las ejecutaba en paralelo y devolvían NULL en silencio para las
-- filas que tocaba cada worker — 4.338 de 94.236 en E01_Ramas, sin un solo error visible.
-- Exactamente la clase de defecto silencioso que esta migración existe para eliminar.
--
-- Validar con regex es además bastante más rápido: no hay subtransacción por fila.

-- Número decimal, con notación científica incluida: el extractor serializa los flotantes con
-- repr() y hay valores como 1.2478755888830965e-27.
CREATE OR REPLACE FUNCTION stg.fn_es_numero(p_texto text)
RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT btrim(coalesce(p_texto, '')) ~ '^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$';
$$;

CREATE OR REPLACE FUNCTION stg.fn_a_numero(p_texto text)
RETURNS numeric
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE WHEN stg.fn_es_numero(p_texto) THEN btrim(p_texto)::numeric END;
$$;

CREATE OR REPLACE FUNCTION stg.fn_a_entero(p_texto text)
RETURNS integer
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    -- round() antes del cast: el origen escribe algunos enteros como 55.0.
    SELECT CASE WHEN stg.fn_es_numero(p_texto)
                THEN round(btrim(p_texto)::numeric)::integer END;
$$;

CREATE OR REPLACE FUNCTION stg.fn_conteo(p_texto text)
RETURNS integer
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    -- Un conteo no puede ser negativo. El origen tiene dos filas con -1 (una en
    -- E02_ConteoFlores y otra en E04_Brotes): son errores de captura, no un centinela de
    -- "no medido", porque el origen ya distingue el no medido con NULL. Se convierten a NULL
    -- y quedan registradas en cuarentena.
    SELECT CASE WHEN stg.fn_a_entero(p_texto) >= 0 THEN stg.fn_a_entero(p_texto) END;
$$;

COMMENT ON FUNCTION stg.fn_conteo(text) IS
    'Conteo entero no negativo. Los valores negativos pasan a NULL: son imposibles en un '
    'conteo y el origen ya usa NULL para lo no medido.';

CREATE OR REPLACE FUNCTION stg.fn_diametro_valido(p_mm numeric, p_max numeric)
RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    -- Marca los diámetros físicamente imposibles sin descartarlos: el origen tiene ramas de
    -- 8.789 mm y bayas de 13.381 mm, que son casi con seguridad decimales perdidos. Se
    -- cargan igual, porque las cifras de control de la auditoría los incluyen (N-13).
    SELECT p_mm IS NOT NULL AND p_mm > 0 AND p_mm <= p_max;
$$;

CREATE OR REPLACE FUNCTION stg.fn_a_real(p_texto text)
RETURNS double precision
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    -- El doble cast NO es redundante: en Access estas medidas son Single (4 bytes) y sus
    -- sumas se calculan en doble precisión. Pasar por real recupera el valor exacto que tenía
    -- el origen, y sumar en float8 reproduce su aritmética. Es lo que permite que
    -- SUM(KG) dé 33.381.134,659151 y no un número parecido.
    SELECT CASE WHEN stg.fn_es_numero(p_texto)
                THEN btrim(p_texto)::real::double precision END;
$$;

COMMENT ON FUNCTION stg.fn_a_real(text) IS
    'Convierte una medida de Access reproduciendo su aritmética: texto -> real (el Single '
    'original, bit a bit) -> double precision (como Access acumula las sumas).';

-- El extractor escribe las fechas en ISO 8601, con o sin parte de tiempo.
CREATE OR REPLACE FUNCTION stg.fn_es_timestamp(p_texto text)
RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT btrim(coalesce(p_texto, ''))
             ~ '^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$';
$$;

CREATE OR REPLACE FUNCTION stg.fn_a_fecha(p_texto text)
RETURNS date
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    -- 1899-12-30 es la fecha cero de Access: un valor así no es una fecha, es una hora suelta.
    SELECT CASE
             WHEN NOT stg.fn_es_timestamp(p_texto) THEN NULL
             WHEN left(btrim(p_texto), 10) = '1899-12-30' THEN NULL
             ELSE left(btrim(p_texto), 10)::date
           END;
$$;

CREATE OR REPLACE FUNCTION stg.fn_a_timestamp(p_texto text)
RETURNS timestamp
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE WHEN stg.fn_es_timestamp(p_texto) THEN btrim(p_texto)::timestamp END;
$$;

CREATE OR REPLACE FUNCTION stg.fn_a_hora(p_texto text)
RETURNS time
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE
             -- Con fecha delante: así llegan E02, E04 y H02.
             WHEN stg.fn_es_timestamp(p_texto) THEN btrim(p_texto)::timestamp::time
             -- Hora pelada: así llega E03.F16, porque en Access esa columna es de TEXTO y no
             -- de fecha. Exigir un timestamp descartaba sus 13.230 horas enteras (N-17).
             WHEN btrim(coalesce(p_texto, '')) ~ '^\d{1,2}:\d{2}(:\d{2})?$'
                  THEN btrim(p_texto)::time
           END;
$$;

COMMENT ON FUNCTION stg.fn_a_hora(text) IS
    'Extrae la hora, venga con fecha delante o sola. Access guarda una hora sin fecha como '
    '1899-12-30 07:52:39, su fecha cero, y quedarse con la parte de tiempo es lo correcto '
    'tanto ahí como en H02, donde el mismo campo sí trae fecha real. E03.F16 es la excepción: '
    'en el origen es una columna de texto, así que llega como 09:59:03 — exigirle un timestamp '
    'era lo que descartaba sus 13.230 horas (N-17).';

CREATE OR REPLACE FUNCTION stg.fn_a_fecha_dmy(p_texto text)
RETURNS date
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE
             WHEN btrim(coalesce(p_texto, '')) ~ '^\d{1,2}/\d{1,2}/\d{4}$'
             THEN to_date(btrim(p_texto), 'FMDD/FMMM/YYYY')
           END;
$$;

COMMENT ON FUNCTION stg.fn_a_fecha_dmy(text) IS
    'Para las fechas que M_Evaluadores guarda como texto en formato d/mm/aaaa (5/08/1977).';

CREATE OR REPLACE FUNCTION stg.fn_semana(p_texto text)
RETURNS smallint
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    -- H02_BDElifab escribe la semana como 'Sem 33': 117.536 filas donde un cast directo falla.
    SELECT CASE
             WHEN btrim(coalesce(p_texto, '')) ~ '([0-9]{1,2})'
             THEN (regexp_match(btrim(p_texto), '([0-9]{1,2})'))[1]::smallint
             ELSE NULL
           END;
$$;

CREATE OR REPLACE FUNCTION stg.fn_mes_abrev(p_texto text)
RETURNS smallint
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE stg.fn_norm_texto(p_texto)
             WHEN 'ENE' THEN 1  WHEN 'FEB' THEN 2  WHEN 'MAR' THEN 3
             WHEN 'ABR' THEN 4  WHEN 'MAY' THEN 5  WHEN 'JUN' THEN 6
             WHEN 'JUL' THEN 7  WHEN 'AGO' THEN 8
             -- El origen usa "Set" por setiembre, no "Sep". Se aceptan las dos.
             WHEN 'SET' THEN 9  WHEN 'SEP' THEN 9
             WHEN 'OCT' THEN 10 WHEN 'NOV' THEN 11 WHEN 'DIC' THEN 12
             ELSE NULL
           END::smallint;
$$;

COMMENT ON FUNCTION stg.fn_mes_abrev(text) IS
    'Mes a partir de la abreviatura en español de M_Time. Acepta Set y Sep: el origen escribe '
    'setiembre a la peruana.';

-- ── Calibre comercial ───────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION stg.fn_calibre_mm(p_texto text)
RETURNS numeric
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE
             WHEN stg.fn_norm_texto(p_texto) ~ '^([0-9]+)\s*MM'
             THEN (regexp_match(stg.fn_norm_texto(p_texto), '^([0-9]+)\s*MM'))[1]::numeric
             ELSE NULL
           END;
$$;

COMMENT ON FUNCTION stg.fn_calibre_mm(text) IS
    'Milímetros de un calibre escrito como "12 mm" o "26 mm+". Devuelve NULL para los valores '
    'que no son un calibre y que en el origen conviven en la misma columna: DESCARTE, '
    'Descarte, Defectos y "-" (H-10).';
