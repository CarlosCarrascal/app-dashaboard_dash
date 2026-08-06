-- ============================================================================
-- 70_reporting · 070 · Analítica · panel módulo × semana
--
-- Base para el análisis de relación entre variables y kg/ha: una fila por módulo,
-- campaña y semana, con la cosecha real y las variables ambientales y de tiempo
-- térmico alineadas a esa misma semana.
--
-- No sustituye a las vistas de compatibilidad (010-060): esas reproducen lo que Access
-- exponía. Esta es nueva y existe para el análisis de variables, así que no imita
-- ningún nombre ni columna del origen.
--
-- ── Cinco decisiones que hay que conocer antes de usarla ────────────────────
--
-- 1 · SEMANA = `core.calendario.anio_semana`, que usa el AÑO ISO. No se agrupa por
--     (anio, semana): ese par mezcla el año calendario con la semana ISO y produce
--     celdas contaminadas — verificado, (2025, semana 1) reúne 428 filas de cosecha y
--     309.190 kg fechados entre 2025-01-02 y 2025-12-31, o sea enero y diciembre en la
--     misma celda. Tampoco se usa sem_ev_conteo, que solo cubre 1.224 de 2.189 días y
--     difiere de la semana en 527: unir por ahí es el hallazgo H-05 (explosión ×54).
--
-- 2 · Se EXCLUYEN los lotes `es_ficticio` (los L000). Son totales de módulo disfrazados
--     de lote: 19 filas que aportan 311,61 ha de las 1.140 (37,6% de inflación) y
--     cargan 118.284 kg. Sin ellos el área es 828,46 ha, que reconcilia con las
--     829,02 ha auditadas en Access. Incluirlos hunde el kg/ha de todos los módulos.
--
-- 3 · El clima NO tiene grano espacial: una sola estación, sin columna de lote, módulo
--     ni fundo. Por eso las columnas `*_semana` son idénticas para todos los módulos de
--     la misma semana (rango entre módulos medido = 0,00) y NO pueden explicar por qué
--     un módulo rinde distinto de otro. Las que sí discriminan por módulo son las
--     `*_acum_poda`: acumulan desde la poda de CADA módulo, así que la misma serie
--     global se convierte en tiempo térmico propio de cada uno.
--
-- Sin campaña fija (regla D-6): se expone `campania` como columna y el consumidor
-- filtra.
--
-- 4 · Riego (`riego_mm`, `riego_m3`) viene de core.riego_semanal — 4 Excel de Riego/
--     Operaciones, 2025, ajenos a Access. Solo cubre Aqu Anqa 1-4 y M11 (de Aqu Anqa
--     5): no hay riego para M16-M18 ni Aqu Anqa 6, y `riego_mm` queda NULL ahí, no en
--     0 — 0 significaría "se midió y no se regó", que no es lo que pasó. `riego_estimado`
--     avisa cuándo la semana incluye el reparto de M10A/M10B (D-7).
--
-- 5 · `modulo` (M01, M02...) NO ES ÚNICO GLOBALMENTE. Verificado: hay un M01 en Aqu
--     Anqa 1 y OTRO M01 distinto en Aqu Anqa 2 (modulo_id 8 y 2 — 9 pares de módulo se
--     repiten entre fundos, ver el comentario de core.lote). Agrupar, filtrar o
--     entrenar un modelo por la columna `modulo` a solas MEZCLA módulos físicos
--     distintos con historias de poda, área y cosecha distintas. La clave real es
--     `modulo_id`, expuesta como primera columna — úsala para agrupar; `modulo` y
--     `fundo` son solo para leer.
-- ============================================================================

