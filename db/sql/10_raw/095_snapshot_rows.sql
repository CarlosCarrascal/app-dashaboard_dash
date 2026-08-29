-- ============================================================================
-- 095 · raw · Metadatos por fila y vistas de snapshots publicados
--
-- Las columnas de origen permanecen intactas. Estas columnas técnicas permiten
-- conservar varias copias del mismo Access sin confundir histórico con vigente.
-- Son nullable para que este DDL pueda convivir con una base antigua; toda fila
-- nueva cargada por el ETL debe tenerlas pobladas.
-- ============================================================================

DO $$
DECLARE
    tabla text;
    tablas text[] := ARRAY[
        'e01_ramas', 'e02_conteo_flores', 'e03_conteo_estados',
        'e04_brotes', 'e05_diametros_bayas', 'e05_seguimiento',
        'h00_volumen_campo', 'h01_detalle_cosecha', 'h01_prod_historica',
        'h02_bd_elifab', 'h05_clima', 'm_equivalencia_elifab',
        'm_evaluadores', 'm_lotes', 'm_n_muestra', 'm_poda',
        'm_presupuesto_mo', 'm_time', 'r08_forecast_campania',
        'r08_forecast_campania_24', 'r08_forecast_campania_25',
        'r09_forecast_semanal', 'r09_forecast_semanal_25',
        'm_lotes_maestro', 'tareo', 'riego_diario'
    ];
BEGIN
    FOREACH tabla IN ARRAY tablas LOOP
        EXECUTE format(
            'ALTER TABLE raw.%I
                ADD COLUMN IF NOT EXISTS source_snapshot_id bigint,
                ADD COLUMN IF NOT EXISTS source_row_number bigint,
                ADD COLUMN IF NOT EXISTS source_row_hash text,
                ADD COLUMN IF NOT EXISTS loaded_at timestamptz',
            tabla
        );

        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON raw.%I (source_snapshot_id)',
            tabla || '_snapshot_idx', tabla
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON raw.%I (source_snapshot_id, source_row_hash)',
            tabla || '_row_hash_idx', tabla
        );

        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = tabla || '_source_snapshot_fk'
              AND conrelid = ('raw.' || tabla)::regclass
        ) THEN
            EXECUTE format(
                'ALTER TABLE raw.%I ADD CONSTRAINT %I
                    FOREIGN KEY (source_snapshot_id)
                    REFERENCES raw.source_snapshot(source_snapshot_id)',
                tabla, tabla || '_source_snapshot_fk'
            );
        END IF;

        EXECUTE format(
            'CREATE OR REPLACE VIEW raw.v_%I_vigente AS
                SELECT t.*
                FROM raw.%I t
                WHERE t.source_snapshot_id IS NULL
                  AND NOT EXISTS (SELECT 1 FROM raw.v_snapshot_publicado)
                UNION ALL
                SELECT t.*
                FROM raw.%I t
                JOIN raw.v_snapshot_publicado p
                  ON p.source_snapshot_id = t.source_snapshot_id',
            tabla, tabla, tabla
        );
    END LOOP;
END $$;

-- La fuente primaria de identidad de lote se decide explícitamente en el gobierno de la
-- migración. `raw.v_m_lotes_vigente` apunta al snapshot Access publicado; el Excel se conserva
-- en `raw.v_m_lotes_maestro_vigente` únicamente como fuente externa de contraste.
CREATE OR REPLACE VIEW raw.v_m_lotes_principal_vigente AS
SELECT t.*
FROM raw.v_m_lotes_vigente t;

COMMENT ON VIEW raw.v_m_lotes_principal_vigente IS
    'Fuente primaria de identidad de lote: M_Lotes de Access del snapshot publicado. '
    'M_Lotes.xlsx permanece en raw como control de contraste; no reemplaza Access.';

COMMENT ON VIEW raw.v_e05_seguimiento_vigente IS
    'E05_Seguimiento de los snapshots Access publicados; no contiene todas las versiones históricas.';

CREATE OR REPLACE VIEW raw.v_source_snapshot_resumen AS
SELECT s.source_snapshot_id,
       s.tipo,
       s.campania,
       s.version_fuente,
       s.nombre_archivo,
       s.sha256,
       s.schema_hash,
       s.estado,
       s.modificado_en,
       s.extraido_en,
       p.publicado_en,
       p.autorizado_por
FROM raw.source_snapshot s
LEFT JOIN raw.v_snapshot_publicado p
  ON p.tipo = s.tipo
 AND p.campania = s.campania
 AND p.source_snapshot_id = s.source_snapshot_id;

COMMENT ON VIEW raw.v_source_snapshot_resumen IS
    'Resumen operativo de snapshots detectados, cargados y publicados.';

-- Esta vista ya existía antes del gobierno de snapshots. Se reemplaza al final de 10_raw para
-- que las capas posteriores no vuelvan a consumir todos los bloques append-only de R09.
CREATE OR REPLACE VIEW raw.v_r09_forecast_semanal_historico AS
SELECT campania, pasada, modulo, turno, lote, area, fecha_cos_ant, fecha_cos,
       sem, frt_cos, peso, frutos_total, rend, kg, dr, version, fund_ppto, fundo
FROM raw.v_r09_forecast_semanal_vigente
UNION
SELECT campania, pasada, modulo, turno, lote, area, fecha_cos_ant, fecha_cos,
       sem, frt_cos, peso, frutos_total, rend, kg, dr, version, fund_ppto, fundo
FROM raw.r09_forecast_semanal_snapshot;
