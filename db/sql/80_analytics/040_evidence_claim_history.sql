-- ============================================================================
-- 80_analytics · 040 · Historial inmutable de claims
--
-- La tabla analytics.evidence_claim sigue siendo la tabla vigente que consume
-- el dashboard. Esta tabla adicional conserva una copia por corrida.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS analytics.evidence_claim_history (
    claim_id             text NOT NULL,
    run_id               bigint NOT NULL
                         REFERENCES analytics.forecast_run(run_id) ON DELETE RESTRICT,
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
    n_efectivo            double precision,
    alcance              jsonb NOT NULL DEFAULT '{}'::jsonb,
    supuestos             jsonb NOT NULL DEFAULT '[]'::jsonb,
    limitaciones          jsonb NOT NULL DEFAULT '[]'::jsonb,
    referencias           jsonb NOT NULL DEFAULT '[]'::jsonb,
    actualizado_en        timestamptz NOT NULL DEFAULT now(),
    registrado_en         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pk_evidence_claim_history PRIMARY KEY (claim_id, run_id),
    CONSTRAINT ck_evidence_claim_history_alcance_json
        CHECK (jsonb_typeof(alcance) = 'object'),
    CONSTRAINT ck_evidence_claim_history_supuestos_json
        CHECK (jsonb_typeof(supuestos) = 'array'),
    CONSTRAINT ck_evidence_claim_history_limitaciones_json
        CHECK (jsonb_typeof(limitaciones) = 'array'),
    CONSTRAINT ck_evidence_claim_history_referencias_json
        CHECK (jsonb_typeof(referencias) = 'array')
);

CREATE INDEX IF NOT EXISTS ix_evidence_claim_history_run
    ON analytics.evidence_claim_history (run_id, claim_id);

-- La tabla vigente no imponía el tipo semántico de estos JSONB.  Para que un
-- dato legacy no aborte la migración, se conserva dentro de un contenedor del
-- tipo esperado.  Así el valor original sigue siendo consultable en
-- la clave JSONB `_legacy_jsonb` y el histórico continúa cumpliendo sus checks.
DO $$
DECLARE
    v_alcance bigint;
    v_supuestos bigint;
    v_limitaciones bigint;
    v_referencias bigint;
BEGIN
    SELECT
        count(*) FILTER (WHERE jsonb_typeof(alcance) IS DISTINCT FROM 'object'),
        count(*) FILTER (WHERE jsonb_typeof(supuestos) IS DISTINCT FROM 'array'),
        count(*) FILTER (WHERE jsonb_typeof(limitaciones) IS DISTINCT FROM 'array'),
        count(*) FILTER (WHERE jsonb_typeof(referencias) IS DISTINCT FROM 'array')
    INTO v_alcance, v_supuestos, v_limitaciones, v_referencias
    FROM analytics.evidence_claim
    WHERE run_id IS NOT NULL;

    IF v_alcance > 0 THEN
        RAISE WARNING
            'evidence_claim_history: % claims tienen alcance JSONB legacy no objeto; se conservarán bajo alcance->''_legacy_jsonb''',
            v_alcance;
    END IF;
    IF v_supuestos > 0 THEN
        RAISE WARNING
            'evidence_claim_history: % claims tienen supuestos JSONB legacy no array; se conservarán bajo supuestos[0]->''_legacy_jsonb''',
            v_supuestos;
    END IF;
    IF v_limitaciones > 0 THEN
        RAISE WARNING
            'evidence_claim_history: % claims tienen limitaciones JSONB legacy no array; se conservarán bajo limitaciones[0]->''_legacy_jsonb''',
            v_limitaciones;
    END IF;
    IF v_referencias > 0 THEN
        RAISE WARNING
            'evidence_claim_history: % claims tienen referencias JSONB legacy no array; se conservarán bajo referencias[0]->''_legacy_jsonb''',
            v_referencias;
    END IF;
END $$;

INSERT INTO analytics.evidence_claim_history (
    claim_id, run_id, hipotesis_id, hipotesis, clase_evidencia, estado,
    afirmacion, estimacion, intervalo_inferior, intervalo_superior, unidad,
    n_efectivo, alcance, supuestos, limitaciones, referencias, actualizado_en
)
SELECT
    claim_id, run_id, hipotesis_id, hipotesis, clase_evidencia, estado,
    afirmacion, estimacion, intervalo_inferior, intervalo_superior, unidad,
    n_efectivo,
    CASE
        WHEN jsonb_typeof(alcance) = 'object' THEN alcance
        ELSE jsonb_build_object('_legacy_jsonb', COALESCE(alcance, 'null'::jsonb))
    END,
    CASE
        WHEN jsonb_typeof(supuestos) = 'array' THEN supuestos
        ELSE jsonb_build_array(jsonb_build_object(
            '_legacy_jsonb', COALESCE(supuestos, 'null'::jsonb)
        ))
    END,
    CASE
        WHEN jsonb_typeof(limitaciones) = 'array' THEN limitaciones
        ELSE jsonb_build_array(jsonb_build_object(
            '_legacy_jsonb', COALESCE(limitaciones, 'null'::jsonb)
        ))
    END,
    CASE
        WHEN jsonb_typeof(referencias) = 'array' THEN referencias
        ELSE jsonb_build_array(jsonb_build_object(
            '_legacy_jsonb', COALESCE(referencias, 'null'::jsonb)
        ))
    END,
    actualizado_en
FROM analytics.evidence_claim
WHERE run_id IS NOT NULL
ON CONFLICT (claim_id, run_id) DO NOTHING;

