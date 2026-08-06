-- ============================================================================
-- 70_reporting · 040 · Compatibilidad · familia de estados y brotes (03xx, 04xx)
--
-- Ocho consultas: 0302_ConteoAjustado, 0303_ConteoEstados_Turno,
-- 0304_ConteoEst_Flo_Turno, 0306_FrutosFlores, 0307_EstadosFlores,
-- 0401_Estados_planta, y las CORREGIDAS 0402_ConteoBrotes y E.
-- (0301_ConteoEstados y 0305_Brotes_Ramas ya están en 020_compat_campania.sql.)
--
-- 0303_ConteoEstados_Turno despivota Est1..Est5 con un CROSS JOIN LATERAL en vez del UNION
-- ALL de 5 bloques que usaba Access (H-11) — mismo patrón que ya usa `reporting.v_fenologia`.
-- ============================================================================

-- ── 0302_ConteoAjustado ──────────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."0302_ConteoAjustado" AS
SELECT t.anio    AS "Año",
       t.semana  AS "Sem",
       to_timestamp(avg(extract(epoch FROM e.fecha))::double precision)::date AS "Fecha",
       l.empresa AS "Fundo",
       l.modulo  AS "Modulo",
       l.turno   AS "Turno",
       sum(e.e1)::numeric / nullif(sum(e.e1 + e.e2 + e.e3 + e.e4 + e.e5), 0) AS "pE1",
       sum(e.e2)::numeric / nullif(sum(e.e1 + e.e2 + e.e3 + e.e4 + e.e5), 0) AS "pE2",
       sum(e.e3)::numeric / nullif(sum(e.e1 + e.e2 + e.e3 + e.e4 + e.e5), 0) AS "pE3",
       sum(e.e4)::numeric / nullif(sum(e.e1 + e.e2 + e.e3 + e.e4 + e.e5), 0) AS "pE4",
       sum(e.e5)::numeric / nullif(sum(e.e1 + e.e2 + e.e3 + e.e4 + e.e5), 0) AS "pE5",
       sum(e.total)                            AS "SumTotal",
       count(*)                                AS "n",
       sum(e.total)::numeric / count(*)        AS "FrutosxPl",
       NULL::text                              AS "Fundo_pptom5"
FROM fact.estados e
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = e.fecha
GROUP BY t.anio, t.semana, l.empresa, l.modulo, l.turno
HAVING sum(e.total) > 0;

COMMENT ON VIEW reporting."0302_ConteoAjustado" IS
    'Compatibilidad. pE1..pE5 son proporciones agregadas por semana (suma de Ei entre suma '
    'del total), no el promedio de proporciones por planta — así lo calculaba Access. '
    '"el mejor diseño de la base" según la documentación original: sin hallazgos.';

-- ── 0303_ConteoEstados_Turno ─────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."0303_ConteoEstados_Turno" AS
SELECT c."Año", c."Sem", c."Fecha", c."Fundo", c."Fundo_pptom5", c."Modulo", c."Turno",
       x.estado AS "Estado",
       x.proporcion * c."FrutosxPl" AS "Cantidad",
       c."SumTotal", c."n"
FROM reporting."0302_ConteoAjustado" c
CROSS JOIN LATERAL (VALUES
    ('Est1', c."pE1"), ('Est2', c."pE2"), ('Est3', c."pE3"),
    ('Est4', c."pE4"), ('Est5', c."pE5")
) AS x(estado, proporcion);

COMMENT ON VIEW reporting."0303_ConteoEstados_Turno" IS
    'Compatibilidad. Despivote de Est1..Est5 con CROSS JOIN LATERAL en vez del UNION ALL de 5 '
    'bloques con el FROM repetido que usaba Access (H-11, patrón 2 de 6). La multiplicación '
    '×5 de filas es correcta y esperada: es el despivote, no un defecto.';

-- ── 0304_ConteoEst_Flo_Turno ─────────────────────────────────────────────────
-- La cadena fenológica completa: Flor + Est1..Est5, cronológica. Descrita en la
-- documentación original como "la vista analítica más valiosa que produce esta base".
CREATE OR REPLACE VIEW reporting."0304_ConteoEst_Flo_Turno" AS
SELECT "Año", "Sem", "Fecha", "Fundo", "Fundo_pptom5", "Modulo", "Turno", "Estado",
       "Cantidad", "SumaTotal", "n"
