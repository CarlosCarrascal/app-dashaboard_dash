-- ============================================================================
-- 50_carga_core · 025 · Carga del modelo extensible de bayas
--
-- Primera fuente: E05_Seguimiento de Access (madurez + diámetro). El Excel oficial de peso
-- tendrá un adaptador propio cuando se inspeccione su estructura; no se fuerza aquí.
-- ============================================================================

CREATE OR REPLACE PROCEDURE core.sp_cargar_evaluaciones_baya()
LANGUAGE plpgsql
AS $$
DECLARE
    v_cab integer;
    v_det integer;
BEGIN
    TRUNCATE core.ev_baya_observacion, core.ev_evaluacion_baya RESTART IDENTITY CASCADE;

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E05_Seguimiento', 'core.ev_baya_observacion', 'DIAMETRO_BAYA_NO_POSITIVO',
           'MIGRACION-VALIDACION',
           'El valor se conserva en raw, pero no se materializa como diámetro en core porque '
           'la medición debe ser mayor que cero.',
           to_jsonb(v)
    FROM stg.e05_seguimiento v
    WHERE v.diametro_mm IS NOT NULL AND v.diametro_mm <= 0;

    INSERT INTO qua.rechazos
        (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'E05_Seguimiento', 'core.ev_evaluacion_baya',
           coalesce(motivo, 'LOTE_INEXISTENTE'), 'H-01',
           'No se pudo identificar el lote de la evaluación de baya.', to_jsonb(v)
    FROM stg.e05_seguimiento v
    WHERE lote_id IS NULL OR fecha IS NULL;

    INSERT INTO core.ev_evaluacion_baya
        (lote_id, fecha, cortina, hilera, planta, evaluador_id, tipo, origen,
         idempotency_key, source_snapshot_id, source_row_hash)
    SELECT DISTINCT ON (v.source_snapshot_id, v.source_row_number)
           v.lote_id, v.fecha, coalesce(v.cortina, 0), coalesce(v.hilera, 0),
           coalesce(v.planta, 0), stg.fn_resolver_evaluador(v.dni), 'madurez', 'access',
           'access:' || coalesce(v.source_snapshot_id::text, 'legacy') || ':'
               || coalesce(v.source_row_number::text, md5(v.id_origen || v.fecha::text)),
           v.source_snapshot_id, v.source_row_hash
    FROM stg.e05_seguimiento v
    WHERE v.lote_id IS NOT NULL AND v.fecha IS NOT NULL
      AND (v.estado_codigo IS NOT NULL OR v.diametro_mm > 0)
    ORDER BY v.source_snapshot_id, v.source_row_number, v.numero_muestra;

    GET DIAGNOSTICS v_cab = ROW_COUNT;

    INSERT INTO core.ev_baya_observacion
        (evaluacion_baya_id, numero_muestra, numero_medicion, estado_codigo, diametro_mm)
    SELECT e.evaluacion_baya_id, v.numero_muestra, 1, v.estado_codigo,
           CASE WHEN v.diametro_mm > 0 THEN v.diametro_mm END
    FROM stg.e05_seguimiento v
    JOIN core.ev_evaluacion_baya e
      ON e.origen = 'access'
     AND e.idempotency_key =
         'access:' || coalesce(v.source_snapshot_id::text, 'legacy') || ':'
             || coalesce(v.source_row_number::text, md5(v.id_origen || v.fecha::text))
    WHERE v.estado_codigo IS NOT NULL OR v.diametro_mm > 0;

    GET DIAGNOSTICS v_det = ROW_COUNT;
    RAISE NOTICE 'Evaluaciones de baya: % cabeceras, % observaciones', v_cab, v_det;
END;
$$;

COMMENT ON PROCEDURE core.sp_cargar_evaluaciones_baya() IS
    'Carga E05_Seguimiento al contrato extensible de bayas. El peso de campo se cargará por '
    'otro adaptador cuando el Excel operativo oficial tenga contrato validado.';
