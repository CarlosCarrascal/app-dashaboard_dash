-- ============================================================================
-- 70_reporting · 030 · Compatibilidad · familia de flores y ramas (01xx, 02xx)
--
-- Nueve consultas de Access: 01_Flores_C2025, 0101_Diametros, 0102_CantRamas,
-- 0104_PromFlores, 0105_AcumFlores, 0106_RaFloYem, 0107_YemasAb, 0108_diam,
-- 0202_FloresTurno. (0201_Flores ya está en 020_compat_campania.sql.)
--
-- El defecto más grave de la familia era H-05: 01_Flores_C2025 unía una SEMANA
-- (0104_PromFlores.Sem, 1-52) contra una tabla de DÍAS (M_Time.SEvConteo) con INNER JOIN.
-- Como muchos días comparten el mismo número de semana, cada fila se multiplicaba por
-- todos los días que la compartían: 9.040 filas reales pasaban a 487.368. Aquí no hay
-- ningún join contra el calendario para resolver la campaña; se resuelve por la poda del
-- lote, igual que en `reporting.v_flores`.
--
-- 0108_diam en Access devolvía SIEMPRE 0 filas: el INNER JOIN contra M_Lotes y M_Time
-- nunca coincidía por el vocabulario roto de Fundo (H-01). Aquí sí produce datos.
-- ============================================================================

-- ── Base: promedio de flores por lote y semana, con lote_id conservado ──────
-- Sirve de origen a 0104_PromFlores, 0105_AcumFlores, 0107_YemasAb y 01_Flores_C2025.
-- Conservar lote_id (que las vistas de compatibilidad ya no exponen) es lo que permite a
-- 01_Flores_C2025 resolver la poda por fecha sin el join que causaba H-05.
CREATE OR REPLACE VIEW reporting.v_flores_semana AS
SELECT f.lote_id,
       l.empresa, l.fundo, l.fundo_operativo, l.modulo, l.turno, l.lote,
       l.clave_negocio, l.n_plantas, l.key_map,
       t.anio, t.semana,
       avg(f.cuajo)           AS prom_cuajo,
       avg(f.n_flores)        AS prom_flores,
       avg(f.yemas_abiertas)  AS prom_ya,
       avg(f.yemas_por_abrir) AS prom_yp,
       min(f.fecha)           AS min_fecha
FROM fact.flores f
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = f.fecha
GROUP BY f.lote_id, l.empresa, l.fundo, l.fundo_operativo, l.modulo, l.turno, l.lote,
         l.clave_negocio, l.n_plantas, l.key_map, t.anio, t.semana;

COMMENT ON VIEW reporting.v_flores_semana IS
    'Promedio semanal de flores, cuajo y yemas por lote. Base de 0104_PromFlores, '
    '0105_AcumFlores, 0107_YemasAb y 01_Flores_C2025.';

-- ── Base: ramas por semana, ya en el grano correcto de planta (N-1) ─────────
CREATE OR REPLACE VIEW reporting.v_ramas_semana AS
SELECT r.lote_id,
       l.empresa, l.fundo, l.modulo, l.turno, l.lote, l.key_map,
       t.anio, t.semana,
       avg(r.ramas_mayor5)     AS prom_ramas_mayor5,
       avg(r.ramas_declaradas) AS prom_ramas_declaradas,
       count(*)                AS n_evaluaciones
FROM fact.evaluacion_ramas r
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = r.fecha
GROUP BY r.lote_id, l.empresa, l.fundo, l.modulo, l.turno, l.lote, l.key_map, t.anio, t.semana;

-- ── 0104_PromFlores ──────────────────────────────────────────────────────────
-- CORRECCIÓN DE FIDELIDAD: "Fundo" es v.empresa, no v.fundo. En Access, E02_ConteoFlores.Fundo
-- usa el vocabulario B (empresa: "Aqu Anqa I"/"Aqu Anqa II"), el mismo que ya usa
-- 0301_ConteoEstados y 0305_Brotes_Ramas — no el fundo físico ("Aqu Anqa 1".."6"), que aquí
-- se llamaría FUNDO_FISICO. Detectado al construir 0307_EstadosFlores: con v.fundo el join
-- contra 0301_ConteoEstados por Fundo+Modulo+Lote daba 0 coincidencias.
CREATE OR REPLACE VIEW reporting."0104_PromFlores" AS
SELECT v.empresa     AS "Fundo",
       v.modulo      AS "Modulo",
       v.turno       AS "Turno",
       v.lote        AS "Lote",
       v.anio        AS "Año",
       v.prom_cuajo  AS "PromCuajo",
       v.prom_flores AS "PromFlores",
       v.prom_ya     AS "PromYA",
       v.prom_yp     AS "PromYP",
       v.semana      AS "Sem",
       v.min_fecha   AS "MínDeFecha",
       v.key_map     AS "KeyMap",
       -- M_Lotes.kk se retira con el maestro viejo (ADR-0003); se deriva de KeyMap igual que
       -- ya hacía 0106_RaFloYem, y coincide en 763 de 860 casos verificados en la auditoría.
       CASE WHEN v.key_map ~ 'L' THEN left(v.key_map, position('L' IN v.key_map) - 1) END AS "kk"
