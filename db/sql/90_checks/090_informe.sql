-- ============================================================================
-- 90_checks · 090 · Informe de validación
--
-- Esto es lo que se enseña para decir "la migración está bien". Si algo sale FALLA, no lo
-- está.
-- ============================================================================

\pset border 2
\pset footer off

\echo ''
\echo '════════ Funciones de normalización ════════'
SELECT funcion, entrada, esperado, obtenido, estado
FROM qua.fn_probar_funciones()
WHERE estado <> 'ok';

SELECT count(*) FILTER (WHERE estado = 'ok')     AS pruebas_ok,
       count(*) FILTER (WHERE estado <> 'ok')    AS pruebas_falla
FROM qua.fn_probar_funciones();

\echo ''
\echo '════════ 1 · El origen se reproduce sin pérdidas (medido en raw y stg) ════════'
SELECT codigo, descripcion, access, obtenido, estado, nota
FROM qua.fn_validar() WHERE grupo = 'reproducir';

\echo ''
\echo '════════ 2 · Cifras que DEBEN cambiar: son las correcciones ════════'
SELECT codigo, descripcion, access AS antes, obtenido AS ahora, estado, hallazgo, nota
FROM qua.fn_validar() WHERE grupo = 'cambiar';

\echo ''
\echo '════════ 3 · Defectos que no sobreviven a la migración ════════'
SELECT codigo, descripcion, access AS antes, obtenido AS ahora, estado, hallazgo
FROM qua.fn_validar() WHERE grupo = 'cero';

\echo ''
\echo '════════ 4 · Estado de core: difiere del origen, y se explica ════════'
SELECT codigo, descripcion, access AS origen, obtenido AS en_core, estado, hallazgo, nota
FROM qua.fn_validar() WHERE grupo = 'core';

\echo ''
\echo '════════ 5 · Vistas de compatibilidad de reporting (bloques 1-4) ════════'
SELECT codigo, descripcion, obtenido, estado, hallazgo, nota
FROM qua.fn_validar() WHERE grupo = 'reporting' AND estado <> 'ok';

SELECT count(*) FILTER (WHERE estado = 'ok')  AS vistas_ok,
       count(*) FILTER (WHERE estado <> 'ok') AS vistas_falla
FROM qua.fn_validar() WHERE grupo = 'reporting';

\echo ''
\echo '════════ Cuarentena ════════'
SELECT motivo, hallazgo, filas, tope,
       CASE WHEN excede_umbral THEN 'REVISAR' ELSE 'ok' END AS estado
FROM qua.v_resumen ORDER BY filas DESC;

\echo ''
\echo '════════ Reconciliación H00 / H01 por campaña (H-07) ════════'
SELECT campania, filas_h00, filas_h01, filas_h00 - filas_h01 AS dif_filas,
       round(kg_h00, 2) AS kg_h00, round(kg_h01, 2) AS kg_h01,
       round(kg_h00 - kg_h01, 2) AS dif_kg
FROM qua.reconciliacion_cosecha ORDER BY campania;

\echo ''
\echo '════════ Veredicto ════════'
-- El caso de cero comprobaciones se trata como fallo a propósito: un contrato vacío que
-- informa "cumplido" es peor que uno que falla, porque nadie vuelve a mirarlo.
SELECT count(*) FILTER (WHERE estado = 'ok')    AS ok,
       count(*) FILTER (WHERE estado = 'FALLA') AS falla,
       count(*) FILTER (WHERE estado = 'ERROR') AS error,
       (SELECT count(*) FROM qua.fn_probar_funciones() WHERE estado <> 'ok') AS pruebas_falla,
       CASE
         WHEN count(*) = 0 THEN 'SIN COMPROBACIONES: el contrato está vacío'
         WHEN count(*) FILTER (WHERE estado <> 'ok') > 0
           OR (SELECT count(*) FROM qua.fn_probar_funciones() WHERE estado <> 'ok') > 0
              THEN 'HAY COMPROBACIONES SIN PASAR'
         WHEN EXISTS (SELECT 1 FROM qua.v_alertas) THEN 'CUARENTENA POR ENCIMA DEL UMBRAL'
         ELSE 'CONTRATO CUMPLIDO'
       END AS veredicto
FROM qua.fn_validar();
