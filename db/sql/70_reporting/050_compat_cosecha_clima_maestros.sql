-- ============================================================================
-- 70_reporting · 050 · Compatibilidad · cosecha, clima y maestros (H0xxx, M_, R01)
--
-- Trece consultas: H0100_Resumen_kgCosecha, H0102_Producciondiaria, H0103_ResModulo,
-- H0104_FechaFinCosecha, H0105_RendTurno_paña, H0201_PesoBaya_Elifab,
-- H0501_VariablesClima, H0502_Temperatura_variacion, M_EdadCultivo, M_Lote_turno,
-- M_Mod, TPlantas, y la CORREGIDA R0101_KgCosecha.
-- (H0101_ResumenHistoricos ya está en 020_compat_campania.sql.)
--
-- Convención de vocabulario de fundo en esta familia (verificada contra el join real de
-- Access, no supuesta): "Fundo" y "FundoPPto" son el MISMO valor (empresa, vocab B) — se
-- prueba porque el join original es `M_Lotes.FundoPPto = H00_VolumenCampo.Fundo`, y ya
-- sabemos que H00.Fundo es vocab B. "Fundo_pptom5" es una tercera agrupación (en 5 grupos)
-- que no tiene equivalente en el maestro vigente y queda NULL, documentado (N-21).
--
-- H0104 y H0105 tenían un filtro de campaña fijo en el SQL (C2026 y C2025 respectivamente).
-- No se reproduce (D-6): la campaña queda como columna para que Power BI filtre.
-- ============================================================================

-- ── H0100_Resumen_kgCosecha ──────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."H0100_Resumen_kgCosecha" AS
SELECT c.campania  AS "Campaña",
       c.fecha     AS "Fecha",
       c.empresa   AS "Fundo",
       c.variedad  AS "Variedad",
       c.modulo    AS "Modulo",
       c.turno     AS "Turno",
       c.lote      AS "Lote",
       c.kg        AS "KG",
       c.semana    AS "Sem",
       c.anio      AS "Año",
       c.n_plantas AS "NPlantas"
FROM reporting.v_cosecha c
WHERE c.en_h00;

COMMENT ON VIEW reporting."H0100_Resumen_kgCosecha" IS
    'Compatibilidad. Solo las filas que vienen de H00_VolumenCampo (en_h00), con Turno y '
    'NPlantas ya resueltos desde la carga en vez del join roto de H-01.';

-- ── H0102_Producciondiaria ───────────────────────────────────────────────────
-- "La versión más limpia de la familia": el INNER JOIN original eliminaba automáticamente
-- las filas de subtotal de H-06 y los huérfanos de H-01. Aquí el filtro en_h01 hace lo mismo.
CREATE OR REPLACE VIEW reporting."H0102_Producciondiaria" AS
SELECT c.empresa   AS "Fundo",
       c.campania  AS "Campaña",
       c.modulo    AS "Modulo",
       c.turno     AS "Turno",
       c.lote      AS "Lote",
       c.n_plantas AS "NPlantas",
       c.fecha     AS "Fecha",
       c.semana    AS "Sem",
       c.anio      AS "Año",
       c.kg_h01    AS "KG",
       c.pana      AS "Paña",
       c.peso_baya AS "Peso",
       c.area_ha   AS "Area"
FROM reporting.v_cosecha c
WHERE c.en_h01;

COMMENT ON VIEW reporting."H0102_Producciondiaria" IS
    'Compatibilidad. KG es el de H01 (kg_h01), porque esta consulta parte de H01_ProdHistorica, '
    'no de H00. Para el KG de referencia de la campaña, usar H0100 o v_cosecha.kg.';