FROM reporting.v_flores_semana v;

COMMENT ON VIEW reporting."0104_PromFlores" IS
    'Compatibilidad. En Access, Fundo/Modulo/Lote resolvían contra M_Lotes con el join de H-01: '
    'aquí el lote ya viene resuelto desde la carga, así que Turno y KeyMap nunca son NULL.';

-- ── 0105_AcumFlores ──────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."0105_AcumFlores" AS
SELECT "Fundo", "Modulo", "Lote", sum("PromFlores") AS "SumaDePromFlores", "Año"
FROM reporting."0104_PromFlores"
GROUP BY "Fundo", "Modulo", "Lote", "Año";

COMMENT ON VIEW reporting."0105_AcumFlores" IS
    'Compatibilidad. Es una suma de PROMEDIOS semanales, no un total real de flores contadas — '
    'así lo calculaba Access. Es un índice comparativo entre lotes, no una cantidad absoluta.';

-- ── 0107_YemasAb ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."0107_YemasAb" AS
SELECT v.anio         AS "Año",
       v.semana       AS "Sem",
       v.empresa      AS "Fundo",
       v.modulo       AS "Modulo",
       v.turno        AS "Turno",
       v.lote         AS "Lote",
       v.prom_ya      AS "PromYA",
       v.key_map      AS "KeyMap",
       'YemaAb'::text AS "Evaluacion"
FROM reporting.v_flores_semana v;

COMMENT ON VIEW reporting."0107_YemasAb" IS
    'Compatibilidad. En Access era idéntica a una de las cuatro ramas de 0106_RaFloYem — se '
    'conserva la misma redundancia porque algún informe puede seguir consumiéndola directo.';

-- ── 0102_CantRamas ───────────────────────────────────────────────────────────
-- En Access era 0101_Diametros agrupado por fecha/planta con TotalRamas = Ramas<5+Ramas>5.
-- fact.evaluacion_ramas YA es esa cabecera por planta: el GROUP BY de Access reconstruía a
-- mano lo que aquí ya existe como tabla propia (N-1).
CREATE OR REPLACE VIEW reporting."0102_CantRamas" AS
SELECT r.fecha            AS "Fecha",
       l.turno            AS "Turno",
       l.empresa          AS "Fundo",
       l.modulo           AS "Modulo",
       l.lote             AS "Lote",
       r.cortina          AS "Cortina",
       r.hilera           AS "Hilera",
       r.planta           AS "Planta",
       r.ramas_menor5     AS "Ramas <5",
       r.ramas_mayor5     AS "Ramas >5",
       r.ramas_declaradas AS "TotalRamas",
       l.key_map          AS "KeyMap"
FROM fact.evaluacion_ramas r
JOIN dim.lote l USING (lote_id);

COMMENT ON VIEW reporting."0102_CantRamas" IS
    'Compatibilidad. TotalRamas = Ramas<5 + Ramas>5, igual que en Access, pero ya no hace falta '
    'el GROUP BY de la consulta original: fact.evaluacion_ramas ya está al grano de planta (N-1).';

-- ── 0101_Diametros ───────────────────────────────────────────────────────────
-- Grano de rama medida (fact.rama_medicion), con las columnas de cabecera repetidas en cada
-- rama, igual que hacía Access. 71.095 filas (las 94.236 del origen menos 23.141 duplicados
-- exactos, H-03) en vez de las 94.236 con Turno NULL en el 100% de los casos (H-01).
CREATE OR REPLACE VIEW reporting."0101_Diametros" AS
SELECT m.rama_medicion_id::text AS "Id",
       'ConteoRamas'::text      AS "Actividad",
       ev.dni                   AS "Evaluador",
       m.fecha                  AS "Fecha",
       l.turno                  AS "Turno",
       l.empresa                AS "Fundo",
       l.modulo                 AS "Modulo",
       l.lote                   AS "Lote",
       m.cortina                AS "Cortina",
       m.hilera                 AS "Hilera",
       m.planta                 AS "Planta",
       r.ramas_menor5           AS "Ramas <5",
       r.ramas_mayor5           AS "Ramas >5",
       m.nro_rama               AS "# Ramas",
       m.diametro               AS "Diametro",
       l.key_map                AS "KeyMap"
