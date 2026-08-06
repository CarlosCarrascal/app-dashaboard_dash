-- ============================================================================
-- 70_reporting · 060 · Compatibilidad · forecast (R0xxx)
--
-- Seis consultas: R0801_Forecast_Campaña_SemMes (CORREGIDA), R0801_ResCampaña,
-- R0802_ResumenAño (CORREGIDA), R0901_Forecas_SemAc, R0902_Forecast_Sem_vs_Camp
-- (CORREGIDA), R0903_Forecast_FrtsTotal.
--
-- Vocabulario de fundo en R08_Forecast_Campaña (verificado, N-5): aquí SÍ está invertido
-- respecto al resto de la familia H0xxx/M_ — "Fundo" es la empresa y "FundoPPto" es el
-- fundo físico. fact.forecast_campania ya lo tiene desinvertido y resuelto: empresa_id
-- para "Fundo", y el fundo físico se recupera vía modulo_id → dim.modulo.fundo.
-- ============================================================================

-- ── R0801_Forecast_Campaña_SemMes — CORREGIDA (H-04 caso 5) ──────────────────
-- Rota en Access: pedía M_Time.CampProAra y M_Time.Trimestre, columnas que no existen —
-- M_Time solo tiene 7 columnas. CampProAra intentaba aproximar el concepto de "campaña de
-- producción de arándano", que aquí ya existe resuelto y sin ambigüedad en
-- fact.forecast_campania.campania_id — no hace falta derivarlo de año+semana. Trimestre se
-- toma de core.calendario, con año+semana como clave de búsqueda.
CREATE OR REPLACE VIEW reporting."R0801_Forecast_Campaña_SemMes" AS
WITH tim AS (
    SELECT anio, semana, min(mes_sem) AS mes_sem, min(trimestre) AS trimestre
    FROM core.calendario
    GROUP BY anio, semana
),
plantas_modulo AS (
    SELECT modulo_id, sum(n_plantas) AS n_plantas FROM core.lote GROUP BY modulo_id
)
SELECT cp.campania    AS "CampProAra",
       cp.campania    AS "Campaña",
       vf.version     AS "Version",
       em.empresa     AS "Fundo",
       mo.fundo       AS "FundoPPto",
       mo.modulo      AS "Modulo",
       pm.n_plantas   AS "NPlantas",
       tu.turno       AS "Turno",
       f.anio         AS "Año",
       f.semana       AS "Semana",
       x.descripcion  AS "Descripcion",
       x.valor        AS "Valor",
       f.frutos_exp   AS "FrtTotal_Exp",
       tim.mes_sem    AS "MesSem",
       tim.trimestre  AS "Trimestre"
FROM fact.forecast_campania f
JOIN dim.empresa em USING (empresa_id)
JOIN dim.modulo mo USING (modulo_id)
JOIN dim.turno tu USING (turno_id)
JOIN dim.version_forecast vf USING (version_id)
LEFT JOIN dim.campania cp USING (campania_id)
LEFT JOIN tim ON tim.anio = f.anio AND tim.semana = f.semana
LEFT JOIN plantas_modulo pm USING (modulo_id)
CROSS JOIN LATERAL (VALUES
    ('Kg Exp', f.kg_exp),
    ('Kg Des', f.kg_des),
    ('Kg Con', f.kg_con)
) AS x(descripcion, valor);

COMMENT ON VIEW reporting."R0801_Forecast_Campaña_SemMes" IS
    'Compatibilidad, CORREGIDA (H-04 caso 5): Access pedía M_Time.CampProAra y .Trimestre, que '
    'no existen — nunca se pudo ejecutar. CampProAra y Campaña salen iguales aquí a propósito: '
    'son el mismo dato, ya resuelto en el forecast sin pasar por año+semana.';

-- ── R0801_ResCampaña ─────────────────────────────────────────────────────────
-- El join contra el área/plantas del módulo usa FundoPPto=empresa (no Fundo_pptom5, que no
-- tiene equivalente en el maestro vigente, N-21) contra reporting.M_Mod, ya construida.
-- LEFT JOIN (no INNER): el módulo centinela "SIN_IDENTIFICAR" (ADR-0005) no tiene fila en
-- M_Mod porque no es un módulo real — pero sus 2 filas de forecast deben seguir visibles con
-- Area/NPlantas en NULL, no desaparecer en silencio como pasaría con un INNER JOIN.
CREATE OR REPLACE VIEW reporting."R0801_ResCampaña" AS
SELECT vf.version    AS "Version",
       em.empresa    AS "FundoPPto",
       mo.modulo     AS "Modulo",
       f.anio        AS "Año",
       cp.campania   AS "Campaña",
       sum(f.kg_exp) AS "KG",
       mm."Area"     AS "Area",
       mm."NPlantas" AS "NPlantas"
