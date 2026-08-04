-- ============================================================================
-- 30_stg · 050 · Materialización
--
-- Las vistas de 040 definen la transformación; aquí se ejecuta UNA vez y el resultado queda
-- en tablas. Un staging que no materializa obliga a recalcular la normalización en cada
-- consulta: son ~40 llamadas a funciones de texto por fila sobre 300.000 filas, y la carga
-- de core pasaba de minutos a horas.
--
-- Las tablas se llaman igual que su vista sin el prefijo `v_`: stg.v_e01_ramas → stg.e01_ramas.
-- ============================================================================

CREATE OR REPLACE PROCEDURE stg.sp_materializar(p_solo text[] DEFAULT NULL)
LANGUAGE plpgsql
AS $$
DECLARE
    v_tablas text[] := ARRAY[
        'maestro_lote', 'e01_ramas', 'e02_flores', 'e03_estados', 'e04_brotes', 'e05_bayas',
        'h00_cosecha', 'h01_cosecha', 'h02_packing', 'h05_clima',
        'm_poda', 'm_evaluadores', 'm_n_muestra', 'm_time', 'r08_forecast', 'r09_forecast'
    ];
    v_tabla   text;
    v_filas   bigint;
    v_total   bigint := 0;
BEGIN
    FOREACH v_tabla IN ARRAY coalesce(p_solo, v_tablas) LOOP
        -- Sin CASCADE a propósito: si algo depende de una tabla de staging, quiero que
        -- falle aquí. Lo que consume el modelo es `core`, no `stg` (ADR-0004).
        EXECUTE format('DROP TABLE IF EXISTS stg.%I', v_tabla);
        EXECUTE format('CREATE TABLE stg.%I AS SELECT * FROM stg.v_%I', v_tabla, v_tabla);

        EXECUTE format('SELECT count(*) FROM stg.%I', v_tabla) INTO v_filas;
        v_total := v_total + v_filas;

        -- Índices sobre las columnas por las que se cargan los hechos.
        IF EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'stg' AND table_name = v_tabla
                      AND column_name = 'lote_id') THEN
            EXECUTE format('CREATE INDEX ON stg.%I (lote_id)', v_tabla);
        END IF;
        IF EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'stg' AND table_name = v_tabla
                      AND column_name = 'motivo') THEN
            EXECUTE format('CREATE INDEX ON stg.%I (motivo) WHERE motivo IS NOT NULL', v_tabla);
        END IF;

        EXECUTE format('ANALYZE stg.%I', v_tabla);
        RAISE NOTICE '  stg.% · % filas', rpad(v_tabla, 16), v_filas;
    END LOOP;

    RAISE NOTICE 'Staging materializado: % filas en % tablas',
        v_total, array_length(coalesce(p_solo, v_tablas), 1);
END;
$$;

COMMENT ON PROCEDURE stg.sp_materializar(text[]) IS
    'Materializa las vistas de stg en tablas. Debe ejecutarse DESPUÉS de stg.sp_refrescar_'
    'mapa_lote(), porque las vistas incorporan el lote ya resuelto.';