-- ── H0103_ResModulo ──────────────────────────────────────────────────────────
-- FIEL a Access con su defecto de grano conocido (no corregido: es de las 30 que sí
-- funcionaban): agrupa por año CALENDARIO y por Campaña a la vez. Como las campañas se
-- solapan (N-11: C2025 va de 2025-03-14 a 2026-03-05), una campaña que cruza fin de año
-- queda partida en dos filas. No es nuevo aquí, ya lo hacía así el original.
CREATE OR REPLACE VIEW reporting."H0103_ResModulo" AS
SELECT c.empresa                       AS "Fundo",
       c.campania                      AS "Campaña",
       c.modulo                        AS "Modulo",
       extract(year FROM c.fecha)::int AS "año",
       sum(c.kg_h01)                   AS "KG",
       c.empresa                       AS "FundoPPto",
       NULL::text                      AS "Fundo_pptom5"
FROM reporting.v_cosecha c
WHERE c.en_h01
GROUP BY c.empresa, c.campania, c.modulo, extract(year FROM c.fecha);

COMMENT ON VIEW reporting."H0103_ResModulo" IS
    'Compatibilidad, FIEL a un defecto conocido no corregido: agrupa por año calendario y '
    'campaña a la vez, y las campañas se solapan entre años (N-11) — una campaña que cruza '
    'el 31 de diciembre queda partida en dos filas, igual que en Access.';

-- ── H0104_FechaFinCosecha ────────────────────────────────────────────────────
-- CORRECCIÓN DE FIDELIDAD (D-6): Access fijaba HAVING Campaña="C2026" en la subconsulta que
-- calcula la última paña — quedaba obsoleta en cuanto empezara otra campaña. Aquí se calcula
-- para TODAS las campañas; Power BI filtra por Campaña.
CREATE OR REPLACE VIEW reporting."H0104_FechaFinCosecha" AS
SELECT h."Fundo", h."Campaña", h."Modulo", h."Turno", h."Lote", h."Area", h."NPlantas",
       h."KG", h."Paña", h."FrutosT", h."FecPon", h."FInicio", h."Fecha", h."Semana",
       h."anio", h."ModTur", h."FundoPPto", h."Fundo_pptom5"
FROM reporting."H0101_ResumenHistoricos" h
JOIN (
    SELECT "Fundo", "Campaña", "Modulo", "Turno", "Lote", max("Paña") AS "ultPaña"
    FROM reporting."H0101_ResumenHistoricos"
    GROUP BY "Fundo", "Campaña", "Modulo", "Turno", "Lote"
) fin
  ON h."Paña" = fin."ultPaña" AND h."Lote" = fin."Lote" AND h."Modulo" = fin."Modulo"
 AND h."Campaña" = fin."Campaña" AND h."Fundo" = fin."Fundo";

COMMENT ON VIEW reporting."H0104_FechaFinCosecha" IS
    'Compatibilidad, CORREGIDA (D-6): Access fijaba la campaña en C2026 dentro de la '
    'subconsulta que busca la última paña — quedaba obsoleta en cuanto empezara otra campaña. '
    'Aquí calcula la última paña de cada campaña, todas a la vez.';

-- ── H0105_RendTurno_paña ─────────────────────────────────────────────────────
-- CORRECCIÓN DE FIDELIDAD (D-6): Access fijaba HAVING Campaña="C2025". Se quita, igual que
-- en H0104. Además, el join original usaba Fundo_pptom5 como parte de la clave — como esa
-- columna no tiene equivalente en el maestro vigente (queda NULL), se sustituye por Fundo
-- (empresa), que es al menos tan selectivo. El filtro Turno<>'T00' SÍ se conserva: es un
-- filtro de negocio real (excluye el turno administrativo), no un recorte de campaña.
CREATE OR REPLACE VIEW reporting."H0105_RendTurno_paña" AS
SELECT k."Campaña", k."Fundo", k."Modulo", k."Turno", k."Paña", k."KG", k."FrutosT",
       k."FecPon", k."Fundo_pptom5", a."Area", a."NPlantas"