FROM fact.forecast_campania f
JOIN dim.empresa em USING (empresa_id)
JOIN dim.modulo mo USING (modulo_id)
JOIN dim.version_forecast vf USING (version_id)
LEFT JOIN dim.campania cp USING (campania_id)
LEFT JOIN reporting."M_Mod" mm ON mm."FundoPPto" = em.empresa AND mm."Modulo" = mo.modulo
GROUP BY vf.version, em.empresa, mo.modulo, f.anio, cp.campania, mm."Area", mm."NPlantas";

COMMENT ON VIEW reporting."R0801_ResCampaña" IS
    'Compatibilidad. KG es SUM(KG Exp) — la decisión D-1, ya parametrizada en '
    'core.config_decision. El join original contra M_Mod usaba FundoPPto=Fundo_pptom5, dos '
    'vocabularios distintos que solo coincidían parcialmente ("join sospechoso" en la '
    'auditoría); aquí se une por FundoPPto=empresa, consistente en ambos lados. Es LEFT JOIN: '
    'el módulo centinela SIN_IDENTIFICAR (ADR-0005) no tiene fila en M_Mod y no debe hacer '
    'desaparecer esas filas de forecast.';

-- ── R0802_ResumenAño — CORREGIDA (H-04 caso 3) ────────────────────────────────
-- Rota en Access: la rama "Forecast" referenciaba R0901_ResCampaña, que no existe — el
-- objeto real es R0801_ResCampaña (error de un dígito). Se conserva la inconsistencia de
-- mayúsculas entre "año" (rama Real) y "Año" (rama Forecast): ya estaba en el original y el
-- UNION ALL es por posición, no por nombre — no cambia el resultado, solo el nombre final.
CREATE OR REPLACE VIEW reporting."R0802_ResumenAño" AS
SELECT 'Real'::text AS "Version",
       cosecha."FundoPPto", cosecha."Modulo", cosecha."año", cosecha."Campaña",
       cosecha."KG", mm."Area", mm."NPlantas"
FROM (
    SELECT "FundoPPto", "Modulo", "año", "Campaña", sum("KG") AS "KG"
    FROM reporting."H0103_ResModulo"
    GROUP BY "FundoPPto", "Modulo", "año", "Campaña"
) cosecha
JOIN reporting."M_Mod" mm ON mm."FundoPPto" = cosecha."FundoPPto" AND mm."Modulo" = cosecha."Modulo"
UNION ALL
SELECT "Version", "FundoPPto", "Modulo", "Año", "Campaña", "KG", "Area", "NPlantas"
FROM reporting."R0801_ResCampaña";

COMMENT ON VIEW reporting."R0802_ResumenAño" IS
    'Compatibilidad, CORREGIDA (H-04 caso 3): Access referenciaba R0901_ResCampaña, que no '
    'existe — nunca se pudo ejecutar. El objeto real es R0801_ResCampaña. "Real" (cosecha) '
    'hereda el defecto de grano de H0103_ResModulo (año calendario vs. campaña, N-11), sin '
    'corregir aquí porque no es de las 6 rotas.';

-- ── R0901_Forecas_SemAc ──────────────────────────────────────────────────────
-- CORRECCIÓN DE FIDELIDAD (D-6): sin el filtro fijo Campaña IN ('C2025','C2026'). El filtro
-- de fondo — quedarse solo con el pronóstico vigente de cada semana — se conserva, pero
-- usando dim.version_forecast.semana_emision (ya parseado con una expresión regular, ADR-0005)
-- en vez del parseo frágil Int(Right(Left(Version,3),2)), que fallaba en silencio si el
-- código no tenía forma exacta "Snn" y no desambiguaba sufijos de iteración (N-5).
CREATE OR REPLACE VIEW reporting."R0901_Forecas_SemAc" AS
SELECT cp.campania          AS "Campaña",
       l.empresa            AS "Fundo",
       l.modulo             AS "Mod",
       l.turno              AS "Turno",
       l.lote               AS "Lote",
       l.area_ha            AS "Area",
       f.fecha_cos_ant      AS "FCosAnt",
       f.fecha_cos          AS "FCos",
       f.semana             AS "Sem",
       f.frutos_por_planta  AS "FrtCos",
       f.rendimiento        AS "Rend",
       f.kg                 AS "Kg",
       f.dr                 AS "Dr",
       vf.version           AS "Version",
       l.fundo              AS "FundPPTo"
FROM fact.forecast_semanal f
JOIN dim.lote l USING (lote_id)
JOIN dim.version_forecast vf USING (version_id)
LEFT JOIN dim.campania cp USING (campania_id)
WHERE vf.semana_emision = f.semana;

