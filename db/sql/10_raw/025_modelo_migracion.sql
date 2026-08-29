-- ============================================================================
-- 025 · Catálogo semántico y ejecución por bloques
--
-- El catálogo técnico de Access describe el origen físico. Estas tablas describen la
-- decisión de modelado y su evidencia, sin convertir automáticamente una fuente en una
-- tabla core. El contrato semántico se siembra desde etl/aquanqa_etl/modelo.py para que la
-- definición viva versionada en código y la base conserve la evidencia de qué contrato se
-- utilizó en cada ejecución.
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw.migracion_modelo_version (
    modelo_version text PRIMARY KEY,
    hash_modelo    char(64) NOT NULL,
    estado         text NOT NULL CHECK (estado IN ('borrador', 'aprobado', 'retirado')),
    vigente        boolean NOT NULL DEFAULT false,
    descripcion    text NOT NULL,
    contrato       jsonb NOT NULL DEFAULT '{}'::jsonb,
    creado_en      timestamptz NOT NULL DEFAULT now(),
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    aprobado_en    timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS migracion_modelo_una_vigente
    ON raw.migracion_modelo_version ((vigente))
    WHERE vigente;

COMMENT ON TABLE raw.migracion_modelo_version IS
    'Versiones del contrato semántico Access → raw/stg/core. Una sola versión puede estar vigente; '
    'las anteriores se conservan para reproducir decisiones históricas.';

CREATE TABLE IF NOT EXISTS raw.migracion_modelo_bloque (
    modelo_version  text NOT NULL REFERENCES raw.migracion_modelo_version(modelo_version),
    bloque          text NOT NULL,
    orden           smallint NOT NULL CHECK (orden > 0),
    nombre          text NOT NULL,
    tablas_raw      text[] NOT NULL DEFAULT '{}',
    prerequisitos   text[] NOT NULL DEFAULT '{}',
    cargable        boolean NOT NULL DEFAULT true,
    notas           text,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    actualizado_en  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (modelo_version, bloque),
    UNIQUE (modelo_version, orden)
);

COMMENT ON TABLE raw.migracion_modelo_bloque IS
    'Orden y composición de los bloques. B06 puede ser raw_only: que no sea cargable a core '
    'es una decisión explícita, no una fuente olvidada.';

CREATE TABLE IF NOT EXISTS raw.migracion_modelo_tabla (
    modelo_version  text NOT NULL,
    tabla_raw       text NOT NULL REFERENCES raw.migracion_plan_access(tabla_raw),
    bloque          text NOT NULL,
    dominio         text NOT NULL,
    rol             text NOT NULL,
    grano           text NOT NULL,
    decision        text NOT NULL CHECK (decision IN ('core', 'raw_only')),
    stg_objetos     text[] NOT NULL DEFAULT '{}',
    core_objetos    text[] NOT NULL DEFAULT '{}',
    depende_de      text[] NOT NULL DEFAULT '{}',
    claves_candidatas jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidencia       text[] NOT NULL DEFAULT '{}',
    notas           text,
    fuente_maestra  boolean NOT NULL DEFAULT false,
    estado          text NOT NULL CHECK (estado IN ('propuesto', 'aprobado', 'retirado')),
    creado_en       timestamptz NOT NULL DEFAULT now(),
    actualizado_en  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (modelo_version, tabla_raw),
    FOREIGN KEY (modelo_version, bloque)
        REFERENCES raw.migracion_modelo_bloque(modelo_version, bloque)
);

COMMENT ON TABLE raw.migracion_modelo_tabla IS
    'Decisión semántica por fuente Access. El número de filas aquí siempre es 23 fuentes; '
    'los objetos core pueden ser cero, uno o varios.';

CREATE INDEX IF NOT EXISTS migracion_modelo_tabla_bloque_idx
    ON raw.migracion_modelo_tabla (modelo_version, bloque, decision);

CREATE TABLE IF NOT EXISTS raw.migracion_modelo_relacion (
    modelo_version          text NOT NULL,
    codigo                  text NOT NULL,
    padre_raw               text NOT NULL,
    hijo_raw                text NOT NULL,
    columnas_padre          text[] NOT NULL,
    columnas_hijo           text[] NOT NULL,
    cardinalidad_esperada   text NOT NULL CHECK (cardinalidad_esperada IN ('1:1', '1:N', 'N:1', 'N:N')),
    metodo                  text NOT NULL,
    evidencia               text[] NOT NULL DEFAULT '{}',
    estado                  text NOT NULL CHECK (estado IN ('candidata', 'aprobada', 'rechazada', 'bloqueada')),
    notas                   text,
    creado_en               timestamptz NOT NULL DEFAULT now(),
    actualizado_en          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (modelo_version, codigo),
    FOREIGN KEY (modelo_version, padre_raw)
        REFERENCES raw.migracion_modelo_tabla(modelo_version, tabla_raw),
    FOREIGN KEY (modelo_version, hijo_raw)
        REFERENCES raw.migracion_modelo_tabla(modelo_version, tabla_raw),
    CHECK (cardinality(columnas_padre) = cardinality(columnas_hijo))
);

COMMENT ON TABLE raw.migracion_modelo_relacion IS
    'Relaciones candidatas. Solo una relación con evidencia y aprobación puede convertirse en '
    'FK de core; los nombres parecidos o el prefijo M_/E_/H_ no son evidencia suficiente.';

CREATE INDEX IF NOT EXISTS migracion_modelo_relacion_estado_idx
    ON raw.migracion_modelo_relacion (modelo_version, estado, padre_raw, hijo_raw);

CREATE TABLE IF NOT EXISTS raw.migracion_relacion_evidencia (
    evidencia_id             bigserial PRIMARY KEY,
    modelo_version           text NOT NULL,
    codigo_relacion          text NOT NULL,
    source_snapshot_id       bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    estado                    text NOT NULL CHECK (estado IN (
        'pendiente', 'validada', 'con_huerfanos', 'no_evaluable', 'rechazada'
    )),
    filas_padre               bigint,
    claves_padre              bigint,
    claves_padre_duplicadas   bigint,
    filas_hijo                bigint,
    filas_hijo_con_match      bigint,
    filas_hijo_huerfanas      bigint,
    cardinalidad_observada    text,
    metodo                    text NOT NULL,
    detalle                   text,
    consulta                  text,
    calculada_en              timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (modelo_version, codigo_relacion)
        REFERENCES raw.migracion_modelo_relacion(modelo_version, codigo)
);

CREATE INDEX IF NOT EXISTS migracion_relacion_evidencia_ultima_idx
    ON raw.migracion_relacion_evidencia
       (modelo_version, codigo_relacion, source_snapshot_id, calculada_en DESC);

COMMENT ON TABLE raw.migracion_relacion_evidencia IS
    'Resultado reproducible del perfilado de una relación para un snapshot. La ausencia de '
    'huérfanos se registra, pero nunca se deduce una aprobación automáticamente.';

-- Enlaza el ledger existente con la decisión semántica exacta usada para abrirlo.
ALTER TABLE raw.migracion_run
    ADD COLUMN IF NOT EXISTS modelo_version text,
    ADD COLUMN IF NOT EXISTS bloque_principal text;

ALTER TABLE raw.migracion_tabla
    ADD COLUMN IF NOT EXISTS modelo_version text,
    ADD COLUMN IF NOT EXISTS bloque text,
    ADD COLUMN IF NOT EXISTS decision_modelo text;

CREATE INDEX IF NOT EXISTS migracion_run_modelo_idx
    ON raw.migracion_run (modelo_version, source_snapshot_id, iniciado_en DESC);

CREATE INDEX IF NOT EXISTS migracion_tabla_modelo_bloque_idx
    ON raw.migracion_tabla (modelo_version, bloque, estado);

CREATE TABLE IF NOT EXISTS raw.migracion_bloque_ejecucion (
    bloque_ejecucion_id   bigserial PRIMARY KEY,
    modelo_version        text NOT NULL,
    source_snapshot_id    bigint NOT NULL REFERENCES raw.source_snapshot(source_snapshot_id),
    migracion_run_id      bigint REFERENCES raw.migracion_run(migracion_run_id),
    bloque                text NOT NULL,
    orden                 smallint NOT NULL,
    estado                text NOT NULL DEFAULT 'iniciado'
                          CHECK (estado IN ('iniciado', 'en_proceso', 'validado', 'publicado',
                                            'fallido', 'cancelado')),
    tablas_plan            text[] NOT NULL DEFAULT '{}',
    filas_raw              bigint,
    filas_stg              bigint,
    filas_core             bigint,
    filas_cuarentena       bigint NOT NULL DEFAULT 0 CHECK (filas_cuarentena >= 0),
    ejecutado_por          text NOT NULL DEFAULT current_user,
    detalle                text,
    iniciado_en            timestamptz NOT NULL DEFAULT now(),
    finalizado_en          timestamptz,
    FOREIGN KEY (modelo_version, bloque)
        REFERENCES raw.migracion_modelo_bloque(modelo_version, bloque),
    UNIQUE (modelo_version, source_snapshot_id, bloque)
);

-- Se conserva una sola ejecución activa, pero los intentos fallidos o cancelados deben
-- quedar auditados y poder repetirse con un nuevo bloque_ejecucion_id. La unicidad histórica
-- impedía reintentar sin borrar evidencia.
ALTER TABLE raw.migracion_bloque_ejecucion
    DROP CONSTRAINT IF EXISTS migracion_bloque_ejecucion_modelo_version_source_snapshot_i_key;

CREATE UNIQUE INDEX IF NOT EXISTS migracion_bloque_ejecucion_activa_uk
    ON raw.migracion_bloque_ejecucion (modelo_version, source_snapshot_id, bloque)
    WHERE estado IN ('iniciado', 'en_proceso');

COMMENT ON TABLE raw.migracion_bloque_ejecucion IS
    'Check-to-check por bloque. Impide repetir accidentalmente un bloque y deja claro qué '
    'fuentes se publicaron juntas y con qué snapshot.';

CREATE OR REPLACE VIEW raw.v_migracion_modelo_actual AS
SELECT modelo_version, hash_modelo, estado, vigente, descripcion, creado_en, actualizado_en,
       aprobado_en
FROM raw.migracion_modelo_version
WHERE vigente AND estado = 'aprobado';

CREATE OR REPLACE VIEW raw.v_migracion_modelo_tablas AS
SELECT t.*
FROM raw.migracion_modelo_tabla t
JOIN raw.v_migracion_modelo_actual v USING (modelo_version)
ORDER BY (SELECT b.orden FROM raw.migracion_modelo_bloque b
          WHERE b.modelo_version = t.modelo_version AND b.bloque = t.bloque), t.tabla_raw;

CREATE OR REPLACE VIEW raw.v_migracion_modelo_relaciones AS
SELECT r.*,
       e.estado AS ultima_evidencia,
       e.filas_hijo_huerfanas AS ultimas_filas_huerfanas,
       e.calculada_en AS ultima_evidencia_en
FROM raw.migracion_modelo_relacion r
JOIN raw.v_migracion_modelo_actual v USING (modelo_version)
LEFT JOIN LATERAL (
    SELECT x.estado, x.filas_hijo_huerfanas, x.calculada_en
    FROM raw.migracion_relacion_evidencia x
    WHERE x.modelo_version = r.modelo_version
      AND x.codigo_relacion = r.codigo
    ORDER BY x.calculada_en DESC, x.evidencia_id DESC
    LIMIT 1
) e ON true
ORDER BY r.padre_raw, r.hijo_raw, r.codigo;

CREATE OR REPLACE VIEW raw.v_migracion_bloques AS
SELECT b.modelo_version,
       b.bloque,
       b.orden,
       b.nombre,
       b.tablas_raw,
       b.prerequisitos,
       b.cargable,
       x.bloque_ejecucion_id,
       x.source_snapshot_id,
       x.estado,
       x.filas_raw,
       x.filas_stg,
       x.filas_core,
       x.filas_cuarentena,
       x.ejecutado_por,
       x.iniciado_en,
       x.finalizado_en,
       x.detalle,
       x.migracion_run_id
FROM raw.migracion_modelo_bloque b
JOIN raw.v_migracion_modelo_actual v USING (modelo_version)
LEFT JOIN LATERAL (
    SELECT e.*
    FROM raw.migracion_bloque_ejecucion e
    WHERE e.modelo_version = b.modelo_version
      AND e.bloque = b.bloque
    ORDER BY e.iniciado_en DESC, e.bloque_ejecucion_id DESC
    LIMIT 1
) x ON true
ORDER BY b.orden;

CREATE OR REPLACE FUNCTION raw.fn_modelo_version_vigente()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT modelo_version FROM raw.v_migracion_modelo_actual LIMIT 1;
$$;

COMMENT ON FUNCTION raw.fn_modelo_version_vigente() IS
    'Devuelve el único contrato semántico aprobado y vigente para iniciar bloques.';

CREATE OR REPLACE FUNCTION raw.fn_iniciar_bloque(
    p_source_snapshot_id bigint,
    p_bloque text,
    p_ejecutado_por text DEFAULT current_user,
    p_detalle text DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_modelo text;
    v_orden smallint;
    v_tablas text[];
    v_cargable boolean;
    v_prerequisito text;
    v_run bigint;
    v_id bigint;
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION 'Bloque bloqueado: la BD actual es %, se exige aquanqa_migracion.', current_database();
    END IF;

    v_modelo := raw.fn_modelo_version_vigente();
    IF v_modelo IS NULL THEN
        RAISE EXCEPTION 'No existe un modelo semántico aprobado y vigente.';
    END IF;

    SELECT orden, tablas_raw, cargable
      INTO v_orden, v_tablas, v_cargable
    FROM raw.migracion_modelo_bloque
    WHERE modelo_version = v_modelo AND bloque = p_bloque;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El bloque % no existe en el modelo %.', p_bloque, v_modelo;
    END IF;
    IF NOT v_cargable THEN
        RAISE EXCEPTION 'El bloque % es raw_only y no puede publicarse en core.', p_bloque;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM raw.v_snapshot_publicado
        WHERE tipo = 'access'
          AND source_snapshot_id = p_source_snapshot_id
    ) THEN
        RAISE EXCEPTION 'El snapshot Access % no está publicado; no se puede iniciar el bloque.', p_source_snapshot_id;
    END IF;

    -- Cada bloque debe quedar asociado al run incremental que lo está ejecutando. Se
    -- resuelve aquí porque los scripts abren el bloque antes de fijar los GUC de la sesión.
    SELECT max(r.migracion_run_id)
      INTO v_run
    FROM raw.migracion_run r
    WHERE r.source_snapshot_id = p_source_snapshot_id
      AND r.capa_destino = 'core'
      AND r.estado IN ('iniciado', 'en_proceso')
      AND r.modelo_version = v_modelo;

    IF v_run IS NULL THEN
        RAISE EXCEPTION
            'No existe un run incremental activo y enlazado al modelo % para el snapshot %.',
            v_modelo, p_source_snapshot_id;
    END IF;

    FOR v_prerequisito IN
        SELECT unnest(prerequisitos)
        FROM raw.migracion_modelo_bloque
        WHERE modelo_version = v_modelo AND bloque = p_bloque
    LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM raw.migracion_bloque_ejecucion e
            WHERE e.modelo_version = v_modelo
              AND e.source_snapshot_id = p_source_snapshot_id
              AND e.bloque = v_prerequisito
              AND e.estado = 'publicado'
        ) THEN
            RAISE EXCEPTION 'El prerequisito % del bloque % aún no está publicado.', v_prerequisito, p_bloque;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1 FROM raw.migracion_bloque_ejecucion
        WHERE modelo_version = v_modelo
          AND source_snapshot_id = p_source_snapshot_id
          AND bloque = p_bloque
          AND estado IN ('iniciado', 'en_proceso')
    ) THEN
        RAISE EXCEPTION 'Ya existe una ejecución activa para el bloque % y snapshot %.', p_bloque, p_source_snapshot_id;
    END IF;

    IF EXISTS (
        SELECT 1 FROM raw.migracion_bloque_ejecucion
        WHERE modelo_version = v_modelo
          AND source_snapshot_id = p_source_snapshot_id
          AND bloque = p_bloque
          AND estado = 'publicado'
    ) THEN
        RAISE EXCEPTION
            'El bloque % ya fue publicado para el snapshot %; use un snapshot/modelo nuevo para reconstruirlo.',
            p_bloque, p_source_snapshot_id;
    END IF;

    INSERT INTO raw.migracion_bloque_ejecucion
        (modelo_version, source_snapshot_id, migracion_run_id, bloque, orden, tablas_plan,
         ejecutado_por, detalle, estado)
    VALUES
        (v_modelo, p_source_snapshot_id, v_run, p_bloque, v_orden, v_tablas,
         coalesce(nullif(p_ejecutado_por, ''), current_user), p_detalle, 'iniciado')
    RETURNING bloque_ejecucion_id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION raw.fn_iniciar_bloque(bigint, text, text, text) IS
    'Abre un bloque contra el snapshot Access publicado, respeta prerequisitos, lo enlaza al run '
    'incremental activo y evita ejecuciones duplicadas.';