-- ── Clima diario, con GDD agronómico calculado ───────────────────────────────
-- La estación mide cada 15 minutos (95,7 registros/día). Aquí se colapsa a día, que es
-- el grano en el que el GDD tiene sentido: la fórmula estándar usa la máxima y la mínima
-- del DÍA, no el promedio de las lecturas.
CREATE OR REPLACE VIEW reporting.v_clima_diario AS
SELECT ca.fecha,
       ca.anio_semana,
       count(*)                                   AS lecturas,
       -- Un día con pocas lecturas da una máxima y una mínima poco fiables. Se marca en
       -- lugar de descartarlo, para que el consumidor decida.
       (count(*) >= 90)                           AS dia_completo,
       round(avg(cl.temp), 3)                     AS temp_media,
       round(max(cl.temp_alta), 3)                AS temp_max,
       round(min(cl.temp_baja), 3)                AS temp_min,
       -- GDD = max((Tmax + Tmin)/2 - base, 0), con la base en core.config_decision.
       -- NO se usa cl.dg_calentamiento: es grado-día de CLIMATIZACIÓN, correlaciona
       -- -0,79 con la temperatura, y como "temperatura acumulada" invertiría el signo.
       round(greatest(
           (max(cl.temp_alta) + min(cl.temp_baja)) / 2
             - core.fn_config('clima.gdd_temp_base')::numeric,
           0), 3)                                 AS gdd,
       round(sum(cl.et_mm), 3)                    AS eto_mm,
       round(sum(cl.lluvia), 3)                   AS lluvia_mm,
       round(avg(cl.humedad), 3)                  AS humedad_media,
       round(avg(cl.vel_viento), 3)               AS viento_medio,
       round(sum(cl.rad_sol), 3)                  AS rad_solar
FROM core.clima cl
JOIN core.calendario ca ON ca.fecha = cl.fecha_hora::date
GROUP BY ca.fecha, ca.anio_semana;

COMMENT ON VIEW reporting.v_clima_diario IS
    'Clima por día, de la única estación del fundo. `gdd` es el grado-día de CRECIMIENTO '
    'calculado aquí desde la máxima y la mínima del día, con la base de '
    'core.config_decision(clima.gdd_temp_base) — no es la columna dg_calentamiento del '
    'origen, que mide climatización y va en sentido contrario a la temperatura. '
    '`dia_completo` marca los días con al menos 90 de las 96 lecturas esperadas.';

-- ── Poda de referencia por módulo y campaña ──────────────────────────────────
-- Un módulo tiene decenas de lotes con fechas de poda distintas, así que "la poda del
-- módulo" no existe: se toma la media ponderada por área y se exponen el mínimo y el
-- máximo para que la dispersión quede a la vista, no escondida en el promedio.
CREATE OR REPLACE VIEW reporting.v_poda_modulo AS
SELECT l.modulo_id,
       p.campania_id,
       (date '2000-01-01' + (
           sum((p.fecha_inicio::date - date '2000-01-01') * l.area_ha)
             / nullif(sum(l.area_ha), 0)
       )::integer)                                      AS poda_ref,
       min(p.fecha_inicio)::date                        AS poda_min,
       max(p.fecha_inicio)::date                        AS poda_max,
       max(p.fecha_inicio)::date
         - min(p.fecha_inicio)::date                     AS poda_dispersion_dias,
       count(*)                                          AS lotes_con_poda
FROM core.poda p
JOIN core.lote l ON l.lote_id = p.lote_id
WHERE NOT l.es_ficticio
  AND NOT l.es_sentinel
  AND l.area_ha > 0
  AND p.fecha_inicio IS NOT NULL      -- 54 filas sin fecha, hallazgo N-20 (cero de Excel)
GROUP BY l.modulo_id, p.campania_id;

COMMENT ON VIEW reporting.v_poda_modulo IS
    'Fecha de poda de referencia por módulo y campaña: media ponderada por área de los '
    'lotes del módulo. Es el origen del tiempo agronómico — en arándano el desarrollo se '
    'mide en días y en grados-día desde la poda, no en fechas absolutas. '
    '`poda_dispersion_dias` advierte cuándo el promedio representa mal al módulo porque '
    'sus lotes se podaron muy separados.';