COMMENT ON VIEW reporting."R0901_Forecas_SemAc" IS
    'Compatibilidad, CORREGIDA (D-6 + N-5): sin el filtro fijo de campaña. El parseo frágil de '
    'la versión se reemplaza por dim.version_forecast.semana_emision, ya resuelto con regex y '
    'sin ambigüedad de iteración (ADR-0005) — el original podía contar una misma semana hasta '
    'tres veces si había varias iteraciones (S27, S27_v2, S27_v3).';

-- ── R0902_Forecast_Sem_vs_Camp — CORREGIDA (H-04 caso 6) ─────────────────────
-- Rota en Access: la rama de campaña seleccionaba R08_Forecast_Campaña.KG, columna que no
-- existe (son KG Exp / Kg Des / Kg Con) — nunca se pudo ejecutar. Se usa KG Exp, la misma
-- decisión D-1 que ya rige en R0801_ResCampaña.
--
-- Se conserva, sin corregir, el defecto ya documentado (D-1/H-04 caso 6): ninguna rama
-- filtra por Version, así que sumar esto sin filtrar mezcla escenarios de forecast distintos
-- del mismo periodo — de ahí que la cifra total no cuadre con la cosecha real si no se filtra.
CREATE OR REPLACE VIEW reporting."R0902_Forecast_Sem_vs_Camp" AS
SELECT 'Proy.' || vf.version AS "Version",
       l.empresa             AS "Fundo",
       l.modulo              AS "Mod",
       t.anio                AS "Año",
       t.semana               AS "Sem",
       sum(f.kg)              AS "Kg",
       cp.campania            AS "Campaña"
FROM fact.forecast_semanal f
JOIN dim.lote l USING (lote_id)
JOIN dim.version_forecast vf USING (version_id)
LEFT JOIN dim.campania cp USING (campania_id)
LEFT JOIN dim.tiempo t ON t.fecha = f.fecha_cos
GROUP BY vf.version, l.empresa, l.modulo, t.anio, t.semana, cp.campania
UNION ALL
SELECT vf.version   AS "Version",
       em.empresa   AS "Fundo",
       mo.modulo    AS "Mod",
       f.anio       AS "Año",
       f.semana     AS "Sem",
       f.kg_exp     AS "Kg",
       cp.campania  AS "Campaña"
FROM fact.forecast_campania f
JOIN dim.empresa em USING (empresa_id)
JOIN dim.modulo mo USING (modulo_id)
JOIN dim.version_forecast vf USING (version_id)
LEFT JOIN dim.campania cp USING (campania_id);

COMMENT ON VIEW reporting."R0902_Forecast_Sem_vs_Camp" IS
    'Compatibilidad, CORREGIDA (H-04 caso 6): Access pedía R08_Forecast_Campaña.KG, columna '
    'que no existe (son KG Exp/Kg Des/Kg Con) — nunca se pudo ejecutar. Se usa KG Exp (D-1). '
    'SIN CORREGIR a propósito, porque no es parte de lo que rompía la consulta: ninguna rama '
    'filtra por Version, así que sumar sin filtrar mezcla escenarios distintos del mismo '
    'periodo. Toda medida sobre esta vista debe filtrar una Version.';

-- ── R0903_Forecast_FrtsTotal ─────────────────────────────────────────────────
-- El INNER JOIN original resolvía el lote por texto (Lote+Mod+Fundo_pptom5) y perdía el 54%
-- de las filas sin coincidencia (N-5). Aquí el lote ya viene resuelto por lote_id desde la
-- carga (con fila centinela para las 23 que no resolvían, ADR-0005): las 48.368 filas
-- conservan su frutosT, no solo el 46% que sobrevivía en Access.
CREATE OR REPLACE VIEW reporting."R0903_Forecast_FrtsTotal" AS
SELECT cp.campania          AS "Campaña",
       l.empresa            AS "Fundo",
       l.modulo             AS "Mod",
       l.turno              AS "Turno",
       l.lote               AS "Lote",
       l.area_ha            AS "Area",
       f.fecha_cos_ant      AS "FCosAnt",
       f.fecha_cos          AS "FCos",
       f.semana             AS "Sem",
       f.frutos_por_planta  AS "FrtCos",
       f.rendimiento        AS "Rend",
       f.kg                 AS "Kg",
       f.dr                 AS "Dr",
       vf.version           AS "Version",
       l.fundo              AS "FundPPTo",
       l.n_plantas * f.frutos_por_planta AS "frutosT"
FROM fact.forecast_semanal f
JOIN dim.lote l USING (lote_id)
JOIN dim.version_forecast vf USING (version_id)
LEFT JOIN dim.campania cp USING (campania_id);

COMMENT ON VIEW reporting."R0903_Forecast_FrtsTotal" IS
    'Compatibilidad. El join original por texto (Lote+Mod+Fundo_pptom5) descartaba el 54% de '
    'las filas sin coincidencia (N-5); aquí el lote_id ya viene resuelto desde la carga, así '
    'que las 48.368 filas tienen frutosT, no solo 22.272 como en Access.';
