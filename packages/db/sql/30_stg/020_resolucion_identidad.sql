-- ============================================================================
-- 30_stg · 020 · Resolución de identidad
--
-- Aquí se resuelve H-01, el hallazgo crítico: el fundo se escribe de seis formas distintas y
-- por eso el 100% de E01_Ramas no enlazaba con el maestro.
--
-- La regla es ADR-0003: la identidad de un lote es (empresa, módulo, lote). El alias de fundo
-- solo sirve para averiguar la EMPRESA; nunca es una clave de join, porque no determina el
-- fundo físico — verificado: `Aqu Anqa II - Kawsay Allpa` está en dos fundos y el vocabulario
-- comercial antiguo `Aqu Anqa II - Ampliacion` en tres.
--
-- Y la regla que gobierna todo lo demás: **nunca adivina**. Cuando la identidad es ambigua
-- devuelve NULL con un motivo, y la fila va a cuarentena entera. Preferimos 732 filas
-- apartadas y explicadas a 732 filas asignadas al lote más parecido.
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'resolucion_lote'
                     AND typnamespace = 'stg'::regnamespace) THEN
        CREATE TYPE stg.resolucion_lote AS (
            lote_id integer,
            motivo  text
        );
    END IF;
END
$$;

COMMENT ON TYPE stg.resolucion_lote IS
    'Resultado de resolver un lote: su id, o NULL con el motivo por el que no se pudo. El '
    'motivo es lo que se registra en qua.rechazos para que sea accionable.';

-- ── Empresa ─────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION stg.fn_resolver_empresa(p_fundo text)
RETURNS smallint
LANGUAGE sql STABLE PARALLEL SAFE
AS $$
    SELECT a.empresa_id
    FROM core.fundo_alias a
    WHERE a.alias_norm = stg.fn_norm_texto(p_fundo);
$$;

COMMENT ON FUNCTION stg.fn_resolver_empresa(text) IS
    'Empresa a partir de CUALQUIERA de los seis vocabularios de fundo, vía core.fundo_alias. '
    'Reconoce el nombre de empresa (Aqu Anqa II), el fundo físico (Aqu Anqa 3), el alias '
    'operativo con prefijo y sin él (Kawsay Allpa) y el comercial antiguo (Vivadis).';

-- ── Módulo ──────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION stg.fn_resolver_modulo(p_fundo text, p_modulo text)
RETURNS smallint
LANGUAGE plpgsql STABLE PARALLEL SAFE
AS $$
DECLARE
    v_modulo    text := stg.fn_norm_modulo(p_modulo);
    v_empresa   smallint := stg.fn_resolver_empresa(p_fundo);
    v_fundo     smallint;
    v_id        smallint;
    v_cuantos   integer;
BEGIN
    IF v_modulo IS NULL THEN
        RETURN NULL;
    END IF;

    -- Si el alias identifica el fundo físico sin ambigüedad, es la vía más precisa.
    SELECT a.fundo_id INTO v_fundo
    FROM core.fundo_alias a
    WHERE a.alias_norm = stg.fn_norm_texto(p_fundo) AND NOT a.ambiguo;

    IF v_fundo IS NOT NULL THEN
        SELECT m.modulo_id INTO v_id
        FROM core.modulo m
        WHERE m.fundo_id = v_fundo AND m.codigo = v_modulo;
        IF v_id IS NOT NULL THEN
            RETURN v_id;
        END IF;
    END IF;

    -- Si no, la empresa basta siempre que el módulo sea único dentro de ella.
    IF v_empresa IS NOT NULL THEN
        SELECT count(*), min(m.modulo_id) INTO v_cuantos, v_id
        FROM core.modulo m
        JOIN core.fundo f ON f.fundo_id = m.fundo_id
        WHERE f.empresa_id = v_empresa AND m.codigo = v_modulo;
        IF v_cuantos = 1 THEN
            RETURN v_id;
        END IF;
    END IF;

    -- Último recurso: el código de módulo por sí solo, y solo si es único en toda la
    -- operación. M01 a M04 existen en dos fundos, así que ahí devuelve NULL.
    SELECT count(*), min(m.modulo_id) INTO v_cuantos, v_id
    FROM core.modulo m
    WHERE m.codigo = v_modulo;

    RETURN CASE WHEN v_cuantos = 1 THEN v_id ELSE NULL END;
END;
$$;

COMMENT ON FUNCTION stg.fn_resolver_modulo(text, text) IS
    'Módulo a partir del fundo (en cualquier vocabulario) y el código de módulo. Prueba tres '
    'vías en orden de precisión: fundo físico, empresa, y código único global. Devuelve NULL '
    'si ninguna resuelve sin ambigüedad — el caso de M01-M04, que pertenecen a dos fundos.';

