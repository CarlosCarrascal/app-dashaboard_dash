-- ============================================================================
-- 50_carga_core · 040 · Riego semanal
-- ============================================================================

CREATE OR REPLACE PROCEDURE core.sp_cargar_riego()
LANGUAGE plpgsql
AS $$
DECLARE v_n integer;
BEGIN
    TRUNCATE core.riego_semanal RESTART IDENTITY CASCADE;

    INSERT INTO core.riego_semanal (modulo_id, anio_semana, agua_m3, lamina_mm,
                                     reposicion_pct_media, dias_con_registro,
                                     turnos_distintos, estimado)
    SELECT r.modulo_id,
           ca.anio_semana,
           sum(coalesce(r.agua_m3, 0)),
           sum(coalesce(r.lamina_mm, 0)),
           avg(r.reposicion_pct),
           count(DISTINCT r.fecha),
           count(DISTINCT r.turno_local),
           bool_or(r.estimado)
    FROM stg.v_riego_diario r
    JOIN core.calendario ca ON ca.fecha = r.fecha
    GROUP BY r.modulo_id, ca.anio_semana;

    GET DIAGNOSTICS v_n = ROW_COUNT;
    RAISE NOTICE 'Riego: % filas (módulo x semana), % de ellas con reparto estimado (D-7)',
        v_n, (SELECT count(*) FROM core.riego_semanal WHERE estimado);
END;
$$;

COMMENT ON PROCEDURE core.sp_cargar_riego() IS
    'Carga core.riego_semanal desde stg.v_riego_diario, sumando agua_m3 y lamina_mm por '
    'los 7 días y todos los turnos de cada módulo y semana ISO.';
