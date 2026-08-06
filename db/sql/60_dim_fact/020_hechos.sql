-- ============================================================================
-- 60_dim_fact · 020 · Hechos
--
-- Vistas sobre `core`, con la clave de cada dimensión y sin duplicar datos. Ningún hecho
-- lleva atributos de dimensión que deban sumarse: el área y el número de plantas viven en
-- dim.lote y se toman de ahí una sola vez. Sumarlos desde el hecho es el error de la medida
-- KG/HA del informe actual (hallazgo B-4).
-- ============================================================================

CREATE OR REPLACE VIEW fact.cosecha AS
SELECT c.cosecha_id,
       c.lote_id,
       c.fecha,
       c.campania_id,
       c.variedad_id,
       c.kg,
       c.pana,
       c.peso_baya,
       c.semana,
       -- Frutos estimados: convierte la medida comercial (kilos) a la agronómica (frutos),
       -- que es lo que permite comparar cosecha con los conteos de estados. El peso de baya
       -- viene en gramos.
       CASE WHEN c.peso_baya > 0 THEN c.kg / c.peso_baya * 1000 END AS frutos_estimados,
       c.en_h00,
       c.en_h01,
       c.kg_h01,
       c.registros_h00
FROM core.cosecha c;

COMMENT ON VIEW fact.cosecha IS
    'Kilos cosechados por lote y fecha. `kg` es la referencia (H00); `kg_h01` permite auditar '
    'la diferencia con H01 sin mantener dos hechos (H-07).';

-- ── Ramas: dos granos, dos hechos ───────────────────────────────────────────

CREATE OR REPLACE VIEW fact.evaluacion_ramas AS
SELECT er.evaluacion_ramas_id,
       er.lote_id,
       er.fecha,
       er.evaluador_id,
       er.cortina,
       er.hilera,
       er.planta,
       er.ramas_menor5,
       er.ramas_mayor5,
       coalesce(er.ramas_menor5, 0) + coalesce(er.ramas_mayor5, 0) AS ramas_declaradas,
       (SELECT count(*) FROM core.rama_medicion m
         WHERE m.evaluacion_ramas_id = er.evaluacion_ramas_id) AS ramas_medidas,
       (SELECT avg(m.diametro) FROM core.rama_medicion m
         WHERE m.evaluacion_ramas_id = er.evaluacion_ramas_id) AS diametro_medio
FROM core.evaluacion_ramas er;

COMMENT ON VIEW fact.evaluacion_ramas IS
    'Grano PLANTA: 5.384 filas. `ramas_declaradas` es lo que declaró el evaluador (110.095 en '
    'total) y `ramas_medidas` cuántas se midieron de verdad (71.095): no coinciden porque se '
    'mide una submuestra. Para "total de ramas" usar una de estas dos, nunca la suma de '
    'nro_rama, que es un índice (N-1).';

CREATE OR REPLACE VIEW fact.rama_medicion AS
SELECT m.rama_medicion_id,
       er.lote_id,
       er.fecha,
       er.evaluador_id,
       er.cortina,
       er.hilera,
       er.planta,
       m.nro_rama,
       m.diametro,
       m.sospechoso
FROM core.rama_medicion m
JOIN core.evaluacion_ramas er USING (evaluacion_ramas_id);

COMMENT ON VIEW fact.rama_medicion IS
    'Grano RAMA: 71.095 filas, una por rama medida. Es el hecho correcto para el diámetro '
    'medio (10,8869 mm). `sospechoso` marca los diámetros físicamente imposibles del origen, '
    'que se conservan porque las cifras de control los incluyen (N-13).';

-- ── Resto de evaluaciones ───────────────────────────────────────────────────

CREATE OR REPLACE VIEW fact.flores AS
SELECT f.flores_id, f.lote_id, f.fecha, f.evaluador_id,
       f.cortina, f.hilera, f.planta,
       f.n_flores, f.cuajo, f.yemas_abiertas, f.yemas_por_abrir,
       coalesce(f.yemas_abiertas, 0) + coalesce(f.yemas_por_abrir, 0) AS yemas_total,
       -- Tasa de cuajo: el principal predictor de producción. Solo tiene sentido donde el
       -- cuajo se evaluó, que es el 12,3% de las filas.
       CASE WHEN f.n_flores > 0 AND f.cuajo IS NOT NULL
            THEN f.cuajo::numeric / f.n_flores END AS tasa_cuajo,
       f.hora
FROM core.flores f;

CREATE OR REPLACE VIEW fact.estados AS
SELECT e.estados_id, e.lote_id, e.fecha, e.evaluador_id,
       e.cortina, e.hilera, e.planta,
       e.e1, e.e2, e.e3, e.e4, e.e5, e.total,
       -- Proporciones de madurez. Se normaliza porque los evaluadores no muestrean el mismo
       -- número de plantas por lote: en conteo absoluto un lote con 40 plantas evaluadas
       -- pesaría cuatro veces más que uno con 10 sin que eso signifique nada agronómico.
       CASE WHEN e.total > 0 THEN e.e1::numeric / e.total END AS p_e1,
       CASE WHEN e.total > 0 THEN e.e2::numeric / e.total END AS p_e2,
       CASE WHEN e.total > 0 THEN e.e3::numeric / e.total END AS p_e3,
       CASE WHEN e.total > 0 THEN e.e4::numeric / e.total END AS p_e4,
       CASE WHEN e.total > 0 THEN e.e5::numeric / e.total END AS p_e5,
       e.item