FROM fact.rama_medicion m
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.evaluador ev ON ev.evaluador_id = m.evaluador_id
LEFT JOIN fact.evaluacion_ramas r
  ON r.lote_id = m.lote_id AND r.fecha = m.fecha
 AND r.cortina = m.cortina AND r.hilera = m.hilera AND r.planta = m.planta;

COMMENT ON VIEW reporting."0101_Diametros" IS
    'Compatibilidad. Turno y KeyMap nunca son NULL: en Access lo eran en el 100% de las 94.236 '
    'filas porque el join contra M_Lotes usaba el vocabulario equivocado de Fundo (H-01). '
    '# Ramas es el ÍNDICE de la rama dentro de la planta, no un total (N-1): no sumar esta '
    'columna, sumar Ramas <5 + Ramas >5 de 0102_CantRamas.';

-- ── 0108_diam ────────────────────────────────────────────────────────────────
-- En Access, 0 filas SIEMPRE: el INNER JOIN de 0101_Diametros contra M_Lotes y M_Time nunca
-- coincidía (H-01). Aquí sí produce datos, al grano de rama (sin agregar: la consulta
-- original tampoco agregaba, solo enriquecía con Año/Sem).
CREATE OR REPLACE VIEW reporting."0108_diam" AS
SELECT t.anio           AS "Año",
       t.semana         AS "Sem",
       l.empresa        AS "Fundo",
       l.modulo         AS "Modulo",
       l.turno          AS "Turno",
       l.lote           AS "Lote",
       m.diametro       AS "Diametro",
       l.key_map        AS "KeyMap",
       'Diametro'::text AS "Evaluacion"
FROM fact.rama_medicion m
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = m.fecha;

COMMENT ON VIEW reporting."0108_diam" IS
    'Compatibilidad. En Access esta consulta devolvía SIEMPRE 0 filas: el INNER JOIN contra '
    'M_Lotes y M_Time nunca coincidía por el vocabulario roto de Fundo (H-01). Aquí produce las '
    'mismas 71.095 filas que 0101_Diametros, a nivel de rama — la consulta original tampoco '
    'agregaba, solo la enriquecía con Año/Sem.';

-- ── 0106_RaFloYem ────────────────────────────────────────────────────────────
-- Despivote a formato largo de 4 evaluaciones: Ramas, Flores, YemaAb (las tres a grano
-- SEMANAL) y Diametro (a grano de RAMA, sin promediar). Esa mezcla de granos ya estaba en
-- el Access original — no es un defecto que se introduce aquí, se documenta y se conserva
-- por fidelidad de compatibilidad. "Fundo" es empresa (vocab B), igual que en el resto de la
-- familia — ver la nota de 0104_PromFlores.
CREATE OR REPLACE VIEW reporting."0106_RaFloYem" AS
SELECT v.anio AS "Año", v.semana AS "Sem", v.empresa AS "Fundo", v.modulo AS "Modulo",
       v.turno AS "Turno", v.lote AS "Lote", v.prom_ramas_mayor5 AS "Valor",
       v.key_map AS "KeyMap", 'Ramas'::text AS "Evaluacion",
       CASE WHEN v.key_map ~ 'L' THEN left(v.key_map, position('L' IN v.key_map) - 1) END AS "kk"
FROM reporting.v_ramas_semana v
UNION ALL
SELECT v.anio, v.semana, v.empresa, v.modulo, v.turno, v.lote, v.prom_flores,
       v.key_map, 'Flores',
       CASE WHEN v.key_map ~ 'L' THEN left(v.key_map, position('L' IN v.key_map) - 1) END
FROM reporting.v_flores_semana v
UNION ALL
SELECT v.anio, v.semana, v.empresa, v.modulo, v.turno, v.lote, v.prom_ya,
       v.key_map, 'YemaAb',
       CASE WHEN v.key_map ~ 'L' THEN left(v.key_map, position('L' IN v.key_map) - 1) END
FROM reporting.v_flores_semana v
UNION ALL
SELECT t.anio, t.semana, l.empresa, l.modulo, l.turno, l.lote, m.diametro,
       l.key_map, 'Diametro',
       CASE WHEN l.key_map ~ 'L' THEN left(l.key_map, position('L' IN l.key_map) - 1) END
FROM fact.rama_medicion m
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = m.fecha;

COMMENT ON VIEW reporting."0106_RaFloYem" IS
    'Compatibilidad. Despivote de 4 evaluaciones en una sola serie (H-11: era un UNION ALL '
    'manual de 4 bloques con el FROM repetido). ATENCIÓN: la rama "Diametro" va a grano de '
    'rama individual, mientras Ramas/Flores/YemaAb van a grano semanal — esa mezcla de granos '
    'ya estaba en Access, no es nueva aquí; cualquier análisis debe filtrar por Evaluacion '
    'antes de agregar.';