-- ── El panel ─────────────────────────────────────────────────────────────────
-- DROP y no solo CREATE OR REPLACE: cambiar el orden o el tipo de las columnas (como
-- pasó al agregar riego_m3/riego_dias_con_registro/riego_estimado) no lo permite
-- PostgreSQL sobre una vista existente. Mismo patrón que fact.forecast_semanal.
DROP VIEW IF EXISTS reporting.v_analitica_modulo_semana;

CREATE VIEW reporting.v_analitica_modulo_semana AS
WITH semana AS (
    -- Rango real de cada semana ISO, tomado del propio calendario del modelo.
    SELECT anio_semana,
           min(fecha) AS fecha_inicio,
           max(fecha) AS fecha_fin,
           count(*)   AS dias
    FROM core.calendario
    GROUP BY anio_semana
),
clima_semana AS (
    SELECT anio_semana,
           round(avg(temp_media), 3)   AS temp_media,
           round(max(temp_max), 3)     AS temp_max,
           round(min(temp_min), 3)     AS temp_min,
           round(sum(gdd), 3)          AS gdd,
           round(sum(eto_mm), 3)       AS eto_mm,
           round(sum(lluvia_mm), 3)    AS lluvia_mm,
           round(avg(humedad_media), 3) AS humedad_media,
           count(*)                    AS dias_con_clima,
           count(*) FILTER (WHERE NOT dia_completo) AS dias_incompletos
    FROM reporting.v_clima_diario
    GROUP BY anio_semana
),
cosecha_semana AS (
    SELECT l.modulo_id,
           co.campania_id,
           ca.anio_semana,
           round(sum(co.kg), 3)                AS kg,
           count(*)                            AS registros_cosecha,
           count(DISTINCT co.lote_id)          AS lotes_cosechados,
           max(co.pana)                        AS pana_max,
           round(avg(co.peso_baya), 4)         AS peso_baya_medio
    FROM core.cosecha co
    JOIN core.lote l       ON l.lote_id = co.lote_id
    JOIN core.calendario ca ON ca.fecha = co.fecha
    WHERE NOT l.es_ficticio AND NOT l.es_sentinel
    GROUP BY l.modulo_id, co.campania_id, ca.anio_semana
),
modulo_area AS (
    -- Denominador de kg/ha: el área productiva del módulo, estable en el tiempo.
    SELECT modulo_id,
           round(sum(area_ha), 4) AS area_ha,
           sum(n_plantas)         AS n_plantas,
           count(*)               AS lotes
    FROM core.lote
    WHERE NOT es_ficticio AND NOT es_sentinel AND area_ha > 0
    GROUP BY modulo_id
)
SELECT
    -- ── Identificación ──
    -- `modulo` (M01, M02...) NO es único globalmente: cada fundo reinicia su propia
    -- numeración, y hay un M01 en Aqu Anqa 1 y OTRO M01 distinto en Aqu Anqa 2 (9 pares
    -- de módulo se repiten entre fundos — ver el comentario de core.lote). Agrupar o
    -- filtrar por `modulo` a solas mezcla módulos físicos distintos. La clave real,
    -- única, es `modulo_id` — úsala en cualquier análisis, y `modulo` solo para mostrar.
    cs.modulo_id,
    cam.codigo                              AS campania,
    mo.codigo                               AS modulo,
    fu.codigo                               AS fundo,
    em.nombre                               AS empresa,
    cs.anio_semana,
    sem.fecha_inicio                        AS semana_desde,
    sem.fecha_fin                           AS semana_hasta,

    -- ── Objetivo ──
    cs.kg,
    ma.area_ha,
    round(cs.kg / nullif(ma.area_ha, 0), 4) AS kg_ha,
    ma.n_plantas,
    round(cs.kg / nullif(ma.n_plantas, 0), 6) AS kg_planta,

    -- ── Tiempo agronómico: varía por módulo ──
    pm.poda_ref,
    sem.fecha_fin - pm.poda_ref             AS edad_dias,
    pm.poda_dispersion_dias,

    -- ── Clima de la semana: IDÉNTICO para todos los módulos de esa semana ──
    cl.temp_media,
    cl.temp_max,
    cl.temp_min,
    cl.gdd                                  AS gdd_semana,
    cl.eto_mm                               AS eto_semana_mm,
    cl.lluvia_mm                            AS lluvia_semana_mm,
    cl.humedad_media,

    -- ── Tiempo térmico acumulado desde la poda: SÍ varía por módulo ──
    -- Misma serie climática global, pero integrada desde la poda de cada módulo. Es lo
    -- que convierte una estación única en una variable que discrimina entre módulos.
    acc.gdd_acum_poda,
    acc.eto_acum_poda_mm,
    acc.lluvia_acum_poda_mm,

    -- ── Contexto de calidad del dato ──
    cs.registros_cosecha,
    cs.lotes_cosechados,
    ma.lotes                                AS lotes_modulo,
    cs.pana_max,
    cs.peso_baya_medio,
    cl.dias_con_clima,
    cl.dias_incompletos,
    sem.dias                                AS dias_en_semana,

    -- ── Riego: fuente externa a Access, cargada 2026-08-06 (4 Excel de Riego/
    -- Operaciones). Cubre solo Aqu Anqa 1-4 y M11 — NULL en los demás módulos, no 0:
    -- 0 significaría "se midió y no se regó", que no es lo que pasó ahí.
    ri.agua_m3                               AS riego_m3,
    ri.lamina_mm                             AS riego_mm,
    ri.dias_con_registro                     AS riego_dias_con_registro,
    coalesce(ri.estimado, false)             AS riego_estimado