FROM core.estados e;

COMMENT ON VIEW fact.estados IS
    'Distribución de frutos por estado de madurez, con las proporciones ya calculadas. Si p_e5 '
    'sube, la cosecha está cerca; si domina p_e1, faltan semanas.';

CREATE OR REPLACE VIEW fact.brotes AS
SELECT b.brotes_id, b.lote_id, b.fecha, b.evaluador_id,
       b.piso, b.cortina, b.hilera, b.planta, b.brotes, b.hora
FROM core.brotes b;

CREATE OR REPLACE VIEW fact.baya_medicion AS
SELECT bm.baya_medicion_id, bm.lote_id, bm.fecha,
       bm.cortina, bm.hilera, bm.nro_muestra, bm.diametro, bm.sospechoso
FROM core.baya_medicion bm;

COMMENT ON VIEW fact.baya_medicion IS
    'Diámetro de baya, una fila por baya medida. Es el eslabón que conectaría la evaluación de '
    'campo con el calibre de packing y permitiría comprometer volumen por calibre semanas '
    'antes de cosechar — hoy ningún tablero los cruza.';

-- ── Clima, packing y forecast ───────────────────────────────────────────────

CREATE OR REPLACE VIEW fact.clima AS
SELECT c.fecha_hora,
       c.fecha_hora::date AS fecha,
       c.temp, c.temp_alta, c.temp_baja,
       c.temp_alta - c.temp_baja AS amplitud_termica,
       c.humedad, c.punto_rocio, c.barometro,
       c.vel_viento, c.direc_viento,
       c.lluvia, c.tasa_lluvia,
       c.rad_sol, c.ener_solar,
       c.et_mm, c.dg_calentamiento, c.dg_enfriamiento,
       c.thw_index
FROM core.clima c;

COMMENT ON VIEW fact.clima IS
    'Clima por instante, ya deduplicado (H-08). `amplitud_termica` es un factor determinante '
    'en arándano: un rango amplio favorece la acumulación de azúcares y la firmeza del fruto.';

CREATE OR REPLACE VIEW fact.packing AS
SELECT p.packing_id,
       p.modulo_id, p.empresa_id, p.variedad_id, p.calibre_id,
       p.fecha_cosecha, p.fecha_proceso, p.semana, p.anio,
       p.turno_packing, p.clase, p.mercado, p.mercado_valido,
       p.recuento, p.peso_kg, p.porcentaje,
       -- Peso unitario real de la baya, medido en planta de proceso. Es la calibración de las
       -- estimaciones de campo.
       CASE WHEN p.recuento > 0 THEN p.peso_kg / p.recuento * 1000 END AS peso_baya_g,
       p.nota_packing, p.acidez, p.defecto,
       p.hora_inicio, p.hora_fin,
       CASE WHEN p.hora_inicio IS NOT NULL AND p.hora_fin IS NOT NULL
            THEN p.hora_fin - p.hora_inicio END AS duracion
FROM core.packing p;

COMMENT ON VIEW fact.packing IS
    'Resultado de packing. Referencia módulo y no lote (N-2). `duracion` solo existe en el '
    '52% de las filas: casi la mitad no tiene hora de proceso en el origen.';

CREATE OR REPLACE VIEW fact.forecast_campania AS
SELECT f.forecast_campania_id, f.version_id, f.modulo_id, f.empresa_id, f.turno_id,
       f.campania_id, f.anio, f.semana,
       f.kg_exp, f.kg_des, f.kg_con,
       coalesce(f.kg_exp, 0) + coalesce(f.kg_des, 0) + coalesce(f.kg_con, 0) AS kg_total,
       f.frutos_exp,
       f.c12, f.c14, f.c16, f.c18, f.c19, f.c20, f.c22, f.c24, f.c26
FROM core.forecast_campania f;

COMMENT ON VIEW fact.forecast_campania IS
    'Proyección por campaña y módulo. FILTRAR SIEMPRE por versión: sin filtro se suman 15 '
    'escenarios del mismo periodo. `kg_exp` es lo que R0801_ResCampaña entiende por "los kilos '
    'del forecast" y el supuesto en uso para la decisión D-1.';

DROP VIEW IF EXISTS fact.forecast_semanal CASCADE;

CREATE VIEW fact.forecast_semanal AS
SELECT f.forecast_semanal_id, f.version_id, f.lote_id, f.campania_id,
       f.pasada, f.fecha_cos, f.fecha_cos_ant, f.semana, f.dr,
       f.frutos_por_planta, f.peso_baya, f.frutos_total, f.rendimiento, f.kg
FROM core.forecast_semanal f;

COMMENT ON VIEW fact.forecast_semanal IS
    'dr (días de reingreso) se añadió al construir R0901_Forecas_SemAc/R0903_Forecast_FrtsTotal '
    '(bloque 4 de reporting): existía en core.forecast_semanal pero se había quedado fuera de '
    'esta vista.';

-- ── Personal ────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW fact.tareo AS
SELECT t.tareo_id, t.evaluador_id, t.documento, t.fecha, t.horas, t.labor, t.lote_id
FROM core.tareo t;

COMMENT ON VIEW fact.tareo IS
    'Horas-hombre por persona y fecha. Es lo que el informe SEGUIMIENTO DE PERSONAL necesita '
    'para sus medidas de productividad y que hoy toma de un Excel en un equipo personal (B-1). '
    'Vacío mientras no se cargue Query Tareo 2026.xlsx.';