FROM (
    SELECT "Fundo", "Campaña", "Modulo", "Turno", "Paña",
           sum("KG")::numeric      AS "KG",
           sum("FrutosT")::numeric AS "FrutosT",
           sum("FecPon")::numeric  AS "FecPon",
           "Fundo_pptom5"
    FROM reporting."H0101_ResumenHistoricos"
    GROUP BY "Fundo", "Campaña", "Modulo", "Turno", "Paña", "Fundo_pptom5"
) k
JOIN (
    SELECT l.empresa AS "Fundo", l.modulo AS "Modulo", l.turno AS "Turno",
           sum(l.area_ha)   AS "Area",
           sum(l.n_plantas) AS "NPlantas"
    FROM dim.lote l
    WHERE l.turno <> 'T00' AND NOT l.es_sentinel
    GROUP BY l.empresa, l.modulo, l.turno
) a ON k."Turno" = a."Turno" AND k."Modulo" = a."Modulo" AND k."Fundo" = a."Fundo";

COMMENT ON VIEW reporting."H0105_RendTurno_paña" IS
    'Compatibilidad, CORREGIDA (D-6): sin el filtro fijo Campaña="C2025". El join contra el '
    'área y plantas del turno usa Fundo (empresa) en vez de Fundo_pptom5, que no tiene '
    'equivalente en el maestro vigente (N-21).';

-- ── H0201_PesoBaya_Elifab ────────────────────────────────────────────────────
-- El productor→empresa (antes M_EquivalenciaElifab) y el módulo normalizado (antes una
-- fórmula IIf/Format ad-hoc sobre texto crudo) ya vienen resueltos desde la carga (N-2, H-10).
-- peso_kg es la columna correcta a sumar — la otra, peso_kg_lote, es un total repetido por
-- fila y NO debe usarse aquí (N-16).
CREATE OR REPLACE VIEW reporting."H0201_PesoBaya_Elifab" AS
WITH eli AS (
    SELECT p.empresa_id, p.modulo_id, p.fecha_cosecha, p.calibre_id,
           sum(p.peso_kg)  AS "Pesototal",
           sum(p.recuento) AS "Recuento"
    FROM fact.packing p
    JOIN dim.calibre c USING (calibre_id)
    WHERE NOT c.es_descarte
    GROUP BY p.empresa_id, p.modulo_id, p.fecha_cosecha, p.calibre_id
),
cam AS (
    SELECT c.campania_id, l.empresa, l.modulo,
           min(c.fecha) AS "MínF", max(c.fecha) AS "MáxF"
    FROM fact.cosecha c
    JOIN dim.lote l USING (lote_id)
    WHERE c.en_h01
    GROUP BY c.campania_id, l.empresa, l.modulo
)
SELECT em.empresa                AS "Empresa",
       mo.modulo                 AS "modulo",
       eli.fecha_cosecha         AS "Fecha Cosecha",
       to_char(eli.fecha_cosecha, 'Mon') AS "Mes",
       extract(year FROM eli.fecha_cosecha)::int AS "año",
       eli."Pesototal"           AS "Pesototal",
       eli."Recuento"            AS "Recuento",
       cam2.campania             AS "Campaña",
       ca.calibre                AS "Calibre"
FROM eli
JOIN dim.empresa em USING (empresa_id)
JOIN dim.modulo mo USING (modulo_id)
JOIN dim.calibre ca USING (calibre_id)
LEFT JOIN cam ON cam.empresa = em.empresa AND cam.modulo = mo.modulo
            AND eli.fecha_cosecha BETWEEN cam."MínF" AND cam."MáxF"
LEFT JOIN dim.campania cam2 ON cam2.campania_id = cam.campania_id;

COMMENT ON VIEW reporting."H0201_PesoBaya_Elifab" IS
    'Compatibilidad. Pesototal usa peso_kg (la parte, sumable) — NUNCA peso_kg_lote, que es un '
    'total repetido por fila y multiplicaría los kilos (N-16). El productor→empresa y el '
    'módulo normalizado ya vienen resueltos desde la carga (N-2, H-10), no de una fórmula '
    'ad-hoc sobre texto crudo. Excluye Descarte con dim.calibre.es_descarte.';