FROM cosecha_semana cs
JOIN core.modulo mo     ON mo.modulo_id = cs.modulo_id
JOIN core.fundo fu      ON fu.fundo_id = mo.fundo_id
JOIN core.empresa em    ON em.empresa_id = fu.empresa_id
JOIN core.campania cam  ON cam.campania_id = cs.campania_id
JOIN semana sem         ON sem.anio_semana = cs.anio_semana
LEFT JOIN modulo_area ma ON ma.modulo_id = cs.modulo_id
LEFT JOIN clima_semana cl ON cl.anio_semana = cs.anio_semana
LEFT JOIN core.riego_semanal ri
       ON ri.modulo_id = cs.modulo_id AND ri.anio_semana = cs.anio_semana
LEFT JOIN reporting.v_poda_modulo pm
       ON pm.modulo_id = cs.modulo_id AND pm.campania_id = cs.campania_id
LEFT JOIN LATERAL (
    SELECT round(sum(cd.gdd), 3)       AS gdd_acum_poda,
           round(sum(cd.eto_mm), 3)    AS eto_acum_poda_mm,
           round(sum(cd.lluvia_mm), 3) AS lluvia_acum_poda_mm
    FROM reporting.v_clima_diario cd
    WHERE pm.poda_ref IS NOT NULL
      AND cd.fecha >= pm.poda_ref
      AND cd.fecha <= sem.fecha_fin
) acc ON true;

COMMENT ON VIEW reporting.v_analitica_modulo_semana IS
    'Panel módulo × campaña × semana para analizar qué variables explican el kg/ha. '
    'Semana por año ISO (core.calendario.anio_semana), sin lotes ficticios L000 y sin '
    'campaña fija. Las columnas *_semana del clima son iguales para todos los módulos de '
    'la misma semana y solo explican variación temporal; las *_acum_poda acumulan desde '
    'la poda de cada módulo y son las únicas del clima que discriminan entre módulos. '
    'riego_mm y riego_m3 vienen de core.riego_semanal (fuente externa a Access): NULL en '
    'los módulos y semanas sin ese registro, no 0. riego_estimado avisa cuándo la '
    'semana incluye el reparto M10A/M10B (D-7). ADVERTENCIA: `modulo` (M01, M02...) no '
    'es único globalmente — hay un M01 en Aqu Anqa 1 y otro M01 distinto en Aqu Anqa 2. '
    'Agrupar o entrenar un modelo por `modulo` a solas mezcla módulos físicos distintos; '
    'la clave real es `modulo_id`.';