-- Normalización posterior al backfill. La función es temporal para no añadir
-- objetos permanentes al esquema: cada valor se procesa de forma aislada y
-- cualquier error de casteo queda contenido en su propia rama EXCEPTION.
CREATE OR REPLACE FUNCTION pg_temp.normalizar_claim_jsonb(
    p_claim_id text,
    p_columna text,
    p_valor jsonb,
    p_tipo_esperado text
)
RETURNS jsonb
LANGUAGE plpgsql
AS $function$
DECLARE
    v_parseado jsonb;
    v_tipo_original text;
BEGIN
    v_tipo_original := jsonb_typeof(p_valor);

    -- Esta salida hace que la migración sea idempotente: un valor ya
    -- normalizado no se vuelve a envolver ni se reescribe.
    IF v_tipo_original = p_tipo_esperado THEN
        RETURN p_valor;
    END IF;

    IF v_tipo_original = 'string' THEN
        BEGIN
            -- #>> elimina las comillas externas del escalar JSONB antes del
            -- cast; si el texto no es JSON válido, el EXCEPTION lo captura.
            v_parseado := (p_valor #>> '{}')::jsonb;
            IF jsonb_typeof(v_parseado) = p_tipo_esperado THEN
                RAISE WARNING
                    'evidence_claim: claim_id=% columna=% era string JSON válido; se normalizó de string a %',
                    p_claim_id, p_columna, p_tipo_esperado;
                RETURN v_parseado;
            END IF;

            RAISE WARNING
                'evidence_claim: claim_id=% columna=% contiene JSON válido de tipo %, se esperaba %; se conserva el valor original bajo _legacy_jsonb',
                p_claim_id, p_columna, jsonb_typeof(v_parseado), p_tipo_esperado;
        EXCEPTION WHEN others THEN
            RAISE WARNING
                'evidence_claim: claim_id=% columna=% contiene un string que no es JSON válido; se conserva el valor original bajo _legacy_jsonb',
                p_claim_id, p_columna;
        END;
    ELSE
        RAISE WARNING
            'evidence_claim: claim_id=% columna=% tiene tipo JSONB % y se esperaba %; se conserva el valor original bajo _legacy_jsonb',
            p_claim_id, p_columna, COALESCE(v_tipo_original, 'null'), p_tipo_esperado;
    END IF;

    -- El valor original completo, incluido un string inválido, queda
    -- consultable y el resultado siempre conserva el tipo semántico esperado.
    RETURN jsonb_build_object('_legacy_jsonb', COALESCE(p_valor, 'null'::jsonb));
END;
$function$;

DO $$
DECLARE
    v_claim record;
BEGIN
    FOR v_claim IN
        SELECT claim_id, alcance, supuestos, limitaciones, referencias
        FROM analytics.evidence_claim
        FOR UPDATE
    LOOP
        UPDATE analytics.evidence_claim
        SET alcance = pg_temp.normalizar_claim_jsonb(
                v_claim.claim_id, 'alcance', v_claim.alcance, 'object'
            ),
            supuestos = pg_temp.normalizar_claim_jsonb(
                v_claim.claim_id, 'supuestos', v_claim.supuestos, 'array'
            ),
            limitaciones = pg_temp.normalizar_claim_jsonb(
                v_claim.claim_id, 'limitaciones', v_claim.limitaciones, 'array'
            ),
            referencias = pg_temp.normalizar_claim_jsonb(
                v_claim.claim_id, 'referencias', v_claim.referencias, 'array'
            )
        WHERE claim_id = v_claim.claim_id
          AND (
              jsonb_typeof(v_claim.alcance) IS DISTINCT FROM 'object'
              OR jsonb_typeof(v_claim.supuestos) IS DISTINCT FROM 'array'
              OR jsonb_typeof(v_claim.limitaciones) IS DISTINCT FROM 'array'
              OR jsonb_typeof(v_claim.referencias) IS DISTINCT FROM 'array'
          );
    END LOOP;
END $$;

-- Protege futuras escrituras sin tocar claim_id, run_id ni las FKs existentes.
-- Los nombres hacen que la operación sea idempotente.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'analytics.evidence_claim'::regclass
          AND conname = 'ck_evidence_claim_alcance_json'
    ) THEN
        ALTER TABLE analytics.evidence_claim
            ADD CONSTRAINT ck_evidence_claim_alcance_json
            CHECK (jsonb_typeof(alcance) = 'object');
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'analytics.evidence_claim'::regclass
          AND conname = 'ck_evidence_claim_supuestos_json'
    ) THEN
        ALTER TABLE analytics.evidence_claim
            ADD CONSTRAINT ck_evidence_claim_supuestos_json
            CHECK (jsonb_typeof(supuestos) = 'array');
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'analytics.evidence_claim'::regclass
          AND conname = 'ck_evidence_claim_limitaciones_json'
    ) THEN
        ALTER TABLE analytics.evidence_claim
            ADD CONSTRAINT ck_evidence_claim_limitaciones_json
            CHECK (jsonb_typeof(limitaciones) = 'array');
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'analytics.evidence_claim'::regclass
          AND conname = 'ck_evidence_claim_referencias_json'
    ) THEN
        ALTER TABLE analytics.evidence_claim
            ADD CONSTRAINT ck_evidence_claim_referencias_json
            CHECK (jsonb_typeof(referencias) = 'array');
    END IF;
END $$;

CREATE OR REPLACE VIEW reporting.evidencia_analitica_historica AS
SELECT
    claim_id, run_id, hipotesis_id, hipotesis, clase_evidencia, estado,
    afirmacion, estimacion, intervalo_inferior, intervalo_superior, unidad,
    n_efectivo, alcance, supuestos, limitaciones, referencias,
    actualizado_en, registrado_en
FROM analytics.evidence_claim_history;

COMMIT;
