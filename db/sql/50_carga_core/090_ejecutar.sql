-- ============================================================================
-- 50_carga_core · 090 · Ejecución de la carga
--
-- El orden NO es arbitrario, y hay dos dependencias que lo fijan:
--
--   · el mapa de identidad necesita core.lote ya cargado,
--   · el staging materializado incorpora el lote ya resuelto, así que va después del mapa,
--     y todos los hechos leen de ahí.
--
-- Toda la carga es idempotente: cada procedimiento vacía su destino antes de escribir, así
-- que ejecutarla dos veces deja el mismo resultado. Eso es lo que faltaba en el origen —
-- H-03 y H-08 existen precisamente porque una recarga se ejecutó sobre datos ya cargados y
-- nada la detuvo.
-- ============================================================================

\timing on

\echo '── Vaciando cuarentena de la ejecución anterior'
TRUNCATE qua.rechazos RESTART IDENTITY;

\echo '── 1/10 · Maestro de ubicación (empresa, fundo, módulo, turno, variedad, lote, alias)'
-- El maestro se materializa primero porque de él sale la identidad de todo lo demás.
CALL stg.sp_materializar(ARRAY['maestro_lote']);
CALL core.sp_cargar_ubicacion();

\echo '── 2/10 · Mapa de identidad'
CALL stg.sp_refrescar_mapa_lote();

\echo '── 3/10 · Materialización del staging'
CALL stg.sp_materializar();

\echo '── 4/10 · Tiempo (campaña, calendario, semana de evaluación)'
CALL core.sp_cargar_tiempo();

\echo '── 5/10 · Evaluadores'
CALL core.sp_cargar_evaluadores();

\echo '── 6/10 · Poda y muestreo requerido'
CALL core.sp_cargar_poda();
CALL core.sp_cargar_muestreo();

\echo '── 7/10 · Evaluaciones fenológicas'
CALL core.sp_cargar_ramas();
CALL core.sp_cargar_flores();
CALL core.sp_cargar_estados();
CALL core.sp_cargar_brotes();
CALL core.sp_cargar_bayas();

\echo '── 8/10 · Cosecha, clima y packing'
CALL core.sp_cargar_cosecha();
CALL core.sp_cargar_clima();
CALL core.sp_cargar_packing();

\echo '── 9/10 · Forecast'
CALL core.sp_cargar_forecast();

\echo '── 10/10 · Riego (fuente externa a Access, ver db/sql/10_raw/080_riego.sql)'
CALL core.sp_cargar_riego();

\timing off

\echo ''
\echo '── Cuarentena'
SELECT motivo, hallazgo, filas, tope,
       CASE WHEN excede_umbral THEN 'REVISAR' ELSE 'ok' END AS estado
FROM qua.v_resumen ORDER BY filas DESC;

ANALYZE;