FROM reporting."0202_FloresTurno"
UNION ALL
SELECT "Año", "Sem", "Fecha", "Fundo", "Fundo_pptom5", "Modulo", "Turno", "Estado",
       "Cantidad", "SumTotal" AS "SumaTotal", "n"
FROM reporting."0303_ConteoEstados_Turno";

COMMENT ON VIEW reporting."0304_ConteoEst_Flo_Turno" IS
    'Compatibilidad. La cadena fenológica Flor→Est1..Est5 en una sola serie. La rama de flores '
    'ya no queda limitada a C2026 (D-6): a diferencia de Access, aquí ambas ramas cubren el '
    'mismo rango de fechas. Para la cadena completa Brotes→Ramas→Flor→Est1..5→Baya→Cosecha, '
    'ver `reporting.v_fenologia`.';

-- ── 0306_FrutosFlores ────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."0306_FrutosFlores" AS
SELECT e."Fundo", e."Modulo", e."Turno", e."Lote", e."Total"::numeric AS "Eval",
       e."SEvConteo" AS "Semana",
       CASE WHEN e."KeyMap" ~ 'L' THEN left(e."KeyMap", position('L' IN e."KeyMap") - 1) END AS "kk",
       'Estadios'::text AS "Conteo"
FROM reporting."0301_ConteoEstados" e
UNION ALL
SELECT f."Fundo", f."Modulo", f."Turno", f."Lote", f."PromFlores",
       f."Sem", f."kk",
       'Flores'::text
FROM reporting."0104_PromFlores" f;

COMMENT ON VIEW reporting."0306_FrutosFlores" IS
    'Compatibilidad. Apila estadios y flores en una sola serie. ATENCIÓN, heredado de Access: '
    'usa SEvConteo (semana de evaluación) para estados y Sem (semana calendario) para flores — '
    'ambos contadores difieren en cientos de días. Es una desalineación temporal ya presente '
    'en el original, no introducida aquí; no promediar "Eval" mezclando ambos Conteo sin '
    'filtrar antes por tipo.';

-- ── 0307_EstadosFlores ───────────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."0307_EstadosFlores" AS
SELECT f."Año"       AS "Año",
       f."Fundo"      AS "Fundo",
       f."Modulo"     AS "Modulo",
       f."Lote"       AS "Lote",
       f."PromFlores" AS "PromFlores",
       e."Total"      AS "Total",
       e."SEvConteo"  AS "SEvConteo"
FROM reporting."0104_PromFlores" f
LEFT JOIN reporting."0301_ConteoEstados" e
       ON f."Fundo" = e."Fundo" AND f."Modulo" = e."Modulo" AND f."Lote" = e."Lote"
      AND f."Sem" = e."SEvConteo" AND f."Año" = e."Año";

COMMENT ON VIEW reporting."0307_EstadosFlores" IS
    'Compatibilidad, fiel a Access con su mismo defecto de grano (no corregido, porque es de '
    'las 30 que sí producían resultado): 0104_PromFlores está a grano de lote+semana, pero '
    '0301_ConteoEstados está a grano de PLANTA — el LEFT JOIN multiplica cada fila de flores '
    'por todas las evaluaciones de planta de esa semana. En Access daba 16.239 filas desde un '
    'origen de 9.040; aquí el mismo patrón se reproduce sobre las cifras nuevas. Además, '
    'empareja Sem (semana calendario) contra SEvConteo (semana de evaluación) — el mismo '
    'desajuste que 0306_FrutosFlores.';

-- ── 0401_Estados_planta ──────────────────────────────────────────────────────
-- Reconocimiento implícito de H-01 en el propio Access: separaba Fundo (físico, de M_Lotes)
-- de Empresa (vocab. B, de E03_ConteoEstados) en vez de asumir que eran el mismo dato.
CREATE OR REPLACE VIEW reporting."0401_Estados_planta" AS
SELECT t.anio    AS "Año",
       t.semana  AS "Sem",
       e.fecha   AS "Fecha",
       l.fundo   AS "Fundo",
       l.empresa AS "Empresa",
       l.modulo  AS "Modulo",
       l.turno   AS "Turno",
       l.lote    AS "Lote",
       e.cortina AS "Cortina",
       e.hilera  AS "Hilera",
       e.planta  AS "Planta",
       e.e1 AS "E1", e.e2 AS "E2", e.e3 AS "E3", e.e4 AS "E4", e.e5 AS "E5",
       e.total   AS "Total"