-- ── 01_Flores_C2025 ──────────────────────────────────────────────────────────
-- El nombre "C2025" es el de Access; NO se reproduce ningún filtro de campaña fijo (D-6) —
-- la columna Campaña queda disponible para filtrar en Power BI.
--
-- CORREGIDA (H-05, el hallazgo más grave de las 40 consultas): Access unía
-- 0104_PromFlores.Sem (número de semana, 1-52) contra M_Time.SEvConteo (contador
-- secuencial de semana de evaluación, a grano de DÍA) con INNER JOIN. Como muchos días
-- comparten el mismo número de semana, cada fila se multiplicaba por todos los días que lo
-- compartían: 9.040 filas reales pasaban a 487.368. Aquí no hay ningún join contra el
-- calendario: la campaña se resuelve por la poda del lote en la fecha mínima del grupo,
-- igual que en `reporting.v_flores`.
CREATE OR REPLACE VIEW reporting."01_Flores_C2025" AS
SELECT cp.campania    AS "Campaña",
       v.empresa      AS "Fundo",
       v.modulo       AS "Modulo",
       v.turno        AS "Turno",
       v.lote         AS "Lote",
       v.n_plantas    AS "NPlantas",
       v.prom_flores  AS "PromFlores",
       v.anio         AS "Año",
       v.semana       AS "Sem",
       p.fecha_inicio AS "FInicio",
       v.min_fecha    AS "MínDeFecha"
FROM reporting.v_flores_semana v
LEFT JOIN core.poda p ON p.poda_id = (
    SELECT p2.poda_id FROM core.poda p2
     WHERE p2.lote_id = v.lote_id AND p2.fecha_inicio <= v.min_fecha
     ORDER BY p2.fecha_inicio DESC LIMIT 1)
LEFT JOIN dim.campania cp ON cp.campania_id = p.campania_id;

COMMENT ON VIEW reporting."01_Flores_C2025" IS
    'Compatibilidad, CORREGIDA (H-05): el join que unía Sem (número de semana) contra '
    'M_Time.SEvConteo (contador de días) multiplicaba las 9.040 filas reales por 54, hasta '
    '487.368, sin ningún error visible. Aquí la poda se resuelve por lote y fecha, no por '
    'número de semana, así que la multiplicación no puede ocurrir. Da 9.033 y no 9.040: la '
    'diferencia son 7 combinaciones de lote+semana que desaparecen porque TODAS sus filas de '
    'origen (de las 140 de E02_ConteoFlores en cuarentena, entre lote inexistente y clave '
    'repetida) quedaron fuera de core.flores — verificado, no es una pérdida nueva.';

-- ── 0202_FloresTurno ─────────────────────────────────────────────────────────
-- CORRECCIÓN DE FIDELIDAD (encontrada al construir el bloque 2): la primera versión de esta
-- vista agrupaba solo por Turno/Año/Sem. El original agrupa por Fundo+Modulo+Turno+Año+Sem,
-- y 0304_ConteoEst_Flo_Turno depende de ese grano exacto para poder unirla con
-- 0303_ConteoEstados_Turno. `Fundo_pptom5` no tiene equivalente en el maestro vigente (ver
-- nota de la auditoría de mapeo, N-21) y queda NULL, documentado.
-- DROP porque el orden/nombre de columnas cambió; CASCADE arrastra 0304_ConteoEst_Flo_Turno,
-- que 040_compat_estados_brotes.sql recrea justo después.
DROP VIEW IF EXISTS reporting."0202_FloresTurno" CASCADE;
CREATE VIEW reporting."0202_FloresTurno" AS
SELECT t.anio    AS "Año",
       t.semana  AS "Sem",
       to_timestamp(avg(extract(epoch FROM f.fecha))::double precision)::date AS "Fecha",
       l.empresa AS "Fundo",
       NULL::text AS "Fundo_pptom5",
       l.modulo  AS "Modulo",
       l.turno   AS "Turno",
       'Flor'::text    AS "Estado",
       avg(f.n_flores) AS "Cantidad",
       sum(f.n_flores) AS "SumaTotal",
       count(*)        AS "n"
FROM fact.flores f
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = f.fecha
GROUP BY t.anio, t.semana, l.empresa, l.modulo, l.turno;

COMMENT ON VIEW reporting."0202_FloresTurno" IS
    'Compatibilidad. Agregado por fundo+módulo+turno+semana, igual que Access. Fecha sustituye '
    'a CDate(Round(Avg(Fecha),0)). Es la base de 0304_ConteoEst_Flo_Turno.';
