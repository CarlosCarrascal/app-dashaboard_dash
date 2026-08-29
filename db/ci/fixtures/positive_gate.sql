-- ============================================================================
-- Fixture positivo del contrato SQL.
--
-- Este archivo SOLO se ejecuta dentro de la base efímera que crea
-- `node scripts/run.mjs validate-fixture`. No es una carga de negocio ni sustituye la
-- validación de los conteos Access: prueba que el esquema, las vistas, las reglas de
-- gobierno y el mecanismo de salida de `90_checks` pueden completar el camino feliz.
-- La paridad de datos reales continúa dependiendo del contrato instalado por
-- `90_checks/010_contrato.sql` y de la carga de las fuentes reales.
-- ============================================================================

\set ON_ERROR_STOP on

DO $fixture_guard$
BEGIN
    IF current_database() !~ '^aquanqa_ci_positive_[0-9]+_[0-9]+$' THEN
        RAISE EXCEPTION
            'Fixture positivo rechazado fuera de una base efímera aquanqa_ci_positive_*';
    END IF;
END
$fixture_guard$;

-- La base recién construida ya pasó 010_contrato y 020_funciones. El fixture conserva las
-- 92 comprobaciones y las hace aplicables a un universo sintético vacío de raw/core; no las
-- elimina ni sustituye por una lista reducida. COALESCE convierte únicamente agregados sin
-- filas (por ejemplo AVG/SUM) en cero para que el smoke test no confunda "sin muestra" con
-- un error de ejecución. Las comprobaciones estructurales de analytics siguen ejecutándose
-- sobre la release mínima que se inserta debajo.
DO $fixture_contract$
DECLARE
    cantidad integer;
BEGIN
    SELECT count(*) INTO cantidad FROM qua.control;
    IF cantidad <> 92 THEN
        RAISE EXCEPTION 'Se esperaban 92 controles, se encontraron %', cantidad;
    END IF;
END
$fixture_contract$;

UPDATE qua.control
SET consulta = 'SELECT COALESCE((' || consulta || '), 0)',
    esperado = 0,
    valor_access = 0,
    tolerancia = 0,
    nota = COALESCE(nota || ' ', '') ||
           'Fixture positivo: universo sintético sin filas de fuente.';

-- El cargador de identidad crea exactamente un centinela en cada una de las tres
-- dimensiones aun sin filas de origen. Además, el control N-23 ve cinco tablas con cero
-- filas frente a su referencia Access; en un fixture sin Access esas diferencias son
-- intencionales, no pérdidas silenciosas. Se declaran explícitamente para no disfrazar
-- esos tres objetos de infraestructura como errores del gate.
UPDATE qua.control
SET esperado = 1
WHERE codigo IN ('core.m_lotes', 'core.m_fundos', 'core.m_modulos');

UPDATE qua.control
SET esperado = 5
WHERE codigo = 'cero.tabla_pierde_sin_rastro';

-- Una corrida y una release operativa mínima ejercitan el camino gobernado de publicación:
-- snapshot -> run succeeded -> prediction válida -> release approved/not_applicable.
-- No se usan IDs fijos para que el script sea repetible.
INSERT INTO analytics.dataset_snapshot (
    fuente, firma, esquema_version, corte_datos, tablas, cobertura, advertencias
)
VALUES (
    'fixture',
    repeat('a', 64),
    'ci-positive-fixture-v1',
    '2026-01-05T00:00:00Z',
    '{"fixture": true}'::jsonb,
    '{"filas": 0}'::jsonb,
    '[]'::jsonb
)
RETURNING snapshot_id \gset fixture_

INSERT INTO analytics.forecast_run (
    snapshot_id, tipo, estado, codigo_commit, configuracion, inicio, fin
)
VALUES (
    :fixture_snapshot_id,
    'project',
    'succeeded',
    'fixture-positive',
    '{"publicacion": "official", "fixture": true}'::jsonb,
    '2026-01-05T10:00:00Z',
    '2026-01-05T10:01:00Z'
)
RETURNING run_id \gset fixture_

INSERT INTO analytics.prediction (
    run_id, modelo, version_modelo, campania, empresa, fundo, modulo, lote, lote_id,
    fecha_emision, fecha_objetivo, horizonte_semanas, banda_horizonte, version_fuente,
    p10_kg, p50_kg, p90_kg, real_kg, plantas, frutos_por_planta, peso_baya_g,
    confianza, componentes
)
VALUES (
    :fixture_run_id,
    'ModeloOperativoActual_v1',
    'fixture-v1',
    'C2026',
    'Aquanqa',
    'Arena',
    'M01',
    'L001',
    NULL,
    '2026-01-05',
    '2026-01-12',
    1,
    'operativo',
    'fixture-positive',
    90,
    100,
    110,
    NULL,
    NULL,
    NULL,
    NULL,
    'media',
    '{"fixture": true}'::jsonb
);

INSERT INTO analytics.model_series_release (
    evaluation_contract_id, run_id, snapshot_id, campania, modelo, version_modelo, uso,
    estado, estado_evaluacion, activo, source_hash, predicciones_sha256, metadatos,
    creado_por, aprobado_en, aprobado_por
)
VALUES (
    NULL,
    :fixture_run_id,
    :fixture_snapshot_id,
    'C2026',
    'ModeloOperativoActual_v1',
    'fixture-v1',
    'operativo',
    'approved',
    'not_applicable',
    true,
    repeat('b', 64),
    repeat('c', 64),
    '{"fixture": true}'::jsonb,
    'ci',
    '2026-01-05T10:02:00Z',
    'ci'
);

DO $fixture_assertions$
DECLARE
    controles integer;
    releases integer;
    predicciones integer;
BEGIN
    SELECT count(*) INTO controles
    FROM qua.control
    WHERE consulta LIKE 'SELECT COALESCE((%';
    SELECT count(*) INTO releases
    FROM analytics.model_series_release
    WHERE activo
      AND estado = 'approved'
      AND estado_evaluacion = 'not_applicable'
      AND uso = 'operativo';
    SELECT count(*) INTO predicciones
    FROM analytics.prediction
    WHERE run_id = (
        SELECT run_id
        FROM analytics.forecast_run
        WHERE codigo_commit = 'fixture-positive'
    )
      AND modelo = 'ModeloOperativoActual_v1'
      AND fecha_objetivo > fecha_emision
      AND p10_kg <= p50_kg
      AND p50_kg <= p90_kg;

    IF controles <> 92 OR releases <> 1 OR predicciones <> 1 THEN
        RAISE EXCEPTION
            'Fixture positivo incompleto: controles=%, releases=%, predicciones=%',
            controles, releases, predicciones;
    END IF;
END
$fixture_assertions$;
