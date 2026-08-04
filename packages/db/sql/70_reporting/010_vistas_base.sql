-- ============================================================================
-- 70_reporting · 010 · Vistas base
--
-- Lo que Power BI consume de verdad, con las dimensiones ya unidas. Estas vistas reemplazan
-- las transformaciones que hoy viven en Power Query y en columnas calculadas DAX (ADR-0004):
-- toda la lógica de negocio está aquí, y el modelo semántico solo mide.
--
-- Los nombres son en snake_case ASCII. Las 40 consultas de Access conservan su grafía
-- original en las vistas de compatibilidad de 020 a 040.
-- ============================================================================

-- ── Evaluación de flores, con su contexto ───────────────────────────────────
CREATE OR REPLACE VIEW reporting.v_flores AS
SELECT f.flores_id,
       l.empresa, l.fundo, l.fundo_operativo, l.modulo, l.turno, l.lote,
       l.clave_negocio, l.area_ha, l.n_plantas, l.key_map,
       f.fecha, t.anio, t.semana, t.sem_ev_conteo, t.mes_abrev, t.trimestre,
       ev.dni, ev.nombre AS evaluador, ev.nombre_corto AS evaluador_corto,
       f.cortina, f.hilera, f.planta,
       f.n_flores, f.cuajo, f.yemas_abiertas, f.yemas_por_abrir, f.yemas_total,
       f.tasa_cuajo,
       p.fecha_inicio AS fecha_poda,
       f.fecha - p.fecha_inicio AS dias_desde_poda,
       cp.campania
FROM fact.flores f
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = f.fecha
LEFT JOIN dim.evaluador ev ON ev.evaluador_id = f.evaluador_id
LEFT JOIN core.poda p ON p.poda_id = (
    SELECT p2.poda_id FROM core.poda p2
     WHERE p2.lote_id = f.lote_id AND p2.fecha_inicio <= f.fecha
     ORDER BY p2.fecha_inicio DESC LIMIT 1)
LEFT JOIN dim.campania cp ON cp.campania_id = p.campania_id;

COMMENT ON VIEW reporting.v_flores IS
    'Conteo de flores con su ubicación, tiempo, evaluador y días desde poda. `dias_desde_poda` '
    'es la escala agronómicamente correcta: dos lotes podados con un mes de diferencia están en '
    'estados distintos la misma fecha. La campaña viene de la poda del lote, no del calendario '
    '(N-11).';

-- ── Estados de madurez, con su contexto ─────────────────────────────────────
CREATE OR REPLACE VIEW reporting.v_estados AS
SELECT e.estados_id,
       l.empresa, l.fundo, l.fundo_operativo, l.modulo, l.turno, l.lote,
       l.clave_negocio, l.area_ha, l.n_plantas, l.key_map,
       e.fecha, t.anio, t.semana, t.sem_ev_conteo, t.mes_abrev, t.trimestre,
       ev.dni, ev.nombre AS evaluador,
       e.cortina, e.hilera, e.planta,
       'C' || e.cortina || 'H' || e.hilera || 'P' || e.planta AS cod_planta,
       e.e1, e.e2, e.e3, e.e4, e.e5, e.total,
       e.p_e1, e.p_e2, e.p_e3, e.p_e4, e.p_e5,
       e.item,
       cp.campania
FROM fact.estados e
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = e.fecha
LEFT JOIN dim.evaluador ev ON ev.evaluador_id = e.evaluador_id
LEFT JOIN core.poda p ON p.poda_id = (
    SELECT p2.poda_id FROM core.poda p2
     WHERE p2.lote_id = e.lote_id AND p2.fecha_inicio <= e.fecha
     ORDER BY p2.fecha_inicio DESC LIMIT 1)
LEFT JOIN dim.campania cp ON cp.campania_id = p.campania_id;

-- ── Ramas, en sus dos granos ────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting.v_ramas_planta AS
SELECT r.evaluacion_ramas_id,
       l.empresa, l.fundo, l.modulo, l.turno, l.lote, l.clave_negocio, l.key_map,
       r.fecha, t.anio, t.semana,
       ev.nombre AS evaluador,
       r.cortina, r.hilera, r.planta,
       r.ramas_menor5, r.ramas_mayor5, r.ramas_declaradas,
       r.ramas_medidas, r.diametro_medio
FROM fact.evaluacion_ramas r
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = r.fecha
LEFT JOIN dim.evaluador ev ON ev.evaluador_id = r.evaluador_id;