CREATE OR REPLACE PROCEDURE raw.sp_registrar_bloque(
    p_bloque_ejecucion_id bigint,
    p_estado text,
    p_filas_raw bigint DEFAULT NULL,
    p_filas_stg bigint DEFAULT NULL,
    p_filas_core bigint DEFAULT NULL,
    p_filas_cuarentena bigint DEFAULT 0,
    p_detalle text DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_estado NOT IN ('iniciado', 'en_proceso', 'validado', 'publicado', 'fallido', 'cancelado') THEN
        RAISE EXCEPTION 'Estado de bloque no permitido: %', p_estado;
    END IF;
    IF p_estado IN ('validado', 'publicado')
       AND (p_filas_raw IS NULL OR p_filas_stg IS NULL OR p_filas_core IS NULL) THEN
        RAISE EXCEPTION 'Un bloque validado/publicado necesita filas raw, stg y core.';
    END IF;
    IF p_estado = 'publicado'
       AND coalesce(p_filas_cuarentena, 0) > 0
       AND coalesce(p_detalle, '') !~* 'observaci[oó]n' THEN
        RAISE EXCEPTION
            'Un bloque con cuarentena solo puede publicarse con observaciones explícitas en el detalle.';
    END IF;

    UPDATE raw.migracion_bloque_ejecucion
       SET estado = p_estado,
           filas_raw = p_filas_raw,
           filas_stg = p_filas_stg,
           filas_core = p_filas_core,
           filas_cuarentena = coalesce(p_filas_cuarentena, 0),
           detalle = p_detalle,
           finalizado_en = CASE
               WHEN p_estado IN ('validado', 'publicado', 'fallido', 'cancelado')
               THEN now() ELSE NULL END
     WHERE bloque_ejecucion_id = p_bloque_ejecucion_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No existe la ejecución de bloque %.', p_bloque_ejecucion_id;
    END IF;
END;
$$;

COMMENT ON PROCEDURE raw.sp_registrar_bloque(bigint, text, bigint, bigint, bigint, bigint, text) IS
    'Cierra o actualiza el check-to-check de un bloque con conteos y evidencia.';