FROM fact.estados e
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = e.fecha;

COMMENT ON VIEW reporting."0401_Estados_planta" IS
    'Compatibilidad. Detalle a grano de planta, sin agregación. Fundo y Empresa ya no '
    'necesitan ser dos columnas separadas para desambiguar vocabularios (H-01 resuelto en la '
    'carga), pero se conservan las dos por fidelidad de nombres.';

-- ── 0402_ConteoBrotes — CORREGIDA (H-04 caso 1) ──────────────────────────────
-- Rota en Access: referenciaba `E04_ConteoBrotes`, que no existe — el objeto real es
-- `E04_Brotes` (3.385 filas). Error de nombre, no de diseño: todas las columnas que pedía
-- existen en la tabla real. Se construye la versión que la consulta pretendía calcular.
CREATE OR REPLACE VIEW reporting."0402_ConteoBrotes" AS
SELECT b.piso     AS "Piso",
       t.anio     AS "Año",
       t.mes_sem  AS "MesSem",
       t.semana   AS "Sem",
       b.fecha    AS "Fecha",
       l.empresa  AS "Fundo",
       NULL::text AS "Fundo_pptom5",
       l.modulo   AS "Modulo",
       l.turno    AS "Turno",
       l.lote     AS "Lote",
       b.cortina  AS "Cortina",
       b.hilera   AS "Hilera",
       b.planta   AS "Planta",
       b.brotes   AS "Brotes",
       l.key_map  AS "KeyMap"
FROM fact.brotes b
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = b.fecha;

COMMENT ON VIEW reporting."0402_ConteoBrotes" IS
    'Compatibilidad, CORREGIDA (H-04 caso 1): Access referenciaba E04_ConteoBrotes, que no '
    'existe — nunca se pudo ejecutar. El objeto real es E04_Brotes. Fundo_pptom5 no tiene '
    'equivalente en el maestro vigente y queda NULL, documentado (N-21).';

-- ── E — CORREGIDA (H-04 caso 4) ──────────────────────────────────────────────
-- Rota en Access: pedía E03_ConteoEstados.Actividad, columna que solo existe en E01_Ramas.
-- Se construye con el mismo criterio que ya usa core.rama_medicion para su propia
-- Actividad ('ConteoRamas'): un literal por tipo de evaluación, ya que Actividad nunca varió
-- dentro de cada tabla (era una constante, no un dato capturado).
CREATE OR REPLACE VIEW reporting."E" AS
SELECT 'ConteoFlores'::text AS "Actividad",
       l.empresa            AS "Fundo",
       ev.dni               AS "Evaluador",
       f.fecha              AS "Fecha",
       count(f.planta)      AS "plantas",
       sum(f.n_flores)      AS "cant"
FROM fact.flores f
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.evaluador ev ON ev.evaluador_id = f.evaluador_id
GROUP BY l.empresa, ev.dni, f.fecha
UNION ALL
SELECT 'ConteoEstados'::text,
       l.empresa,
       ev.dni,
       e.fecha,
       count(e.lote_id),  -- Access contaba Lote, no Planta, en esta rama — se conserva igual
       sum(e.total)
FROM fact.estados e
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.evaluador ev ON ev.evaluador_id = e.evaluador_id
GROUP BY l.empresa, ev.dni, e.fecha;

COMMENT ON VIEW reporting."E" IS
    'Compatibilidad, CORREGIDA (H-04 caso 4): Access pedía Actividad de E03_ConteoEstados, '
    'columna que no existe ahí — nunca se pudo ejecutar. Productividad por evaluador y día, '
    'flores + estados. Para el análisis completo con ramas y consistencia (CV), ver '
    '`reporting.v_productividad_evaluador`, que ya cubre esto y más (B-5, B-6).';