CREATE OR REPLACE VIEW reporting.v_ramas AS
SELECT m.rama_medicion_id,
       l.empresa, l.fundo, l.modulo, l.turno, l.lote, l.clave_negocio, l.key_map,
       m.fecha, t.anio, t.semana,
       ev.nombre AS evaluador,
       m.cortina, m.hilera, m.planta, m.nro_rama, m.diametro, m.sospechoso
FROM fact.rama_medicion m
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = m.fecha
LEFT JOIN dim.evaluador ev ON ev.evaluador_id = m.evaluador_id;

-- ── Cosecha ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting.v_cosecha AS
SELECT c.cosecha_id,
       l.empresa, l.fundo, l.fundo_operativo, l.modulo, l.turno, l.lote,
       l.clave_negocio, l.mod_turno, l.area_ha, l.n_plantas, l.tipo_fibra, l.key_map,
       cp.campania,
       c.fecha, t.anio, t.semana, t.mes_abrev, t.trimestre, t.anio_mes,
       v.variedad,
       c.kg, c.pana, c.peso_baya, c.frutos_estimados,
       c.en_h00, c.en_h01, c.kg_h01,
       p.fecha_inicio AS fecha_poda,
       c.fecha - p.fecha_inicio AS dias_desde_poda
FROM fact.cosecha c
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.campania cp USING (campania_id)
LEFT JOIN dim.tiempo t ON t.fecha = c.fecha
LEFT JOIN dim.variedad v ON v.variedad_id = c.variedad_id
LEFT JOIN core.poda p ON p.lote_id = c.lote_id AND p.campania_id = c.campania_id;

COMMENT ON VIEW reporting.v_cosecha IS
    'Cosecha con toda su jerarquía. IMPORTANTE: `area_ha` viene de la dimensión de lote y está '
    'repetida en cada fila; el rendimiento por hectárea se calcula con el área tomada UNA vez '
    'por lote, no sumándola desde aquí. Ese es el defecto de la medida KG/HA actual (B-4).';

-- ── Rendimiento por hectárea, ya bien calculado ─────────────────────────────
CREATE OR REPLACE VIEW reporting.v_rendimiento_lote AS
SELECT l.lote_id, l.empresa, l.fundo, l.modulo, l.turno, l.lote, l.clave_negocio,
       cp.campania,
       l.area_ha,
       l.n_plantas,
       sum(c.kg)                                    AS kg,
       count(*)                                     AS registros,
       max(c.pana)                                  AS panas,
       CASE WHEN l.area_ha > 0 THEN sum(c.kg) / l.area_ha END     AS kg_por_ha,
       CASE WHEN l.n_plantas > 0 THEN sum(c.kg) / l.n_plantas END AS kg_por_planta,
       -- Fecha media ponderada por kilos: responde cuándo salió el grueso del volumen, que es
       -- lo que sirve para planificar cuadrillas y packing.
       (sum(extract(epoch FROM c.fecha) * c.kg) / nullif(sum(c.kg), 0))::bigint
           AS epoch_medio_ponderado,
       to_timestamp(sum(extract(epoch FROM c.fecha) * c.kg) / nullif(sum(c.kg), 0))::date
           AS fecha_media_ponderada,
       min(c.fecha) AS primera_cosecha,
       max(c.fecha) AS ultima_cosecha
FROM fact.cosecha c
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.campania cp USING (campania_id)
GROUP BY l.lote_id, l.empresa, l.fundo, l.modulo, l.turno, l.lote, l.clave_negocio,
         cp.campania, l.area_ha, l.n_plantas;

COMMENT ON VIEW reporting.v_rendimiento_lote IS
    'Rendimiento por lote y campaña con el área tomada UNA vez. Corrige B-4: la medida actual '
    'divide entre SUM(Area), que multiplica la superficie por el número de pañas y subestima '
    'el rendimiento. `fecha_media_ponderada` sustituye al artificio FecPon = Fecha * KG, que '
    'solo tenía sentido dividido entre SUM(KG).';

-- ── Cadena fenológica completa, en formato largo ────────────────────────────
CREATE OR REPLACE VIEW reporting.v_fenologia AS
SELECT l.empresa, l.fundo, l.modulo, l.turno, l.lote, l.clave_negocio,
       d.fecha, t.anio, t.semana, t.sem_ev_conteo,
       d.etapa, d.orden_etapa, d.valor, d.n