-- ── H0501_VariablesClima ─────────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."H0501_VariablesClima" AS
SELECT t.anio    AS "Año",
       t.mes     AS "Mes",
       t.semana  AS "Sem",
       cl.fecha_hora::date AS "Fecha",
       cl.temp_alta AS "TembAlta",
       cl.temp_baja AS "TempBaja",
       (cl.temp_alta - cl.temp_baja) AS "varTemp",
       cl.humedad   AS "Humedad",
       cl.indice_calor AS "IndiceCalor",
       cl.lluvia    AS "Lluvia",
       cl.rad_sol   AS "RadSol",
       cl.rad_sol_alta AS "RadSolAlta",
       cl.dg_calentamiento AS "DGCalentamiento",
       cl.dg_enfriamiento AS "DGEnfriamiento",
       cl.et_mm     AS "ET-mm",
       CASE WHEN cl.temp < 15 THEN 'T10-15'
            WHEN cl.temp < 20 THEN 'T15-20'
            WHEN cl.temp < 25 THEN 'T20-25'
            WHEN cl.temp < 30 THEN 'T25-30'
            ELSE 'T30>0' END AS "TipoHora",
       CASE WHEN abs(cl.temp_alta - cl.temp_baja) < 0.5  THEN '+-0.5'
            WHEN abs(cl.temp_alta - cl.temp_baja) < 1    THEN '+-1.0'
            WHEN abs(cl.temp_alta - cl.temp_baja) < 2.5  THEN '+-2.5'
            WHEN abs(cl.temp_alta - cl.temp_baja) < 5    THEN '+-5.0'
            WHEN abs(cl.temp_alta - cl.temp_baja) < 9.9  THEN '+-9.9'
            ELSE '>9.9' END AS "catVar",
       cl.vel_viento AS "VelViento"
FROM core.clima cl
LEFT JOIN dim.tiempo t ON t.fecha = cl.fecha_hora::date;

COMMENT ON VIEW reporting."H0501_VariablesClima" IS
    'Compatibilidad. Lee core.clima directo (no fact.clima) porque necesita temp y las dos '
    'temperaturas por separado en la misma fila. Los 2.079 instantes duplicados por recarga '
    '(H-08) ya quedaron fuera en la carga.';

-- ── H0502_Temperatura_variacion ──────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."H0502_Temperatura_variacion" AS
SELECT "Año", "Mes", "Sem", "Fecha",
       max("TembAlta")                    AS "Tmax",
       min("TempBaja")                    AS "Tmin",
       max("TembAlta") - min("TempBaja")  AS "varDia"
FROM reporting."H0501_VariablesClima"
GROUP BY "Año", "Mes", "Sem", "Fecha";

-- ── M_EdadCultivo ─────────────────────────────────────────────────────────────
-- Usa CURRENT_DATE, igual que Access usaba Now(): el resultado depende de cuándo se consulta,
-- no es un dato congelado. Así lo calculaba el original.
--
-- CORRECCIÓN DE FIDELIDAD (encontrada al verificar): Access excluía Lote="L000" como fila
-- placeholder única. En el maestro vigente la identidad es (empresa, módulo, lote), así que
-- "L000" no es un código global: hay 19 filas con ese código, y 6 de ellas son lotes REALES
-- de los módulos nuevos M19-M24 (55,8 ha y 312.513 plantas cada uno, con siembra futura) —
-- filtrar por el texto perdería esos 6 lotes. El criterio correcto es área y plantas en cero,
-- que sí identifica las 13 filas que son placeholder de verdad.
CREATE OR REPLACE VIEW reporting."M_EdadCultivo" AS
SELECT l.empresa                         AS "FundoPPto",
       NULL::text                        AS "Fundo_pptom5",
       l.modulo                          AS "Modulo",
       l.turno                           AS "Turno",
       l.lote                            AS "Lote",
       l.area_ha                         AS "Area",
       l.fecha_siembra                   AS "FSiembra",
       (current_date - l.fecha_siembra) / 365.0 AS "Edad"
