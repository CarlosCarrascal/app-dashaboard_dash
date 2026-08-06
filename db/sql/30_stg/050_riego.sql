-- ============================================================================
-- 30_stg · 050 · Riego: resolución de identidad
--
-- El defecto que hay que evitar es el mismo que H-01 en la auditoría de Access: un
-- número de módulo suelto no es una clave si el mismo número se repite en fundos
-- distintos. Aquí se repite CUATRO veces (todos los archivos tienen módulo "1"), así
-- que la resolución es obligatoria, no cosmética.
--
-- Verificado por ÁREA (no por el número): sumar el área de todos los turnos de un
-- módulo local, un solo día, y compararla contra core.lote.area_ha agrupada por
-- core.modulo. 14 de los 16 módulos coinciden exactos (±0,05 ha de redondeo). Los dos
-- que no, con su resolución:
--
--   archivo 3, módulo local "10" (46,93 ha) = M10A (23,03) + M10B (23,90) SIN dividir
--     en el origen. Repartir por partes iguales inventaría un dato que Riego no midió.
--     Decisión: repartir proporcional al área real de cada uno (D-7, provisional).
--
--   archivo 3, módulo local "11" (42,42 ha) = M11 (42,47 ha) — que en el maestro de
--     lotes pertenece a Aqu Anqa 5, no a Aqu Anqa 3. Confirmado por el usuario
--     2026-08-06: el sistema de riego agrupa M11 en la infraestructura de Aqu Anqa 3
--     aunque el maestro de lotes lo asigne administrativamente a Aqu Anqa 5. Se carga
--     como riego de M11 (D-8, confirmado).
-- ============================================================================

CREATE TABLE IF NOT EXISTS stg.mapa_modulo_riego (
    archivo      smallint NOT NULL,
    modulo_local text NOT NULL,
    modulo_id    smallint NOT NULL REFERENCES core.modulo(modulo_id),
    -- peso < 1 solo en el caso M10A/M10B: el origen no separa esos dos módulos, así
    -- que el agua y la lámina de esa fila se reparten proporcional al área real de
    -- cada uno. peso = 1 en todos los demás casos (mapeo 1:1, sin estimación).
    peso         numeric(6,4) NOT NULL DEFAULT 1.0 CHECK (peso > 0 AND peso <= 1),
    estimado     boolean NOT NULL DEFAULT false,
    PRIMARY KEY (archivo, modulo_local, modulo_id)
);

COMMENT ON TABLE stg.mapa_modulo_riego IS
    'Resolución archivo+módulo_local → core.modulo_id, verificada por área. peso reparte '
    'el módulo local "10" del archivo 3 entre M10A y M10B, proporcional a su área real; '
    'en todo lo demás peso=1. estimado=true marca las filas que resultan de un reparto, '
    'no de una medición directa (D-7).';

-- Los 14 mapeos directos (peso = 1, estimado = false): un módulo local, un core.modulo.
INSERT INTO stg.mapa_modulo_riego (archivo, modulo_local, modulo_id)
SELECT 1, '1', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 1' AND mo.codigo = 'M01'
UNION ALL SELECT 1, '2', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 1' AND mo.codigo = 'M02'
UNION ALL SELECT 1, '3', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 1' AND mo.codigo = 'M03'
UNION ALL SELECT 1, '4', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 1' AND mo.codigo = 'M04'
UNION ALL SELECT 2, '1', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 2' AND mo.codigo = 'M01'
UNION ALL SELECT 2, '2', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 2' AND mo.codigo = 'M02'
UNION ALL SELECT 2, '3', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 2' AND mo.codigo = 'M03'
UNION ALL SELECT 2, '4', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 2' AND mo.codigo = 'M04'
UNION ALL SELECT 2, '5', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 2' AND mo.codigo = 'M05'
UNION ALL SELECT 3, '6', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 3' AND mo.codigo = 'M06'
UNION ALL SELECT 3, '7', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 3' AND mo.codigo = 'M07'
UNION ALL SELECT 3, '8', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 3' AND mo.codigo = 'M08'
UNION ALL SELECT 3, '9', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 3' AND mo.codigo = 'M09'
UNION ALL SELECT 4, '12', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 4' AND mo.codigo = 'M12'
UNION ALL SELECT 4, '13', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 4' AND mo.codigo = 'M13'
UNION ALL SELECT 4, '14', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 4' AND mo.codigo = 'M14'
UNION ALL SELECT 4, '15', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 4' AND mo.codigo = 'M15'
-- D-8: módulo local "11" del archivo 3 es M11, de Aqu Anqa 5 — cruza el fundo del archivo.
UNION ALL SELECT 3, '11', mo.modulo_id FROM core.modulo mo JOIN core.fundo fu USING (fundo_id) WHERE fu.codigo = 'Aqu Anqa 5' AND mo.codigo = 'M11'
ON CONFLICT DO NOTHING;

-- D-7: módulo local "10" del archivo 3 = M10A + M10B sin dividir. Reparto proporcional
-- al área real de cada uno, calculado desde core.lote (no hardcodeado: si el maestro
-- de lotes cambia, el peso se recalcula solo en el próximo build).
INSERT INTO stg.mapa_modulo_riego (archivo, modulo_local, modulo_id, peso, estimado)
SELECT 3, '10', mo.modulo_id,
       round(a.area_ha / sum(a.area_ha) OVER (), 4),
       true
FROM core.modulo mo
JOIN core.fundo fu USING (fundo_id)
JOIN (
    SELECT modulo_id, sum(area_ha) AS area_ha
    FROM core.lote WHERE NOT es_ficticio AND NOT es_sentinel
    GROUP BY modulo_id
) a USING (modulo_id)
WHERE fu.codigo = 'Aqu Anqa 3' AND mo.codigo IN ('M10A', 'M10B')
ON CONFLICT DO NOTHING;

-- ── Vista normalizada y resuelta, un módulo real por fila ────────────────────
CREATE OR REPLACE VIEW stg.v_riego_diario AS
SELECT r.fecha::date                        AS fecha,
       m.modulo_id,
       stg.fn_a_entero(r.turno_local)        AS turno_local,
       stg.fn_a_real(r.area_ha) * m.peso     AS area_ha,
       stg.fn_a_real(r.agua_m3) * m.peso     AS agua_m3,
       stg.fn_a_real(r.lamina_mm)            AS lamina_mm,   -- mm no se reparte por área
       stg.fn_a_real(r.reposicion_pct)       AS reposicion_pct,
       m.estimado
FROM raw.riego_diario r
JOIN stg.mapa_modulo_riego m
  ON m.archivo = r.archivo AND m.modulo_local = r.modulo_local;

COMMENT ON VIEW stg.v_riego_diario IS
    'Riego diario con módulo resuelto contra core.modulo. agua_m3 y area_ha se reparten '
    'por `peso` en el caso estimado (M10A/M10B); lamina_mm NO se reparte por área porque '
    'es una medida intensiva (mm), no un volumen — repartirla la haría más pequeña sin '
    'motivo. Grano: fecha × módulo × turno.';