FROM (
    -- Una sola pasada por cada hecho, en lugar del UNION ALL repetido que usaban seis
    -- consultas de Access (H-11).
    SELECT lote_id, fecha, 'Brotes' AS etapa, 0 AS orden_etapa,
           avg(brotes)::numeric AS valor, count(*) AS n
    FROM fact.brotes GROUP BY lote_id, fecha
    UNION ALL
    SELECT lote_id, fecha, 'Ramas', 1, avg(ramas_declaradas)::numeric, count(*)
    FROM fact.evaluacion_ramas GROUP BY lote_id, fecha
    UNION ALL
    SELECT lote_id, fecha, 'Flor', 2, avg(n_flores)::numeric, count(*)
    FROM fact.flores GROUP BY lote_id, fecha
    UNION ALL
    SELECT lote_id, fecha, 'Est' || e.i, 2 + e.i,
           avg(CASE e.i WHEN 1 THEN f.e1 WHEN 2 THEN f.e2 WHEN 3 THEN f.e3
                        WHEN 4 THEN f.e4 ELSE f.e5 END)::numeric, count(*)
    FROM fact.estados f
    CROSS JOIN LATERAL (SELECT generate_series(1, 5) AS i) e
    GROUP BY lote_id, fecha, e.i
    UNION ALL
    SELECT lote_id, fecha, 'Baya', 8, avg(diametro), count(*)
    FROM fact.baya_medicion GROUP BY lote_id, fecha
    UNION ALL
    SELECT lote_id, fecha, 'Cosecha', 9, sum(kg), count(*)
    FROM fact.cosecha GROUP BY lote_id, fecha
) d
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.tiempo t ON t.fecha = d.fecha;

COMMENT ON VIEW reporting.v_fenologia IS
    'La cadena fenológica entera en una serie: brotes → ramas → flor → Est1..Est5 → baya → '
    'cosecha, ordenada por `orden_etapa`. Cada eslabón predice el siguiente, y esta vista es '
    'la que permite recorrerla completa — algo que en Access no se podía porque E05 estaba '
    'desconectada y E01/E04 no enlazaban con el maestro.';

-- ── Productividad de evaluadores ────────────────────────────────────────────
CREATE OR REPLACE VIEW reporting.v_productividad_evaluador AS
WITH jornada AS (
    SELECT evaluador_id, fecha, 'flores' AS tipo, count(*) AS registros,
           sum(n_flores)::numeric AS unidades, count(DISTINCT (lote_id, cortina, hilera, planta)) AS plantas,
           stddev_pop(n_flores)   AS desv, avg(n_flores) AS media
    FROM fact.flores WHERE evaluador_id IS NOT NULL GROUP BY evaluador_id, fecha
    UNION ALL
    SELECT evaluador_id, fecha, 'estados', count(*), sum(total)::numeric,
           count(DISTINCT (lote_id, cortina, hilera, planta)), stddev_pop(total), avg(total)
    FROM fact.estados WHERE evaluador_id IS NOT NULL GROUP BY evaluador_id, fecha
    UNION ALL
    SELECT evaluador_id, fecha, 'ramas', count(*), sum(ramas_declaradas)::numeric,
           count(DISTINCT (lote_id, cortina, hilera, planta)), stddev_pop(ramas_declaradas),
           avg(ramas_declaradas)
    FROM fact.evaluacion_ramas WHERE evaluador_id IS NOT NULL GROUP BY evaluador_id, fecha
)
SELECT ev.evaluador_id, ev.dni, ev.nombre AS evaluador, ev.nombre_corto, ev.zona,
       ev.en_maestro,
       j.fecha, t.anio, t.semana, j.tipo,
       j.registros, j.unidades, j.plantas,
       j.media, j.desv,
       CASE WHEN j.media > 0 THEN j.desv / j.media * 100 END AS cv,
       ta.horas,
       CASE WHEN ta.horas > 0 THEN j.unidades / ta.horas END AS unidades_por_hora,
       CASE WHEN ta.horas > 0 THEN j.plantas / ta.horas END AS plantas_por_hora
FROM jornada j
JOIN dim.evaluador ev USING (evaluador_id)
LEFT JOIN dim.tiempo t ON t.fecha = j.fecha
LEFT JOIN (SELECT evaluador_id, fecha, sum(horas) AS horas FROM fact.tareo
            WHERE evaluador_id IS NOT NULL GROUP BY 1, 2) ta
       ON ta.evaluador_id = j.evaluador_id AND ta.fecha = j.fecha;

COMMENT ON VIEW reporting.v_productividad_evaluador IS
    'Productividad y consistencia por evaluador y jornada. Baja a SQL las medidas que hoy vive '
    'solo dentro del informe SEGUIMIENTO DE PERSONAL (B-5, B-6): CV Evaluador, Flores por '
    'Hora, Plantas por Hora. Las columnas de horas requieren el tareo cargado.';