FROM dim.lote l
WHERE NOT (l.area_ha = 0 AND l.n_plantas = 0) AND NOT l.es_sentinel;

COMMENT ON VIEW reporting."M_EdadCultivo" IS
    'Compatibilidad. Edad se recalcula cada vez que se consulta (CURRENT_DATE), igual que '
    'Access con Now(): no es un valor congelado en el tiempo.';

-- ── M_Lote_turno ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."M_Lote_turno" AS
SELECT l.empresa       AS "Fundo",
       l.variedad      AS "Variedad",
       l.modulo        AS "Modulo",
       l.turno         AS "Turno",
       l.lote          AS "Lote",
       l.area_ha       AS "Area",
       l.n_plantas     AS "NPlantas",
       l.fecha_siembra AS "FSiembra",
       l.maceta        AS "Maceta",
       l.tipo_fibra    AS "TipoFibra",
       l.mod_turno     AS "ModTur"
FROM dim.lote l
WHERE NOT l.es_sentinel;

COMMENT ON VIEW reporting."M_Lote_turno" IS
    'Compatibilidad. Pase directo del maestro vigente (879 lotes), no del M_Lotes de Access '
    '(860, sustituido por ADR-0003).';

-- ── M_Mod ─────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."M_Mod" AS
SELECT l.empresa   AS "Fundo",
       l.empresa   AS "FundoPPto",
       NULL::text  AS "Fundo_pptom5",
       l.modulo    AS "Modulo",
       sum(l.area_ha)   AS "Area",
       sum(l.n_plantas) AS "NPlantas"
FROM dim.lote l
WHERE NOT l.es_sentinel
GROUP BY l.empresa, l.modulo;

COMMENT ON VIEW reporting."M_Mod" IS
    'Compatibilidad. Del maestro vigente, no del M_Lotes de Access. Fundo_pptom5 sin '
    'equivalente en el maestro vigente, NULL documentado (N-21).';

-- ── TPlantas ──────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting."TPlantas" AS
SELECT l.empresa AS "FundoPPto",
       l.modulo  AS "Modulo",
       sum(l.n_plantas) AS "TotalPlantas"
FROM dim.lote l
WHERE NOT l.es_sentinel
GROUP BY l.empresa, l.modulo;

COMMENT ON VIEW reporting."TPlantas" IS
    'Compatibilidad. Redundante con M_Mod, que ya trae SUM(NPlantas) al mismo grano más el '
    'Area (H-11, caso menor) — se conserva por si algún informe la consume directo.';

-- ── R0101_KgCosecha — CORREGIDA (H-04 caso 2) ────────────────────────────────
-- Rota en Access: referenciaba `R01_VolumenCampo`, que no existe — el objeto real es
-- `H00_VolumenCampo`. Una vez corregido el nombre, la consulta es estructuralmente
-- IDÉNTICA a H0100_Resumen_kgCosecha (mismas tablas, mismos joins, mismas columnas): por
-- eso se expone como un alias en vez de duplicar la lógica.
CREATE OR REPLACE VIEW reporting."R0101_KgCosecha" AS
SELECT * FROM reporting."H0100_Resumen_kgCosecha";

COMMENT ON VIEW reporting."R0101_KgCosecha" IS
    'Compatibilidad, CORREGIDA (H-04 caso 2): Access referenciaba R01_VolumenCampo, que no '
    'existe — nunca se pudo ejecutar. El objeto real es H00_VolumenCampo, y con eso corregido '
    'la consulta queda idéntica a H0100_Resumen_kgCosecha.';
