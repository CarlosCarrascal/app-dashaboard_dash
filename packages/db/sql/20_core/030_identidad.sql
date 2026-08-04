-- ============================================================================
-- 20_core · 030 · Identidad: evaluadores, personas, usuarios y tareo
--
-- Corrige H-09: existe un maestro de 31 evaluadores que ninguna consulta usa, y el enlace se
-- diseñó por un código de 4 letras que no aparece en ninguna tabla de evaluación. Lo que sí
-- se captura en cada fila es el DNI, así que el enlace se hace por DNI.
--
-- La separación evaluador / usuario es deliberada: un evaluador es una persona del dominio y
-- un usuario es una identidad de acceso. El DNI es un atributo de la persona y **nunca** una
-- credencial.
-- ============================================================================

CREATE TABLE IF NOT EXISTS core.evaluador (
    evaluador_id    smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dni             text NOT NULL UNIQUE,
    nombres         text,
    apellidos       text,
    codigo          text,
    zona            text,
    celular         text,
    inicio_labores  date,
    nacimiento      date,
    activo          boolean NOT NULL DEFAULT true,
    en_maestro      boolean NOT NULL DEFAULT true,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    CHECK (dni ~ '^[0-9]{8}$' OR NOT en_maestro)
);

COMMENT ON TABLE core.evaluador IS
    'Evaluador de campo, enlazado por DNI — que es lo que efectivamente se captura (H-09). '
    'La variabilidad entre evaluadores es una fuente de error conocida en evaluación '
    'fenológica: el informe SEGUIMIENTO DE PERSONAL ya la mide con CV Evaluador, pero por su '
    'cuenta y sin este maestro (hallazgo B-5).';
COMMENT ON COLUMN core.evaluador.codigo IS
    'Código de 4 letras del maestro (Cod). Se conserva como atributo descriptivo: no aparece '
    'en ninguna tabla de evaluación y por tanto no sirve como clave.';
COMMENT ON COLUMN core.evaluador.en_maestro IS
    'false para los DNI que aparecen capturando datos pero no están en M_Evaluadores. Son 2 '
    'en E01_Ramas. Se crean para no perder la evaluación y se marcan para que Agronomía los '
    'complete.';
COMMENT ON COLUMN core.evaluador.inicio_labores IS
    'Fecha guardada como texto en el origen; aquí tipada. Permite responder si la calidad de '
    'las mediciones mejora con la antigüedad.';

CREATE TABLE IF NOT EXISTS core.tareo (
    tareo_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    documento       text NOT NULL,
    fecha           date NOT NULL,
    horas           numeric(6,2) NOT NULL CHECK (horas >= 0),
    nombre          text,
    labor           text,
    lote_id         integer REFERENCES core.lote(lote_id),
    evaluador_id    smallint REFERENCES core.evaluador(evaluador_id),
    origen_fila     integer,
    UNIQUE (documento, fecha, labor)
);

COMMENT ON TABLE core.tareo IS
    'Horas-hombre por documento y fecha, de Query Tareo 2026.xlsx. Es el origen de las medidas '
    'de productividad del informe SEGUIMIENTO DE PERSONAL (Flores por Hora, Frutos por Hora, '
    'Jornadas Evaluador). Sin este dominio ese informe seguiría dependiendo de un Excel en la '
    'carpeta de un equipo personal (hallazgo B-1).';
COMMENT ON COLUMN core.tareo.evaluador_id IS
    'Enlace al evaluador por DNI, cuando existe. NULL para personal que no evalúa.';

CREATE INDEX IF NOT EXISTS tareo_fecha_idx ON core.tareo (fecha);
CREATE INDEX IF NOT EXISTS tareo_evaluador_idx ON core.tareo (evaluador_id);

-- ── Acceso a la aplicación ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS core.rol (
    rol_id          smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo          text NOT NULL UNIQUE,
    descripcion     text NOT NULL
);

CREATE TABLE IF NOT EXISTS core.usuario (
    usuario_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email           text NOT NULL UNIQUE,
    nombre          text NOT NULL,
    hash_password   text,
    rol_id          smallint NOT NULL REFERENCES core.rol(rol_id),
    evaluador_id    smallint REFERENCES core.evaluador(evaluador_id),
    activo          boolean NOT NULL DEFAULT true,
    ultimo_acceso   timestamptz,
    creado_en       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE core.usuario IS
    'Identidad de acceso a la aplicación. NO reemplaza a core.evaluador: un evaluador es una '
    'persona del dominio y un usuario es una forma de entrar al sistema. Un usuario puede '
    'apuntar al evaluador que representa, pero el DNI no se almacena aquí ni se usa como '
    'contraseña.';
COMMENT ON COLUMN core.usuario.hash_password IS
    'Hash de la contraseña. NULL cuando la autenticación es externa (SSO).';

INSERT INTO core.rol (codigo, descripcion) VALUES
    ('admin',     'Administra maestros, usuarios y cargas'),
    ('agronomo',  'Consulta todo y corrige evaluaciones'),
    ('evaluador', 'Captura evaluaciones de campo'),
    ('lectura',   'Solo consulta')
ON CONFLICT (codigo) DO NOTHING;
