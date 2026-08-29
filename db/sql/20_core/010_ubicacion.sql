-- ============================================================================
-- 20_core · 010 · Ubicación: empresa → fundo → módulo → lote
--
-- Es la corrección de H-01, el hallazgo crítico de la auditoría. La regla está en
-- ADR-0003: **la identidad de un lote es (empresa, módulo, lote)**; el alias de fundo es
-- un atributo descriptivo y nunca una clave de join.
--
-- El motivo, verificado: `Aqu Anqa II - Kawsay Allpa` corresponde a dos fundos físicos
-- distintos, y el vocabulario comercial antiguo es todavía peor — `Aqu Anqa II - Ampliacion`
-- abarca tres. Unir por alias duplicaría filas.
--
-- Política de fila centinela (ADR-0005): ninguna FK en una tabla de hechos puede ser NULL.
-- Cuando la identidad no resuelve, el hecho apunta a una fila "Sin identificar" en la
-- dimensión correspondiente, en vez de dejar la FK vacía. Por eso empresa, fundo, modulo,
-- turno, variedad y lote llevan `es_sentinel`: marca esa única fila, y un índice único
-- parcial garantiza que no pueda haber una segunda.
-- ============================================================================

CREATE TABLE IF NOT EXISTS core.m_empresa (
    empresa_id      smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre          text NOT NULL UNIQUE,
    activo          boolean NOT NULL DEFAULT true,
    es_sentinel     boolean NOT NULL DEFAULT false,
    creado_en       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE core.m_empresa IS
    'Razón social. Dos: Aqu Anqa y Aqu Anqa II. Es el vocabulario B de la auditoría '
    '(FundoPPto) y el único nivel que todas las fuentes traen de forma reconocible.';
COMMENT ON COLUMN core.m_empresa.es_sentinel IS
    'true en la fila "Sin identificar" (ADR-0005). Ninguna tabla de hechos apunta hoy a esta '
    'fila directamente, pero existe para que fundo/modulo/lote puedan construir su propia '
    'cadena de centinelas sin depender de una empresa real.';

CREATE UNIQUE INDEX IF NOT EXISTS empresa_un_sentinel ON core.m_empresa ((true)) WHERE es_sentinel;

CREATE TABLE IF NOT EXISTS core.m_fundo (
    fundo_id        smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empresa_id      smallint NOT NULL REFERENCES core.m_empresa(empresa_id),
    codigo          text NOT NULL,
    alias_operativo text,
    activo          boolean NOT NULL DEFAULT true,
    es_sentinel     boolean NOT NULL DEFAULT false,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (empresa_id, codigo)
);

CREATE UNIQUE INDEX IF NOT EXISTS fundo_un_sentinel ON core.m_fundo ((true)) WHERE es_sentinel;

COMMENT ON TABLE core.m_fundo IS
    'Fundo físico. Seis: Aqu Anqa 1 a Aqu Anqa 6, del maestro vigente. Sustituye a los '
    'cuatro nombres comerciales de M_Lotes (Ampliacion, Vivadis, Sta.Teresa, ArenaAzul), '
    'que no son recuperables como identificador: uno solo de ellos abarca tres fundos.';
COMMENT ON COLUMN core.m_fundo.alias_operativo IS
    'Nombre quechua de uso corriente (Kawsay Allpa, Ayllu Allpa, Quri Allpa, Arena Azul). '
    'Descriptivo: dos fundos pueden compartirlo.';
COMMENT ON COLUMN core.m_fundo.es_sentinel IS
    'true en "Sin identificar" (ADR-0005): el peldaño intermedio que necesita el módulo '
    'centinela para poder existir (fundo_id es NOT NULL en core.m_modulo).';

CREATE TABLE IF NOT EXISTS core.m_fundo_alias (
    alias_norm      text PRIMARY KEY,
    alias_original  text NOT NULL,
    tipo            text NOT NULL CHECK (tipo IN ('empresa', 'fisico', 'operativo', 'comercial')),
    empresa_id      smallint REFERENCES core.m_empresa(empresa_id),
    fundo_id        smallint REFERENCES core.m_fundo(fundo_id),
    ambiguo         boolean NOT NULL DEFAULT false,
    origen          text NOT NULL,
    nota            text
);

COMMENT ON TABLE core.m_fundo_alias IS
    'Diccionario de las seis formas en que las fuentes nombran un fundo. Resuelve la EMPRESA, '
    'que es lo que se necesita para identificar un lote; el fundo físico solo cuando el alias '
    'lo determina sin ambigüedad. Sigue el precedente de M_EquivalenciaElifab, la única tabla '
    'del origen que resolvía explícitamente un problema de vocabulario.';
COMMENT ON COLUMN core.m_fundo_alias.alias_norm IS
    'Alias normalizado con stg.fn_norm_texto (sin acentos, mayúsculas, espacios colapsados), '
    'para que Ampliación y Ampliacion caigan en la misma entrada.';
COMMENT ON COLUMN core.m_fundo_alias.ambiguo IS
    'true cuando el alias abarca más de un fundo físico y por tanto NO puede usarse para '
    'resolverlo. Caso verificado: Kawsay Allpa está en Aqu Anqa 3 y en Aqu Anqa 5.';
COMMENT ON COLUMN core.m_fundo_alias.fundo_id IS
    'NULL si el alias no determina un fundo físico (porque es un nombre de empresa, o porque '
    'es ambiguo). Nunca se rellena por aproximación.';

CREATE TABLE IF NOT EXISTS core.m_modulo (
    modulo_id       smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fundo_id        smallint NOT NULL REFERENCES core.m_fundo(fundo_id),
    codigo          text NOT NULL,
    activo          boolean NOT NULL DEFAULT true,
    es_sentinel     boolean NOT NULL DEFAULT false,
    UNIQUE (fundo_id, codigo)
);

COMMENT ON TABLE core.m_modulo IS
    'Módulo dentro de un fundo. 25 códigos distintos (M01-M24, con M10A/M10B) en 29 '
    'combinaciones fundo x módulo, porque M01 a M04 pertenecen a DOS fundos a la vez: '
    'Aqu Anqa 1 (empresa Aqu Anqa) y Aqu Anqa 2 (empresa Aqu Anqa II). Por eso el código de '
    'módulo por sí solo no identifica un módulo.';
COMMENT ON COLUMN core.m_modulo.es_sentinel IS
    'true en el módulo "Sin identificar" (ADR-0005). `forecast_campania.modulo_id` apunta '
    'aquí cuando el módulo del origen no resuelve — 624 filas verificadas (hallazgo N-15). '
    'Antes de esta corrección esas 624 filas tenían modulo_id NULL y no quedaban en '
    'cuarentena: era un hueco de trazabilidad, no una decisión.';

CREATE UNIQUE INDEX IF NOT EXISTS modulo_un_sentinel ON core.m_modulo ((true)) WHERE es_sentinel;

CREATE TABLE IF NOT EXISTS core.m_turno (
    turno_id        smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo          text NOT NULL UNIQUE,
    es_sentinel     boolean NOT NULL DEFAULT false
);

COMMENT ON TABLE core.m_turno IS
    'Turno de riego o labor: T00 a T12. No es una unidad física sino un agrupamiento de '
    'gestión. OJO: no confundir con el turno de H02_BDElifab, que es DÍA/NOCHE y designa el '
    'turno de proceso de la empacadora — son dos dominios con el mismo nombre de columna '
    '(hallazgo N-2). Ese vive en core.op_packing.turno_packing.';
COMMENT ON COLUMN core.m_turno.es_sentinel IS
    'true en "Sin identificar" (ADR-0005). Distinto de T00, que es un valor real del origen '
    '(turno de encabezado/prueba, ver core.m_lote.es_ficticio) — no se reutiliza T00 como '
    'centinela para no mezclar dos significados distintos.';

CREATE UNIQUE INDEX IF NOT EXISTS turno_un_sentinel ON core.m_turno ((true)) WHERE es_sentinel;

CREATE TABLE IF NOT EXISTS core.m_variedad (
    variedad_id     smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre          text NOT NULL UNIQUE,
    es_sentinel     boolean NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX IF NOT EXISTS variedad_un_sentinel ON core.m_variedad ((true)) WHERE es_sentinel;

CREATE TABLE IF NOT EXISTS core.m_variedad_alias (
    alias_norm      text PRIMARY KEY,
    alias_original  text NOT NULL,
    variedad_id     smallint NOT NULL REFERENCES core.m_variedad(variedad_id),
    origen          text NOT NULL
);

COMMENT ON TABLE core.m_variedad IS
    'Variedad de arándano. No puede derivarse del maestro de lotes, que solo tiene Sekoya '
    'pop: las variedades reales están en los hechos, con 14 grafías en H00_VolumenCampo '
    '(POP y SEKOYA POP son la misma) — hallazgo N-6.';
COMMENT ON COLUMN core.m_variedad.es_sentinel IS
    'true en "Sin identificar" (ADR-0005). `cosecha.variedad_id` apunta aquí en las 4 filas '
    'que solo existen en H01_ProdHistorica: esa tabla nunca tuvo columna de variedad, así que '
    'no es un fallo de resolución — el dato simplemente no existe en el origen (hallazgo N-15).';
COMMENT ON TABLE core.m_variedad_alias IS
    'Grafías observadas de cada variedad. Mismo patrón que fundo_alias.';

CREATE TABLE IF NOT EXISTS core.m_lote (
    lote_id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    modulo_id       smallint NOT NULL REFERENCES core.m_modulo(modulo_id),
    codigo          text NOT NULL,
    turno_id        smallint NOT NULL REFERENCES core.m_turno(turno_id),
    -- NOT NULL desde ADR-0005: con la fila centinela de variedad ya no hay motivo para que
    -- quede vacía. Verificado: las filas del maestro primario ya resolvían variedad antes
    -- de este cambio (0 nulos), así que la restricción no rechaza ningún lote existente.
    variedad_id     smallint NOT NULL REFERENCES core.m_variedad(variedad_id),
    area_ha         numeric(10,4) NOT NULL CHECK (area_ha >= 0),
    n_plantas       integer NOT NULL CHECK (n_plantas >= 0),
    fecha_siembra   date,
    maceta          text,
    tipo_fibra      text,
    key_map         text,
    es_ficticio     boolean NOT NULL DEFAULT false,
    es_sentinel     boolean NOT NULL DEFAULT false,
    origen          text NOT NULL DEFAULT 'maestro_vigente',
    creado_en       timestamptz NOT NULL DEFAULT now(),
    -- modulo_id ya lleva dentro el fundo y la empresa, así que esta clave equivale a
    -- (empresa, fundo, módulo, lote) y admite los 9 pares (módulo, lote) que el maestro
    -- repite entre las dos empresas.
    UNIQUE (modulo_id, codigo)
);

CREATE UNIQUE INDEX IF NOT EXISTS lote_un_sentinel ON core.m_lote ((true)) WHERE es_sentinel;

COMMENT ON TABLE core.m_lote IS
    'Unidad de gestión productiva: 882 lotes del maestro primario actual. La clave de negocio es '
    '(empresa, módulo, lote) — ADR-0003 — y aquí se expresa como UNIQUE (modulo_id, codigo) '
    'porque modulo_id ya determina fundo y empresa.';
COMMENT ON COLUMN core.m_lote.codigo IS
    'Código canónico L + 3 dígitos + sufijo opcional, producido por stg.fn_norm_lote. El '
    'origen escribe L11B y L011B para el mismo lote; sin normalizar, esas filas quedan '
    'huérfanas aunque el lote exista (hallazgo N-3).';
COMMENT ON COLUMN core.m_lote.es_ficticio IS
    'true para L000, que es un lote de encabezado o prueba presente en varios módulos con '
    'turno T00. Se conserva y se marca en lugar de eliminarlo en silencio.';
COMMENT ON COLUMN core.m_lote.key_map IS
    'Clave de ubicación en el mapa del fundo. 53 lotes la tienen nula en el origen, y de ahí '
    'que el cálculo de kk falle sin aviso en la consulta 0106_RaFloYem.';
COMMENT ON COLUMN core.m_lote.es_sentinel IS
    'true en el lote "Sin identificar" (ADR-0005): apunta al módulo y turno centinela, no a '
    'un fundo real. `forecast_semanal.lote_id` apunta aquí en las 23 filas donde el lote del '
    'origen no existe en el maestro vigente (hallazgo N-15) — antes quedaban con lote_id NULL '
    'Y duplicadas en cuarentena a la vez; ahora están en las dos, sin NULL.';

CREATE INDEX IF NOT EXISTS lote_modulo_idx ON core.m_lote (modulo_id);
CREATE INDEX IF NOT EXISTS lote_turno_idx ON core.m_lote (turno_id);
CREATE INDEX IF NOT EXISTS lote_codigo_idx ON core.m_lote (codigo);
CREATE INDEX IF NOT EXISTS modulo_codigo_idx ON core.m_modulo (codigo);
