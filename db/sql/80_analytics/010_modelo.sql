-- ============================================================================
-- 80_analytics · 010 · Gobierno y resultados analíticos
--
-- MLflow conserva el detalle técnico de entrenamiento. Estas tablas son el contrato de
-- negocio estable: una aplicación puede auditar una cifra sin conocer el esquema interno
-- ni la versión de MLflow.
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics.dataset_snapshot (
    snapshot_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    creado_en         timestamptz NOT NULL DEFAULT now(),
    fuente            text NOT NULL CHECK (fuente IN ('postgres', 'excel', 'fixture')),
    firma              text NOT NULL UNIQUE,
    corte_datos        timestamptz,
    esquema_version    text NOT NULL,
    tablas             jsonb NOT NULL DEFAULT '{}'::jsonb,
    cobertura          jsonb NOT NULL DEFAULT '{}'::jsonb,
    advertencias       jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS analytics.forecast_run (
    run_id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id        bigint NOT NULL REFERENCES analytics.dataset_snapshot(snapshot_id),
    mlflow_run_id      text,
    tipo               text NOT NULL CHECK (tipo IN ('relations', 'backtest', 'train', 'project', 'export')),
    estado             text NOT NULL DEFAULT 'created'
                       CHECK (estado IN ('created', 'running', 'succeeded', 'failed', 'published')),
    codigo_commit      text,
    configuracion      jsonb NOT NULL DEFAULT '{}'::jsonb,
    inicio             timestamptz NOT NULL DEFAULT now(),
    fin                timestamptz,
    error              text
);

-- Evidencia de paridad del modelo operativo Excel/Access. Esta tabla es independiente
-- de forecast_run porque una validación de fuente puede ocurrir antes de emitir una corrida.
CREATE TABLE IF NOT EXISTS analytics.operational_model_validation (
    validation_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id             bigint REFERENCES analytics.forecast_run(run_id) ON DELETE SET NULL,
    modelo             text NOT NULL,
    creado_en          timestamptz NOT NULL DEFAULT now(),
    estado             text NOT NULL CHECK (estado IN (
        'validado', 'fuente_inconsistente', 'mismatch', 'no_evaluable'
    )),
    archivo             text NOT NULL,
    sha256              text NOT NULL,
    filas_fuente        integer NOT NULL DEFAULT 0 CHECK (filas_fuente >= 0),
    filas_motor         integer NOT NULL DEFAULT 0 CHECK (filas_motor >= 0),
    diferencias_filas   integer NOT NULL DEFAULT 0 CHECK (diferencias_filas >= 0),
    max_diferencia      jsonb NOT NULL DEFAULT '{}'::jsonb,
    advertencias        jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadatos           jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_operational_model_validation_modelo_fecha
    ON analytics.operational_model_validation (modelo, creado_en DESC);

-- Migración idempotente para instalaciones creadas antes del comando analytics:export.
DO $$
DECLARE
    v_constraint text;
BEGIN
    SELECT conname INTO v_constraint
    FROM pg_constraint
    WHERE conrelid = 'analytics.forecast_run'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%tipo%relations%backtest%train%project%';
    IF v_constraint IS NOT NULL THEN
        EXECUTE format('ALTER TABLE analytics.forecast_run DROP CONSTRAINT %I', v_constraint);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'analytics.forecast_run'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%export%'
    ) THEN
        ALTER TABLE analytics.forecast_run
            ADD CONSTRAINT forecast_run_tipo_check
            CHECK (tipo IN ('relations', 'backtest', 'train', 'project', 'export'));
    END IF;
END $$;

-- Contrato inmutable del universo usado para comparar modelos. Una corrida que termina
-- correctamente no queda certificada por ese solo hecho: primero debe vincularse a un
-- contrato aprobado que fija snapshot, calendario cerrado, horizontes y denominador real.
CREATE TABLE IF NOT EXISTS analytics.evaluation_contract (
    evaluation_contract_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    firma                   text NOT NULL UNIQUE
                            CHECK (firma ~ '^[0-9a-f]{64}$'),
    campania                text NOT NULL CHECK (btrim(campania) <> ''),
    snapshot_id             bigint NOT NULL
                            REFERENCES analytics.dataset_snapshot(snapshot_id)
                            ON DELETE RESTRICT,
    granularidad            text NOT NULL DEFAULT 'lote_semana'
                            CHECK (granularidad IN (
                                'lote_semana', 'lote_emision_semana', 'fundo_semana',
                                'empresa_semana', 'empresa_mes', 'campania'
                            )),
    fecha_inicio_objetivo   date,
    fecha_fin_objetivo      date,
    cerrado_hasta           date,
    horizontes_semanas      smallint[] NOT NULL DEFAULT '{}'::smallint[],
    emisiones_elegibles     jsonb NOT NULL DEFAULT '[]'::jsonb
                            CHECK (jsonb_typeof(emisiones_elegibles) = 'array'),
    semanas_cerradas        jsonb NOT NULL DEFAULT '[]'::jsonb
                            CHECK (jsonb_typeof(semanas_cerradas) = 'array'),
    keyset_sha256           text CHECK (
                                keyset_sha256 IS NULL
                                OR keyset_sha256 ~ '^[0-9a-f]{64}$'
                            ),
    closed_calendar_sha256  text CHECK (
                                closed_calendar_sha256 IS NULL
                                OR closed_calendar_sha256 ~ '^[0-9a-f]{64}$'
                            ),
    volumen_real_kg         double precision CHECK (
                                volumen_real_kg IS NULL OR volumen_real_kg >= 0
                            ),
    n_unidades              bigint NOT NULL DEFAULT 0 CHECK (n_unidades >= 0),
    n_emisiones             integer NOT NULL DEFAULT 0 CHECK (n_emisiones >= 0),
    estado                  text NOT NULL DEFAULT 'draft'
                            CHECK (estado IN ('draft', 'approved', 'rejected', 'withdrawn')),
    metadatos               jsonb NOT NULL DEFAULT '{}'::jsonb
                            CHECK (jsonb_typeof(metadatos) = 'object'),
    creado_en               timestamptz NOT NULL DEFAULT now(),
    creado_por              text,
    aprobado_en             timestamptz,
    aprobado_por            text,
    CONSTRAINT uq_evaluation_contract_scope
        UNIQUE (evaluation_contract_id, campania, snapshot_id),
    CONSTRAINT ck_evaluation_contract_fechas
        CHECK (
            fecha_inicio_objetivo IS NULL
            OR fecha_fin_objetivo IS NULL
            OR fecha_inicio_objetivo <= fecha_fin_objetivo
        ),
    CONSTRAINT ck_evaluation_contract_aprobado_completo
        CHECK (
            estado <> 'approved'
            OR (
                fecha_inicio_objetivo IS NOT NULL
                AND fecha_fin_objetivo IS NOT NULL
                AND cerrado_hasta IS NOT NULL
                AND cerrado_hasta >= fecha_fin_objetivo
                AND cardinality(horizontes_semanas) > 0
                AND jsonb_array_length(semanas_cerradas) > 0
                AND keyset_sha256 IS NOT NULL
                AND closed_calendar_sha256 IS NOT NULL
                AND volumen_real_kg IS NOT NULL
                AND n_unidades > 0
                AND n_emisiones > 0
                AND aprobado_en IS NOT NULL
            )
        )
);

ALTER TABLE analytics.evaluation_contract
    DROP CONSTRAINT IF EXISTS evaluation_contract_granularidad_check;
ALTER TABLE analytics.evaluation_contract
    ADD CONSTRAINT evaluation_contract_granularidad_check
    CHECK (granularidad IN (
        'lote_semana', 'lote_emision_semana', 'fundo_semana',
        'empresa_semana', 'empresa_mes', 'campania'
    ));

CREATE INDEX IF NOT EXISTS ix_evaluation_contract_campania_estado
    ON analytics.evaluation_contract (campania, estado, cerrado_hasta DESC);

-- Permite garantizar que la release y su corrida apuntan al mismo snapshot sin usar un
-- trigger. run_id ya es único; el índice compuesto existe para la FK de gobierno.
CREATE UNIQUE INDEX IF NOT EXISTS ux_forecast_run_run_snapshot
    ON analytics.forecast_run (run_id, snapshot_id);

-- Puntero explícito de publicación. Las predicciones continúan inmutables en su run; activar
-- una release solo decide qué versión certificada puede consumir reporting.
CREATE TABLE IF NOT EXISTS analytics.model_series_release (
    release_id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Una release histórica o de referencia siempre requiere contrato de evaluación.
    -- Una release operativa apunta a una emisión futura y, por definición, todavía no
    -- tiene un denominador real cerrado; por eso no se le fabrica un contrato falso.
    evaluation_contract_id  bigint,
    run_id                  bigint NOT NULL,
    snapshot_id             bigint NOT NULL,
    campania                text NOT NULL CHECK (btrim(campania) <> ''),
    modelo                  text NOT NULL CHECK (btrim(modelo) <> ''),
    version_modelo          text NOT NULL CHECK (btrim(version_modelo) <> ''),
    uso                     text NOT NULL
                            CHECK (uso IN (
                                'operativo', 'historico', 'referencia', 'screening'
                            )),
    estado                  text NOT NULL DEFAULT 'candidate'
                            CHECK (estado IN ('candidate', 'approved', 'rejected', 'withdrawn')),
    estado_evaluacion       text NOT NULL DEFAULT 'pending'
                            CHECK (estado_evaluacion IN (
                                'pending', 'passed', 'rejected', 'not_applicable'
                            )),
    activo                  boolean NOT NULL DEFAULT false,
    source_hash             text NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    predicciones_sha256     text CHECK (
                                predicciones_sha256 IS NULL
                                OR predicciones_sha256 ~ '^[0-9a-f]{64}$'
                            ),
    metadatos               jsonb NOT NULL DEFAULT '{}'::jsonb
                            CHECK (jsonb_typeof(metadatos) = 'object'),
    creado_en               timestamptz NOT NULL DEFAULT now(),
    creado_por              text,
    aprobado_en             timestamptz,
    aprobado_por            text,
    retirado_en             timestamptz,
    CONSTRAINT fk_model_series_release_contract_scope
        FOREIGN KEY (evaluation_contract_id, campania, snapshot_id)
        REFERENCES analytics.evaluation_contract (
            evaluation_contract_id, campania, snapshot_id
        ) ON DELETE RESTRICT,
    CONSTRAINT fk_model_series_release_run_snapshot
        FOREIGN KEY (run_id, snapshot_id)
        REFERENCES analytics.forecast_run (run_id, snapshot_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_model_series_release_snapshot
        FOREIGN KEY (snapshot_id)
        REFERENCES analytics.dataset_snapshot (snapshot_id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_model_series_release_version
        UNIQUE (
            evaluation_contract_id, run_id, campania, modelo, version_modelo, uso
        ),
    CONSTRAINT ck_model_series_release_activa_certificada
        CHECK (
            NOT activo
            OR (
                estado = 'approved'
                AND (
                    estado_evaluacion = 'passed'
                    OR (uso = 'operativo' AND estado_evaluacion = 'not_applicable')
                )
                AND aprobado_en IS NOT NULL
            )
        ),
    CONSTRAINT ck_model_series_release_contract_required
        CHECK (uso = 'operativo' OR evaluation_contract_id IS NOT NULL),
    CONSTRAINT ck_model_series_release_retiro
        CHECK (
            estado <> 'withdrawn'
            OR (NOT activo AND retirado_en IS NOT NULL)
        )
);

-- Migración idempotente desde la primera versión, que exigía contrato incluso para
-- una proyección futura. El contrato sigue siendo obligatorio para histórico/R09.
ALTER TABLE analytics.model_series_release
    ALTER COLUMN evaluation_contract_id DROP NOT NULL;
ALTER TABLE analytics.model_series_release
    DROP CONSTRAINT IF EXISTS model_series_release_uso_check;
ALTER TABLE analytics.model_series_release
    ADD CONSTRAINT model_series_release_uso_check
    CHECK (uso IN ('operativo', 'historico', 'referencia', 'screening'));
ALTER TABLE analytics.model_series_release
    DROP CONSTRAINT IF EXISTS ck_model_series_release_activa_certificada;
ALTER TABLE analytics.model_series_release
    ADD CONSTRAINT ck_model_series_release_activa_certificada
    CHECK (
        NOT activo
        OR (
            estado = 'approved'
            AND (
                estado_evaluacion = 'passed'
                OR (uso = 'operativo' AND estado_evaluacion = 'not_applicable')
            )
            AND aprobado_en IS NOT NULL
        )
    );
ALTER TABLE analytics.model_series_release
    DROP CONSTRAINT IF EXISTS ck_model_series_release_contract_required;
ALTER TABLE analytics.model_series_release
    ADD CONSTRAINT ck_model_series_release_contract_required
    CHECK (uso = 'operativo' OR evaluation_contract_id IS NOT NULL);

-- Regla pedida: solo una release activa por campaña, modelo y uso. Una corrida challenger
-- puede quedar persistida como candidate/rejected sin desplazar la serie publicada.
CREATE UNIQUE INDEX IF NOT EXISTS ux_model_series_release_activa
    ON analytics.model_series_release (campania, modelo, uso)
    WHERE activo;
CREATE UNIQUE INDEX IF NOT EXISTS ux_model_series_release_operativa_version
    ON analytics.model_series_release (run_id, campania, modelo, version_modelo, uso)
    WHERE uso = 'operativo';

CREATE INDEX IF NOT EXISTS ix_model_series_release_contract
    ON analytics.model_series_release (
        evaluation_contract_id, campania, modelo, uso, estado
    );
CREATE INDEX IF NOT EXISTS ix_model_series_release_run
    ON analytics.model_series_release (run_id, modelo, version_modelo);

COMMENT ON TABLE analytics.evaluation_contract IS
    'Universo inmutable y cerrado para comparar modelos: snapshot, semanas, horizontes, denominador y hashes.';
COMMENT ON TABLE analytics.model_series_release IS
    'Puntero gobernado a una serie persistida. succeeded no implica approved, evaluation_passed ni publicación.';
COMMENT ON COLUMN analytics.model_series_release.version_modelo IS
    'Versión exacta publicada; usar sin_version para predicciones históricas cuyo version_modelo sea NULL.';

CREATE TABLE IF NOT EXISTS analytics.prediction (
    prediction_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id             bigint NOT NULL REFERENCES analytics.forecast_run(run_id) ON DELETE CASCADE,
    modelo             text NOT NULL,
    version_modelo     text,
    campania           text,
    empresa            text,
    fundo              text,
    modulo             text,
    lote               text,
    lote_id            bigint,
    fecha_emision      date NOT NULL,
    fecha_objetivo     date NOT NULL,
    horizonte_semanas  smallint NOT NULL CHECK (horizonte_semanas BETWEEN 0 AND 52),
    banda_horizonte    text NOT NULL CHECK (banda_horizonte IN ('operativo', 'planificacion', 'escenario')),
    version_fuente     text,
    p10_kg              double precision,
    p50_kg              double precision NOT NULL CHECK (p50_kg >= 0),
    p90_kg              double precision,
    real_kg             double precision,
    plantas             double precision,
    frutos_por_planta   double precision,
    peso_baya_g         double precision,
    confianza           text NOT NULL DEFAULT 'baja' CHECK (confianza IN ('alta', 'media', 'baja')),
    componentes         jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (p10_kg IS NULL OR p10_kg <= p50_kg),
    CHECK (p90_kg IS NULL OR p50_kg <= p90_kg),
    CONSTRAINT uq_prediction_lote_semana UNIQUE NULLS NOT DISTINCT
        (run_id, modelo, campania, lote_id, fecha_emision, fecha_objetivo, version_fuente)
);

-- El cierre intra-semanal no es una proyección h1 ni una predicción por lote.
-- Se emite después de observar lunes y martes y estima el total al cierre de la
-- misma semana. Mantenerlo en una tabla separada evita mezclar sus métricas con
-- las del plan de 1--10 semanas y permite reconciliar Empresa con los cuatro
-- fundos sin fabricar lote_id sintéticos.
CREATE TABLE IF NOT EXISTS analytics.weekly_nowcast (
    nowcast_id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id                 bigint NOT NULL
                           REFERENCES analytics.forecast_run(run_id) ON DELETE CASCADE,
    modelo                 text NOT NULL CHECK (btrim(modelo) <> ''),
    version_modelo         text NOT NULL CHECK (btrim(version_modelo) <> ''),
    campania               text NOT NULL CHECK (btrim(campania) <> ''),
    semana_inicio          date NOT NULL,
    semana_cierre          date NOT NULL,
    fecha_corte            date NOT NULL,
    fecha_emision          date NOT NULL,
    fundo                  text NOT NULL,
    kg_lun_mar             double precision NOT NULL CHECK (kg_lun_mar >= 0),
    p50_kg                 double precision NOT NULL CHECK (p50_kg >= 0),
    real_kg                double precision CHECK (real_kg IS NULL OR real_kg >= 0),
    macro_kg               double precision CHECK (macro_kg IS NULL OR macro_kg >= 0),
    r09_presemana_kg       double precision
                           CHECK (r09_presemana_kg IS NULL OR r09_presemana_kg >= 0),
    r09_misma_semana_kg    double precision
                           CHECK (r09_misma_semana_kg IS NULL OR r09_misma_semana_kg >= 0),
    estado_evaluacion      text NOT NULL DEFAULT 'pendiente'
                           CHECK (estado_evaluacion IN (
                               'evaluado', 'pendiente', 'no_evaluable'
                           )),
    componentes            jsonb NOT NULL DEFAULT '{}'::jsonb
                           CHECK (jsonb_typeof(componentes) = 'object'),
    creado_en              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_weekly_nowcast_scope UNIQUE
        (run_id, modelo, campania, semana_inicio, fundo),
    CONSTRAINT ck_weekly_nowcast_calendario CHECK (
        semana_cierre = semana_inicio + 6
        AND fecha_corte BETWEEN semana_inicio AND semana_cierre
        AND fecha_emision > fecha_corte
        AND fecha_emision <= semana_cierre
    ),
    CONSTRAINT ck_weekly_nowcast_evaluacion CHECK (
        estado_evaluacion <> 'evaluado' OR real_kg IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS ix_weekly_nowcast_campania_semana
    ON analytics.weekly_nowcast (campania, semana_inicio, modelo, fundo);

COMMENT ON TABLE analytics.weekly_nowcast IS
    'Estimación de cierre de la semana en curso usando exclusivamente avance real hasta el corte; no es forecast presemana.';

-- Migración para checkouts que alcanzaron a crear la primera versión con `lote` textual.
-- El código L001 se repite en módulos distintos (ADR-0003); lote_id es la identidad física.
DO $$
DECLARE
    v_constraint text;
BEGIN
    SELECT conname INTO v_constraint
    FROM pg_constraint
    WHERE conrelid = 'analytics.prediction'::regclass
      AND contype = 'u'
      AND pg_get_constraintdef(oid) LIKE '%campania, lote, fecha_emision%';
    IF v_constraint IS NOT NULL THEN
        EXECUTE format('ALTER TABLE analytics.prediction DROP CONSTRAINT %I', v_constraint);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'analytics.prediction'::regclass
          AND conname = 'uq_prediction_lote_semana'
    ) THEN
        ALTER TABLE analytics.prediction
            ADD CONSTRAINT uq_prediction_lote_semana UNIQUE NULLS NOT DISTINCT
            (run_id, modelo, campania, lote_id, fecha_emision, fecha_objetivo, version_fuente);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS analytics.metric (
    metric_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id              bigint NOT NULL REFERENCES analytics.forecast_run(run_id) ON DELETE CASCADE,
    modelo              text NOT NULL,
    metrica             text NOT NULL,
    valor               double precision,
    n                   integer NOT NULL DEFAULT 0 CHECK (n >= 0),
    campania            text,
    fundo               text,
    horizonte_semanas   smallint,
    banda_horizonte     text,
    intervalo_inferior  double precision,
    intervalo_superior  double precision,
    atributos           jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS analytics.evidence_claim (
    claim_id             text PRIMARY KEY,
    run_id               bigint REFERENCES analytics.forecast_run(run_id) ON DELETE SET NULL,
    hipotesis_id         text,
    hipotesis            text NOT NULL,
    clase_evidencia      text NOT NULL CHECK (
        clase_evidencia IN ('descriptiva', 'correlacional', 'temporal', 'predictiva', 'causal')
    ),
    estado               text NOT NULL CHECK (
        estado IN ('exploratorio', 'consistente', 'replicado', 'predictivo', 'causal')
    ),
    afirmacion           text NOT NULL,
    estimacion           double precision,
    intervalo_inferior   double precision,
    intervalo_superior   double precision,
    unidad               text,
    n_efectivo           double precision,
    alcance              jsonb NOT NULL DEFAULT '{}'::jsonb,
    supuestos            jsonb NOT NULL DEFAULT '[]'::jsonb,
    limitaciones         jsonb NOT NULL DEFAULT '[]'::jsonb,
    referencias          jsonb NOT NULL DEFAULT '[]'::jsonb,
    actualizado_en       timestamptz NOT NULL DEFAULT now(),
    CHECK (clase_evidencia <> 'causal' OR estado = 'causal')
);

ALTER TABLE analytics.evidence_claim
    ADD COLUMN IF NOT EXISTS hipotesis_id text;

DO $$
DECLARE
    v_constraint text;
BEGIN
    SELECT conname INTO v_constraint
    FROM pg_constraint
    WHERE conrelid = 'analytics.evidence_claim'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%estado%exploratorio%replicado%';
    IF v_constraint IS NOT NULL THEN
        EXECUTE format('ALTER TABLE analytics.evidence_claim DROP CONSTRAINT %I', v_constraint);
    END IF;
    ALTER TABLE analytics.evidence_claim
        ADD CONSTRAINT evidence_claim_estado_check
        CHECK (estado IN ('exploratorio', 'consistente', 'replicado', 'predictivo', 'causal'));
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

CREATE TABLE IF NOT EXISTS analytics.model_feature_evidence (
    feature_evidence_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id               bigint NOT NULL REFERENCES analytics.forecast_run(run_id) ON DELETE CASCADE,
    modelo               text NOT NULL,
    modelo_componente    text,
    predictor            text NOT NULL,
    objetivo             text NOT NULL,
    rezago               smallint,
    transformacion       text,
    hipotesis_id         text,
    claim_id             text REFERENCES analytics.evidence_claim(claim_id) ON DELETE SET NULL,
    hipotesis            text,
    referencias          jsonb NOT NULL DEFAULT '[]'::jsonb,
    metodo               text,
    papel                text NOT NULL CHECK (
        papel IN ('predictor_fundamentado', 'control', 'identificador', 'variable_operativa')
    ),
    estado               text NOT NULL,
    admitida             boolean NOT NULL DEFAULT false,
    cobertura            double precision CHECK (cobertura BETWEEN 0 AND 1),
    n_efectivo           double precision,
    estimacion           double precision,
    p_value              double precision,
    q_value              double precision,
    placebo              double precision,
    estabilidad_modulo   double precision,
    fecha_emision        date NOT NULL,
    limitacion           text NOT NULL,
    creado_en            timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, modelo, predictor, objetivo, fecha_emision)
);

ALTER TABLE analytics.model_feature_evidence
    ADD COLUMN IF NOT EXISTS referencias jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE analytics.model_feature_evidence
    ADD COLUMN IF NOT EXISTS claim_id text REFERENCES analytics.evidence_claim(claim_id)
    ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS analytics.projection_scenario (
    scenario_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre               text NOT NULL,
    modo_decision        text NOT NULL CHECK (modo_decision IN ('plan_semanal', 'poda_campania')),
    estado               text NOT NULL DEFAULT 'guardado' CHECK (
        estado IN ('guardado', 'en_revision', 'aprobado', 'publicado', 'reemplazado')
    ),
    run_base_id          bigint REFERENCES analytics.forecast_run(run_id) ON DELETE SET NULL,
    parametros           jsonb NOT NULL DEFAULT '{}'::jsonb,
    advertencias         jsonb NOT NULL DEFAULT '[]'::jsonb,
    creado_por           text,
    creado_en            timestamptz NOT NULL DEFAULT now(),
    actualizado_en       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analytics.projection_scenario_review (
    review_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scenario_id          bigint NOT NULL REFERENCES analytics.projection_scenario(scenario_id)
                         ON DELETE CASCADE,
    estado_anterior      text,
    estado_nuevo         text NOT NULL,
    comentario           text,
    actor                text,
    creado_en            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analytics.weather_forecast_snapshot (
    weather_snapshot_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id              bigint REFERENCES analytics.forecast_run(run_id) ON DELETE SET NULL,
    proveedor           text NOT NULL,
    endpoint            text NOT NULL,
    latitud             double precision NOT NULL CHECK (latitud BETWEEN -90 AND 90),
    longitud            double precision NOT NULL CHECK (longitud BETWEEN -180 AND 180),
    emitido_en          timestamptz NOT NULL,
    payload_sha256      char(64) NOT NULL,
    payload             jsonb NOT NULL,
    creado_en           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (proveedor, latitud, longitud, emitido_en, payload_sha256)
);

COMMENT ON TABLE analytics.weather_forecast_snapshot IS
    'Payload climático conocido al emitir; permite replay sin sustituirlo por clima observado futuro.';

CREATE TABLE IF NOT EXISTS analytics.model_decision (
    decision_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id               bigint REFERENCES analytics.forecast_run(run_id) ON DELETE SET NULL,
    banda_horizonte      text NOT NULL CHECK (banda_horizonte IN ('operativo', 'planificacion', 'escenario')),
    campeon              text NOT NULL,
    challenger           text,
    resultado            text NOT NULL CHECK (resultado IN ('retener', 'promover', 'experimental')),
    regla                jsonb NOT NULL,
    metricas             jsonb NOT NULL DEFAULT '{}'::jsonb,
    justificacion        text NOT NULL,
    vigente              boolean NOT NULL DEFAULT true,
    decidido_en          timestamptz NOT NULL DEFAULT now(),
    decidido_por         text
);

CREATE TABLE IF NOT EXISTS analytics.quality_result (
    quality_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id          bigint NOT NULL REFERENCES analytics.dataset_snapshot(snapshot_id) ON DELETE CASCADE,
    run_id               bigint REFERENCES analytics.forecast_run(run_id) ON DELETE CASCADE,
    regla                text NOT NULL,
    estado               text NOT NULL CHECK (estado IN ('ok', 'warning', 'error')),
    observados           bigint,
    afectados            bigint,
    detalle              jsonb NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE analytics.quality_result
    ADD COLUMN IF NOT EXISTS run_id bigint REFERENCES analytics.forecast_run(run_id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS analytics.artifact (
    artifact_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id               bigint NOT NULL REFERENCES analytics.forecast_run(run_id) ON DELETE CASCADE,
    tipo                 text NOT NULL,
    uri                  text NOT NULL,
    sha256               text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    bytes                bigint CHECK (bytes IS NULL OR bytes >= 0),
    creado_en            timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, tipo, sha256)
);

CREATE INDEX IF NOT EXISTS ix_prediction_vigente
    ON analytics.prediction (fecha_emision DESC, fecha_objetivo, banda_horizonte);

-- Vintage histórico: distingue la emisión que originó una predicción de la semana que se
-- está evaluando. Estas columnas hacen auditable el replay ciego y permiten construir la
-- curva histórica completa sin confundirla con una emisión única.
ALTER TABLE analytics.prediction
    ADD COLUMN IF NOT EXISTS origen_emision date;
ALTER TABLE analytics.prediction
    ADD COLUMN IF NOT EXISTS tipo_prediccion text NOT NULL DEFAULT 'operativa';
ALTER TABLE analytics.prediction
    ADD COLUMN IF NOT EXISTS es_replay_ciego boolean NOT NULL DEFAULT false;
ALTER TABLE analytics.prediction
    ADD COLUMN IF NOT EXISTS es_curva_stitched boolean NOT NULL DEFAULT false;
ALTER TABLE analytics.prediction
    ADD COLUMN IF NOT EXISTS estado_evaluacion text;

CREATE INDEX IF NOT EXISTS ix_prediction_vintage
    ON analytics.prediction (modelo, campania, lote_id, fecha_objetivo, fecha_emision);
CREATE INDEX IF NOT EXISTS ix_prediction_release_lookup
    ON analytics.prediction (
        run_id, modelo, campania, version_modelo, fecha_objetivo, lote_id
    );

-- Una release aprobada es inmutable. Las corridas se construyen primero y recién
-- después se aprueban; desde ese momento no se pueden insertar, alterar ni borrar
-- filas que cambiarían silenciosamente los KPI o la proyección operativa publicada.
CREATE OR REPLACE FUNCTION analytics.proteger_prediccion_publicada()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_run_id bigint;
    v_modelo text;
    v_campania text;
    v_version text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_run_id := OLD.run_id;
        v_modelo := OLD.modelo;
        v_campania := OLD.campania;
        v_version := COALESCE(NULLIF(OLD.version_modelo, ''), 'sin_version');
    ELSE
        v_run_id := NEW.run_id;
        v_modelo := NEW.modelo;
        v_campania := NEW.campania;
        v_version := COALESCE(NULLIF(NEW.version_modelo, ''), 'sin_version');
    END IF;

    IF EXISTS (
        SELECT 1
        FROM analytics.model_series_release l
        WHERE l.run_id = v_run_id
          AND l.modelo = v_modelo
          AND l.campania = v_campania
          AND l.version_modelo = v_version
          AND l.activo
          AND l.estado = 'approved'
    ) THEN
        RAISE EXCEPTION
            'La serie aprobada %/%/% (run %) es inmutable',
            v_campania, v_modelo, v_version, v_run_id;
    END IF;

    IF TG_OP = 'UPDATE' AND EXISTS (
        SELECT 1
        FROM analytics.model_series_release l
        WHERE l.run_id = OLD.run_id
          AND l.modelo = OLD.modelo
          AND l.campania = OLD.campania
          AND l.version_modelo = COALESCE(NULLIF(OLD.version_modelo, ''), 'sin_version')
          AND l.activo
          AND l.estado = 'approved'
    ) THEN
        RAISE EXCEPTION
            'La serie aprobada %/%/% (run %) es inmutable',
            OLD.campania, OLD.modelo,
            COALESCE(NULLIF(OLD.version_modelo, ''), 'sin_version'), OLD.run_id;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_proteger_prediccion_publicada ON analytics.prediction;
CREATE TRIGGER trg_proteger_prediccion_publicada
BEFORE INSERT OR UPDATE OR DELETE ON analytics.prediction
FOR EACH ROW EXECUTE FUNCTION analytics.proteger_prediccion_publicada();

-- La release activa también forma parte del contrato publicado. Se permite retirarla
-- para promover otra, pero no reescribir silenciosamente run, versión, hashes o metadatos.
CREATE OR REPLACE FUNCTION analytics.proteger_release_publicada()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.activo AND OLD.estado = 'approved' THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'La release aprobada % no puede borrarse; debe retirarse', OLD.release_id;
        END IF;
        IF NEW.evaluation_contract_id IS DISTINCT FROM OLD.evaluation_contract_id
           OR NEW.run_id IS DISTINCT FROM OLD.run_id
           OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id
           OR NEW.campania IS DISTINCT FROM OLD.campania
           OR NEW.modelo IS DISTINCT FROM OLD.modelo
           OR NEW.version_modelo IS DISTINCT FROM OLD.version_modelo
           OR NEW.uso IS DISTINCT FROM OLD.uso
           OR NEW.source_hash IS DISTINCT FROM OLD.source_hash
           OR NEW.predicciones_sha256 IS DISTINCT FROM OLD.predicciones_sha256
           OR NEW.metadatos IS DISTINCT FROM OLD.metadatos THEN
            RAISE EXCEPTION 'La identidad y huellas de la release aprobada % son inmutables',
                            OLD.release_id;
        END IF;
        IF NEW.activo OR NEW.estado <> 'withdrawn' OR NEW.retirado_en IS NULL THEN
            RAISE EXCEPTION 'La release aprobada % solo admite transición a withdrawn',
                            OLD.release_id;
        END IF;
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_proteger_release_publicada
    ON analytics.model_series_release;
CREATE TRIGGER trg_proteger_release_publicada
BEFORE UPDATE OR DELETE ON analytics.model_series_release
FOR EACH ROW EXECUTE FUNCTION analytics.proteger_release_publicada();
CREATE INDEX IF NOT EXISTS ix_metric_comparacion
    ON analytics.metric (run_id, banda_horizonte, modelo, metrica);

CREATE TABLE IF NOT EXISTS analytics.model_comparison_metric (
    comparison_metric_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id                bigint NOT NULL REFERENCES analytics.forecast_run(run_id)
                          ON DELETE CASCADE,
    modelo_base           text NOT NULL,
    modelo                text NOT NULL,
    banda_horizonte       text NOT NULL CHECK (
                              banda_horizonte IN ('operativo', 'planificacion', 'escenario')
                          ),
    n                     integer NOT NULL CHECK (n >= 0),
    wape                  double precision,
    mase                  double precision,
    mae_kg                double precision,
    sesgo_pct             double precision,
    cobertura_80          double precision,
    volumen_real_kg       double precision,
    universo              text NOT NULL,
    creado_en             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, modelo_base, modelo, banda_horizonte)
);

CREATE INDEX IF NOT EXISTS ix_model_comparison_metric_ultima
    ON analytics.model_comparison_metric (modelo_base, modelo, run_id DESC);

-- Parámetros de la curva tipo Excel usados en cada corte. La tabla no guarda kilos
-- calculados: conserva el prior, la corrección aprendida y su procedencia para poder
-- reproducir una emisión sin depender del libro abierto en el escritorio.
CREATE TABLE IF NOT EXISTS analytics.legacy_parameter_snapshot (
    parameter_snapshot_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id                  bigint NOT NULL REFERENCES analytics.forecast_run(run_id)
                            ON DELETE CASCADE,
    campania                text NOT NULL,
    fecha_emision           date NOT NULL,
    lote_id                 bigint NOT NULL,
    fundo                   text,
    modulo                  text,
    variedad                text,
    nivel_calibracion       text,
    n_observaciones_asof    integer NOT NULL DEFAULT 0 CHECK (n_observaciones_asof >= 0),
    fuente_parametros       text,
    archivo_fuente          text,
    sha256_fuente           text,
    parametros_base_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    correcciones_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    parametros_finales_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    gdd_base                double precision,
    gdd_ventana             integer,
    fecha_corte             date NOT NULL,
    creado_en               timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, campania, fecha_emision, lote_id)
);

CREATE INDEX IF NOT EXISTS ix_legacy_parameter_snapshot_lookup
    ON analytics.legacy_parameter_snapshot (campania, fecha_emision, lote_id);

COMMENT ON TABLE analytics.legacy_parameter_snapshot IS
    'Snapshot as-of de parámetros X/O/N/A/B, prior Excel, corrección y GDD; no contiene R09 como predictor.';
CREATE INDEX IF NOT EXISTS ix_claim_clase ON analytics.evidence_claim (clase_evidencia, estado);
CREATE INDEX IF NOT EXISTS ix_feature_evidence_run
    ON analytics.model_feature_evidence (run_id, objetivo, admitida);
CREATE INDEX IF NOT EXISTS ix_projection_scenario_estado
    ON analytics.projection_scenario (estado, actualizado_en DESC);
CREATE INDEX IF NOT EXISTS ix_quality_run ON analytics.quality_result (run_id, estado);
CREATE UNIQUE INDEX IF NOT EXISTS ux_model_decision_vigente
    ON analytics.model_decision (banda_horizonte) WHERE vigente;

COMMENT ON TABLE analytics.dataset_snapshot IS
    'Huella inmutable de las fuentes usadas por una ejecución; registra cobertura y fallback.';
COMMENT ON TABLE analytics.prediction IS
    'Pronóstico trazable al grano lote-semana. P10/P50/P90 son cuantiles, no límites causales.';
COMMENT ON TABLE analytics.model_comparison_metric IS
    'Métricas calculadas sobre el mismo universo de filas para una pareja baseline-challenger.';
COMMENT ON TABLE analytics.evidence_claim IS
    'Afirmaciones publicables con clase de evidencia y límites. Causal exige estado causal.';
COMMENT ON TABLE analytics.model_feature_evidence IS
    'Trazabilidad de cada feature al análisis recalculado dentro del fold; nunca implica causalidad.';
COMMENT ON TABLE analytics.projection_scenario IS
    'Escenarios guardados y gobernados. Mover controles en UI no crea una fila automáticamente.';
COMMENT ON TABLE analytics.model_decision IS
    'Decisión champion-challenger por banda de horizonte, con regla y métricas auditables.';
