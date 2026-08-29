-- ============================================================================
-- 90_checks · 030 · Gobierno analítico y coherencia de proyecciones
-- ============================================================================

DO $$
DECLARE
    faltantes text[];
    violaciones bigint;
BEGIN
    IF to_regclass('raw.source_snapshot') IS NULL
       OR to_regclass('raw.source_table_delta') IS NULL
       OR to_regclass('raw.v_ultimo_snapshot_fuente') IS NULL
       OR to_regclass('raw.v_r09_forecast_semanal_historico') IS NULL THEN
        RAISE EXCEPTION 'Falta trazabilidad Access-first o el histórico R09 en raw';
    END IF;

    SELECT array_agg(nombre ORDER BY nombre) INTO faltantes
    FROM unnest(ARRAY[
        'dataset_snapshot', 'forecast_run', 'prediction', 'metric', 'evidence_claim',
        'evidence_claim_history',
        'model_feature_evidence', 'model_decision', 'quality_result', 'artifact',
        'projection_scenario', 'projection_scenario_review', 'weather_forecast_snapshot',
        'model_comparison_metric', 'evaluation_contract', 'model_series_release'
    ]) AS nombre
    WHERE to_regclass('analytics.' || nombre) IS NULL;
    IF faltantes IS NOT NULL THEN
        RAISE EXCEPTION 'Faltan tablas analytics: %', array_to_string(faltantes, ', ');
    END IF;

    IF to_regclass('reporting.proyeccion_vigente') IS NULL
       OR to_regclass('reporting.desempeno_modelos') IS NULL
       OR to_regclass('reporting.evidencia_analitica') IS NULL
       OR to_regclass('reporting.evidencia_analitica_historica') IS NULL
       OR to_regclass('reporting.evidencia_features_modelo') IS NULL
       OR to_regclass('reporting.fuente_operativa_access') IS NULL
       OR to_regclass('reporting.proyeccion_experimental') IS NULL
       OR to_regclass('reporting.proyeccion_operativa_detalle') IS NULL
       OR to_regclass('reporting.proyeccion_operativa_fundo_semana') IS NULL
       OR to_regclass('reporting.cosecha_real_fundo_semana') IS NULL
       OR to_regclass('reporting.comparacion_r09_fenologico_pareada') IS NULL
       OR to_regclass('reporting.comparacion_modelos_historica') IS NULL
       OR to_regclass('reporting.curva_historica_modelos') IS NULL
       OR to_regclass('reporting.model_series_release_status') IS NULL
       OR to_regclass('reporting.trazabilidad_modelo') IS NULL THEN
        RAISE EXCEPTION 'Falta al menos una vista reporting del contrato analítico';
    END IF;

    IF to_regclass('analytics.ux_model_series_release_activa') IS NULL THEN
        RAISE EXCEPTION 'Falta la unicidad de release activa por campaña, modelo y uso';
    END IF;

    SELECT count(*) INTO violaciones
    FROM (
        SELECT campania, modelo, uso
        FROM analytics.model_series_release
        WHERE activo
        GROUP BY campania, modelo, uso
        HAVING count(*) > 1
    ) releases_activas_duplicadas;
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% series tienen más de una release activa para el mismo uso',
                        violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM analytics.model_series_release l
    JOIN analytics.evaluation_contract c
      ON c.evaluation_contract_id = l.evaluation_contract_id
    JOIN analytics.forecast_run r
      ON r.run_id = l.run_id
    WHERE l.activo
      AND (
          l.estado <> 'approved'
          OR l.estado_evaluacion <> 'passed'
          OR l.aprobado_en IS NULL
          OR c.estado <> 'approved'
          OR r.estado NOT IN ('succeeded', 'published')
          OR l.campania <> c.campania
          OR l.snapshot_id <> c.snapshot_id
          OR l.snapshot_id <> r.snapshot_id
      );
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% releases activas carecen de contrato, evaluación o corrida aprobable',
                        violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM analytics.model_series_release l
    JOIN analytics.forecast_run r
      ON r.run_id = l.run_id
    WHERE l.activo
      AND l.uso = 'operativo'
      AND (
          l.estado <> 'approved'
          OR l.estado_evaluacion <> 'not_applicable'
          OR l.evaluation_contract_id IS NOT NULL
          OR l.aprobado_en IS NULL
          OR r.estado NOT IN ('succeeded', 'published')
          OR l.snapshot_id <> r.snapshot_id
      );
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% releases operativas activas violan publicación o snapshot',
                        violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM (
        SELECT campania
        FROM analytics.model_series_release
        WHERE activo
          AND estado = 'approved'
          AND estado_evaluacion = 'passed'
          AND uso IN ('historico', 'referencia')
        GROUP BY campania
        HAVING count(DISTINCT evaluation_contract_id) > 1
    ) contratos_historicos_incompatibles;
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% campañas mezclan contratos históricos activos', violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM analytics.evaluation_contract c
    WHERE c.estado = 'approved'
      AND (
          c.fecha_inicio_objetivo IS NULL
          OR c.fecha_fin_objetivo IS NULL
          OR c.cerrado_hasta IS NULL
          OR c.cerrado_hasta < c.fecha_fin_objetivo
          OR cardinality(c.horizontes_semanas) = 0
          OR EXISTS (
              SELECT 1 FROM unnest(c.horizontes_semanas) h WHERE h < 1
          )
          OR jsonb_array_length(c.semanas_cerradas) = 0
          OR c.keyset_sha256 IS NULL
          OR c.closed_calendar_sha256 IS NULL
          OR c.volumen_real_kg IS NULL
          OR c.n_unidades = 0
          OR c.n_emisiones = 0
          OR c.aprobado_en IS NULL
      );
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% contratos aprobados están incompletos o contienen horizonte cero',
                        violaciones;
    END IF;

    -- Histórico y referencia comparten la misma gráfica. Dos releases activas del mismo
    -- modelo con usos distintos producirían dos curvas indistinguibles y se bloquean aquí.
    SELECT count(*) INTO violaciones
    FROM (
        SELECT campania, modelo
        FROM analytics.model_series_release
        WHERE activo
          AND estado = 'approved'
          AND estado_evaluacion = 'passed'
          AND uso IN ('historico', 'referencia')
        GROUP BY campania, modelo
        HAVING count(*) > 1
    ) releases_visibles_ambiguas;
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% modelos tienen releases históricas/referencia activas ambiguas',
                        violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM analytics.model_series_release l
    WHERE l.activo
      AND NOT EXISTS (
          SELECT 1
          FROM analytics.prediction p
          WHERE p.run_id = l.run_id
            AND p.campania = l.campania
            AND p.modelo = l.modelo
            AND COALESCE(NULLIF(p.version_modelo, ''), 'sin_version') = l.version_modelo
      );
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% releases activas no encuentran su modelo/versión exactos en prediction',
                        violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM (
        SELECT l.release_id, p.lote_id,
               date_trunc('week', p.fecha_objetivo)::date AS semana_inicio,
               p.fecha_emision
        FROM analytics.model_series_release l
        JOIN analytics.prediction p
          ON p.run_id = l.run_id
         AND p.campania = l.campania
         AND p.modelo = l.modelo
         AND COALESCE(NULLIF(p.version_modelo, ''), 'sin_version') = l.version_modelo
        WHERE l.activo
          AND l.estado = 'approved'
          AND l.estado_evaluacion = 'passed'
        GROUP BY l.release_id, p.lote_id,
                 date_trunc('week', p.fecha_objetivo)::date, p.fecha_emision
        HAVING count(*) > 1
    ) duplicadas_release;
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% claves lote-semana-emisión están duplicadas en releases activas',
                        violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM reporting.curva_historica_modelos c
    WHERE c.certificado IS DISTINCT FROM true
       OR c.evaluation_contract_id IS NULL
       OR c.estado_contrato <> 'approved'
       OR c.fecha_objetivo + 6 > c.cerrado_hasta
       OR (
           c.modelo <> 'Real cosechado'
           AND (
               c.release_id IS NULL
               OR c.estado_release <> 'approved'
               OR c.estado_evaluacion_release <> 'passed'
               OR c.origen_emision_min IS NULL
               OR c.origen_emision_max IS NULL
               OR c.origen_emision_min <> c.origen_emision_max
               OR c.origen_emision_max >= c.fecha_objetivo
               OR c.horizonte_semanas < 1
           )
       );
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% filas históricas violan certificación, cierre o emisión coherente',
                        violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM analytics.prediction p
    JOIN analytics.forecast_run r USING (run_id)
    WHERE r.estado IN ('succeeded', 'published')
      AND (p.fecha_objetivo < p.fecha_emision
       OR p.p50_kg < 0
       OR (p.p10_kg IS NOT NULL AND p.p10_kg > p.p50_kg)
       OR (p.p90_kg IS NOT NULL AND p.p90_kg < p.p50_kg));
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% predicciones violan tiempo, no negatividad o cuantiles', violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM analytics.evidence_claim
    WHERE clase_evidencia = 'causal' AND estado <> 'causal';
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% claims usan etiqueta causal sin evidencia causal', violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM analytics.evidence_claim_history
    WHERE jsonb_typeof(alcance) IS DISTINCT FROM 'object'
       OR jsonb_typeof(supuestos) IS DISTINCT FROM 'array'
       OR jsonb_typeof(limitaciones) IS DISTINCT FROM 'array'
       OR jsonb_typeof(referencias) IS DISTINCT FROM 'array';
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% filas del histórico de claims tienen tipos JSONB incompatibles',
                        violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM analytics.evidence_claim vigente
    LEFT JOIN analytics.evidence_claim_history historico
      ON historico.claim_id = vigente.claim_id
     AND historico.run_id = vigente.run_id
    WHERE vigente.run_id IS NOT NULL
      AND historico.claim_id IS NULL;
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% claims vigentes con run_id no tienen fila correspondiente en el histórico',
                        violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM (
        SELECT banda_horizonte
        FROM analytics.model_decision
        WHERE vigente
        GROUP BY banda_horizonte
        HAVING count(*) > 1
    ) duplicadas;
    IF violaciones > 0 THEN
        RAISE EXCEPTION 'Existe más de una decisión vigente para un horizonte';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'analytics.prediction'::regclass
          AND conname = 'uq_prediction_lote_semana'
          AND pg_get_constraintdef(oid) LIKE '%lote_id%'
    ) THEN
        RAISE EXCEPTION 'La identidad de predicción no está protegida por lote_id';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgrelid = 'analytics.prediction'::regclass
          AND tgname = 'trg_proteger_prediccion_publicada'
          AND NOT tgisinternal
    ) THEN
        RAISE EXCEPTION 'Las predicciones publicadas no están protegidas contra mutación';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgrelid = 'analytics.model_series_release'::regclass
          AND tgname = 'trg_proteger_release_publicada'
          AND NOT tgisinternal
    ) THEN
        RAISE EXCEPTION 'Las releases publicadas no están protegidas contra reescritura';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'analytics' AND table_name = 'quality_result'
          AND column_name = 'run_id'
    ) THEN
        RAISE EXCEPTION 'quality_result no identifica la corrida que produjo el control';
    END IF;

    SELECT count(*) INTO violaciones
    FROM (
        SELECT banda_horizonte
        FROM reporting.comparacion_r09_fenologico_pareada
        GROUP BY banda_horizonte
        HAVING count(DISTINCT n) > 1 OR count(DISTINCT volumen_real_kg) > 1
    ) universos_distintos;
    IF violaciones > 0 THEN
        RAISE EXCEPTION 'La comparación R09-challenger no usa el mismo n y volumen real';
    END IF;

    SELECT count(*) INTO violaciones
    FROM reporting.proyeccion_operativa_detalle
    WHERE fundo IS NULL OR fundo NOT IN ('Arena', 'Ayllu', 'Kawsay', 'Quri');
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% filas no pertenecen a los cuatro fundos operativos', violaciones;
    END IF;

    SELECT count(*) INTO violaciones
    FROM (
        WITH detalle AS MATERIALIZED (
            SELECT d.run_id, d.campania, d.fecha_emision,
                   date_trunc('week', d.fecha_objetivo)::date AS semana_inicio,
                   d.fundo, SUM(d.p50_kg)::double precision AS kg
            FROM reporting.proyeccion_operativa_detalle d
            GROUP BY d.run_id, d.campania, d.fecha_emision,
                     date_trunc('week', d.fecha_objetivo)::date, d.fundo
        ), agregado AS MATERIALIZED (
            SELECT run_id, campania, fecha_emision, semana_inicio, fundo, kg
            FROM reporting.proyeccion_operativa_fundo_semana
        )
        SELECT d.run_id
        FROM detalle d
        LEFT JOIN agregado s
          ON s.run_id = d.run_id
         AND s.campania IS NOT DISTINCT FROM d.campania
         AND s.fecha_emision = d.fecha_emision
         AND s.semana_inicio = d.semana_inicio
         AND s.fundo IS NOT DISTINCT FROM d.fundo
        WHERE s.kg IS NULL OR ABS(d.kg - s.kg) > 0.01
    ) diferencias;
    IF violaciones > 0 THEN
        RAISE EXCEPTION '% agregados fundo-semana no concilian con el detalle', violaciones;
    END IF;
END $$;

SELECT 'analytics' AS componente, 'ok' AS estado,
       (SELECT count(*) FROM analytics.forecast_run
        WHERE estado IN ('succeeded', 'published')) AS corridas_validas,
       (SELECT count(*) FROM analytics.evidence_claim) AS conclusiones_versionadas,
       (SELECT count(*) FROM analytics.prediction) AS predicciones_auditables;
