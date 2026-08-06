-- ============================================================================
-- 20_core · 080 · Riego semanal
--
-- Grano: módulo × semana ISO (core.calendario.anio_semana), no módulo × campaña ×
-- semana como el resto del modelo agronómico. El riego no tiene campaña propia en el
-- origen (es un registro operativo de 2025 calendario); anio_semana basta para unirlo
-- al panel de reporting.v_analitica_modulo_semana, que sí expone esa columna.
-- ============================================================================

CREATE TABLE IF NOT EXISTS core.riego_semanal (
    riego_semanal_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    modulo_id        smallint NOT NULL REFERENCES core.modulo(modulo_id),
    anio_semana      text NOT NULL,
    agua_m3          numeric(12,4) NOT NULL CHECK (agua_m3 >= 0),
    lamina_mm        numeric(10,4) NOT NULL CHECK (lamina_mm >= 0),
    reposicion_pct_media numeric(8,4),
    dias_con_registro   smallint NOT NULL,
    turnos_distintos    smallint NOT NULL,
    -- true si algún día de la semana vino de un reparto estimado (M10A/M10B, D-7). No
    -- descarta la fila: la marca, igual que `sospechoso` en core.baya_medicion.
    estimado         boolean NOT NULL DEFAULT false,
    UNIQUE (modulo_id, anio_semana)
);

COMMENT ON TABLE core.riego_semanal IS
    'Riego aplicado por módulo y semana ISO, fuente externa (4 Excel de Riego/'
    'Operaciones, 2025, cargados 2026-08-06 — no vienen de BD_AQUANQA_26.accdb). '
    'agua_m3 y lamina_mm son la suma de los 7 días de la semana, sumando también los '
    'turnos del módulo. Solo cubre Aqu Anqa 1-4 y M11 de Aqu Anqa 5: no hay riego para '
    'M16-M18 ni para Aqu Anqa 6.';
COMMENT ON COLUMN core.riego_semanal.lamina_mm IS
    'La variable de riego que Access nunca tuvo. Milímetros aplicados en la semana, '
    'sumados por día y por turno del módulo.';
COMMENT ON COLUMN core.riego_semanal.estimado IS
    'true cuando el módulo es M10A o M10B: el origen no las separa (llegan juntas como '
    '"módulo 10" en el archivo de Aqu Anqa 3) y se repartieron proporcional al área real '
    'de cada una (decisión D-7, provisional — la confirma Riego/Agronomía).';