-- ── Lote ────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION stg.fn_resolver_lote_detalle(
    p_fundo text, p_modulo text, p_lote text
)
RETURNS stg.resolucion_lote
LANGUAGE plpgsql STABLE PARALLEL SAFE
AS $$
DECLARE
    v_modulo_txt text := stg.fn_norm_modulo(p_modulo);
    v_lote_txt   text := stg.fn_norm_lote(p_lote);
    v_modulo_id  smallint;
    v_id         integer;
    v_cuantos    integer;
    r            stg.resolucion_lote;
BEGIN
    IF v_modulo_txt IS NULL OR v_lote_txt IS NULL THEN
        -- Es el patrón de las 3 filas de subtotal de Excel de H-06: todos los
        -- identificadores vacíos y un valor grande en KG.
        r := (NULL::integer, 'SIN_IDENTIFICADORES');
        RETURN r;
    END IF;

    v_modulo_id := stg.fn_resolver_modulo(p_fundo, p_modulo);

    IF v_modulo_id IS NOT NULL THEN
        SELECT l.lote_id INTO v_id
        FROM core.lote l
        WHERE l.modulo_id = v_modulo_id AND l.codigo = v_lote_txt;

        IF v_id IS NOT NULL THEN
            r := (v_id, NULL::text);
        ELSE
            r := (NULL::integer, 'LOTE_INEXISTENTE');
        END IF;
        RETURN r;
    END IF;

    -- Sin módulo resuelto, queda el par (módulo, lote) global. Vale para 861 de los 870
    -- pares; los 9 restantes están en las dos empresas a la vez y no se pueden desambiguar
    -- sin el fundo (hallazgo N-4).
    SELECT count(*), min(l.lote_id) INTO v_cuantos, v_id
    FROM core.lote l
    JOIN core.modulo m ON m.modulo_id = l.modulo_id
    WHERE m.codigo = v_modulo_txt AND l.codigo = v_lote_txt;

    IF v_cuantos = 1 THEN
        r := (v_id, NULL::text);
    ELSIF v_cuantos > 1 THEN
        r := (NULL::integer, 'LOTE_AMBIGUO');
    ELSE
        r := (NULL::integer, 'LOTE_INEXISTENTE');
    END IF;
    RETURN r;
END;
$$;

COMMENT ON FUNCTION stg.fn_resolver_lote_detalle(text, text, text) IS
    'Resuelve un lote y explica el fallo cuando no puede. Motivos: SIN_IDENTIFICADORES (la '
    'fila no trae módulo o lote, patrón de las filas de subtotal de H-06), LOTE_INEXISTENTE '
    '(el par no está en el maestro vigente) y LOTE_AMBIGUO (el par existe en las dos empresas '
    'y el fundo no permite distinguir).';

CREATE OR REPLACE FUNCTION stg.fn_resolver_lote(p_fundo text, p_modulo text, p_lote text)
RETURNS integer
LANGUAGE sql STABLE PARALLEL SAFE
AS $$
    SELECT (stg.fn_resolver_lote_detalle(p_fundo, p_modulo, p_lote)).lote_id;
$$;

COMMENT ON FUNCTION stg.fn_resolver_lote(text, text, text) IS
    'Atajo cuando solo interesa el id. Para cargar hechos usar fn_resolver_lote_detalle, que '
    'devuelve además el motivo y permite que la cuarentena diga algo accionable.';

-- ── Campaña, variedad y evaluador ───────────────────────────────────────────

CREATE OR REPLACE FUNCTION stg.fn_resolver_campania(p_codigo text)
RETURNS smallint
LANGUAGE sql STABLE PARALLEL SAFE
AS $$
    SELECT c.campania_id FROM core.campania c
    WHERE c.codigo = upper(btrim(coalesce(p_codigo, '')));
$$;

CREATE OR REPLACE FUNCTION stg.fn_resolver_variedad(p_nombre text)
RETURNS smallint
LANGUAGE sql STABLE PARALLEL SAFE
AS $$
    SELECT a.variedad_id FROM core.variedad_alias a
    WHERE a.alias_norm = stg.fn_norm_texto(p_nombre);
$$;

CREATE OR REPLACE FUNCTION stg.fn_resolver_evaluador(p_dni text)
RETURNS smallint
LANGUAGE sql STABLE PARALLEL SAFE
AS $$
    SELECT e.evaluador_id FROM core.evaluador e
    WHERE e.dni = btrim(coalesce(p_dni, ''));
$$;

CREATE OR REPLACE FUNCTION stg.fn_resolver_turno(p_turno text)
RETURNS smallint
LANGUAGE sql STABLE PARALLEL SAFE
AS $$
    SELECT t.turno_id FROM core.turno t WHERE t.codigo = stg.fn_norm_turno(p_turno);
$$;
