-- ============================================================================
-- 70_reporting · 020 · Compatibilidad · informe SEGUIMIENTO DE CAMPAÑA
--
-- Las cuatro consultas de Access que ese informe consume, con su nombre y sus columnas
-- originales, para que el reapuntado no obligue a rehacer el modelo semántico.
--
-- Dos cosas cambian respecto a Access, y son correcciones, no regresiones:
--
--   · Las columnas que venían del join roto de H-01 (Turno, KeyMap, NPlantas, Area) ahora
--     traen valor. En Access el 100% de las filas de 0101_Diametros salía con Turno NULL.
--   · Los conteos bajan donde había duplicados por recarga (H-03) y filas de subtotal (H-06).
--
-- Se añaden columnas nuevas al final (empresa, fundo físico, clave de negocio) para que el
-- informe pueda dejar de fabricar dimensiones con DAX (B-2). Añadir columnas no rompe nada:
-- Power BI ignora las que no usa.
-- ============================================================================

-- ── H0101_ResumenHistoricos · cosecha por lote y paña ───────────────────────
CREATE OR REPLACE VIEW reporting."H0101_ResumenHistoricos" AS
SELECT c.empresa            AS "Fundo",          -- en Access, Fundo traía la empresa
       c.campania           AS "Campaña",
       c.modulo             AS "Modulo",
       c.turno              AS "Turno",
       c.lote               AS "Lote",
       c.area_ha            AS "Area",
       c.n_plantas          AS "NPlantas",
       c.kg                 AS "KG",
       c.pana               AS "Paña",
       c.frutos_estimados   AS "FrutosT",
       -- FecPon era Fecha * KG, un valor intermedio que solo significaba algo dividido entre
       -- SUM(KG). Se conserva por compatibilidad, pero v_rendimiento_lote ya expone la fecha
       -- media ponderada directamente.
       extract(epoch FROM c.fecha) * c.kg AS "FecPon",
       c.fecha_poda         AS "FInicio",
       c.fecha              AS "Fecha",
       c.semana             AS "Semana",
       c.anio               AS "anio",
       c.mod_turno          AS "ModTur",
       c.tipo_fibra         AS "TipoFibra",
       c.empresa            AS "FundoPPto",
       c.fundo_operativo    AS "Fundo_pptom5",
       -- Nuevas, para sustituir las dimensiones calculadas en DAX (B-2, B-3):
       c.fundo              AS "FUNDO_FISICO",
       c.fundo_operativo    AS "FUNDO_CAMPO",
       c.clave_negocio      AS "LOTE_CLAVE",
       c.dias_desde_poda    AS "DiasDesdePoda"
FROM reporting.v_cosecha c;

COMMENT ON VIEW reporting."H0101_ResumenHistoricos" IS
    'Compatibilidad con la consulta homónima de Access. Cambios esperados: ya no incluye las 2 '
    'filas de subtotal de Excel de H-06 (995.333,20 kg sin lote ni fecha) y el KG de referencia '
    'pasa a ser el de H00, que conserva los registros completos en C2023 y C2024 (H-07). '
    'FUNDO_FISICO distingue Aqu Anqa 1..6, que es lo que el mapeo DAX del informe no hacía.';

-- ── 0201_Flores · conteo de flores a nivel de planta ────────────────────────
-- El filtro fijo `WHERE M_Poda.Campaña = "C2026"` NO se reproduce: dejaba la consulta
-- obsoleta en cuanto empieza otra campaña (D-6). Power BI filtra por Campaña.
CREATE OR REPLACE VIEW reporting."0201_Flores" AS
SELECT NULL::text          AS "Item",
       f.dni               AS "Evaluador",
       f.empresa           AS "Fundo",
       f.fundo_operativo   AS "Fundo_pptom5",
       f.modulo            AS "Modulo",
       f.turno             AS "Turno",
       f.lote              AS "Lote",
       f.cortina           AS "Cortina",
       f.hilera            AS "Hilera",
       f.planta            AS "Planta",
       f.n_flores          AS "nFlores",
       f.yemas_abiertas    AS "YA",
       f.yemas_por_abrir   AS "YP",
       f.yemas_total       AS "yemas",
       f.fecha             AS "Fecha",
       f.semana            AS "Sem",
       f.anio              AS "Año",
       f.key_map           AS "KeyMap",
       f.fecha_poda        AS "FInicio",
       f.campania          AS "Campaña",
       f.fundo             AS "FUNDO_FISICO",
       f.fundo_operativo   AS "FUNDO_CAMPO",
       f.clave_negocio     AS "LOTE_CLAVE",
       f.cuajo             AS "Cuajo",
       f.tasa_cuajo        AS "TasaCuajo",
       f.dias_desde_poda   AS "DiasDesdePoda",
       f.evaluador         AS "EvaluadorNombre"
FROM reporting.v_flores f;

COMMENT ON VIEW reporting."0201_Flores" IS
    'Compatibilidad. A diferencia de Access NO filtra por C2026: ese filtro estaba escrito en '
    'el SQL y habría dejado el informe congelado en esa campaña (D-6). Ahora expone Campaña '
    'para que Power BI filtre. Añade Cuajo y TasaCuajo, que la consulta original omitía aunque '
    'el cuajo es el principal predictor de producción.';

-- ── 0301_ConteoEstados · estados de madurez con contexto ────────────────────
CREATE OR REPLACE VIEW reporting."0301_ConteoEstados" AS
SELECT e.item              AS "Item",
       e.dni               AS "Evaluador",
       e.empresa           AS "Fundo",
       e.modulo            AS "Modulo",
       e.turno             AS "Turno",
       e.lote              AS "Lote",
       e.area_ha           AS "Area",
       e.n_plantas         AS "NPlantas",
       e.cortina           AS "Cortina",
       e.hilera            AS "Hilera",
       e.planta            AS "Planta",
       e.e1 AS "E1", e.e2 AS "E2", e.e3 AS "E3", e.e4 AS "E4", e.e5 AS "E5",
       e.total             AS "Total",
       e.fecha             AS "Fecha",
       e.cod_planta        AS "codPlt",
       -- Key1 era Right(Fundo,2) & Modulo & Turno: un apaño para tener una clave compuesta en
       -- ausencia de claves reales. Se conserva por compatibilidad; lo correcto es LOTE_CLAVE.
       right(e.empresa, 2) || e.modulo || e.turno AS "Key1",
       e.key_map           AS "KeyMap",
       e.fundo_operativo   AS "Fundo_pptom5",
       e.anio              AS "Año",
       e.semana            AS "Sem",
       e.sem_ev_conteo     AS "SEvConteo",
       e.campania          AS "Campaña",
       e.fundo             AS "FUNDO_FISICO",
       e.fundo_operativo   AS "FUNDO_CAMPO",
       e.clave_negocio     AS "LOTE_CLAVE",
       e.p_e1 AS "pE1", e.p_e2 AS "pE2", e.p_e3 AS "pE3", e.p_e4 AS "pE4", e.p_e5 AS "pE5"
FROM reporting.v_estados e;

COMMENT ON VIEW reporting."0301_ConteoEstados" IS
    'Compatibilidad. Total es ahora una columna generada, así que la diferencia de 2.430 frutos '
    'entre Total y la suma de E1..E5 desaparece. Añade las proporciones pE1..pE5, que en Access '
    'requerían una consulta aparte (0302_ConteoAjustado).';

-- ── 0305_Brotes_Ramas · brotes y ramas gruesas en una serie ─────────────────
CREATE OR REPLACE VIEW reporting."0305_Brotes_Ramas" AS
SELECT b.piso              AS "Piso",
       ev.dni              AS "Evaluador",
       b.fecha             AS "Fecha",
       l.empresa           AS "Empresa",
       l.empresa           AS "Fundo",
       l.modulo            AS "Modulo",
       l.lote              AS "Lote",
       b.cortina           AS "Cortina",
       b.hilera            AS "Hilera",
       b.planta            AS "Planta",
       b.brotes            AS "Brotes",
       b.brotes            AS "valor",
       l.turno             AS "Turno",
       l.fundo             AS "FUNDO_FISICO",
       l.fundo_operativo   AS "FUNDO_CAMPO",
       l.clave_negocio     AS "LOTE_CLAVE"
FROM fact.brotes b
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.evaluador ev ON ev.evaluador_id = b.evaluador_id
UNION ALL
SELECT 'Ramas',
       ev.dni,
       r.fecha,
       l.empresa, l.empresa, l.modulo, l.lote,
       r.cortina, r.hilera, r.planta,
       r.ramas_mayor5,
       r.ramas_mayor5,
       l.turno, l.fundo, l.fundo_operativo, l.clave_negocio
FROM fact.evaluacion_ramas r
JOIN dim.lote l USING (lote_id)
LEFT JOIN dim.evaluador ev ON ev.evaluador_id = r.evaluador_id;

COMMENT ON VIEW reporting."0305_Brotes_Ramas" IS
    'Compatibilidad: brotes y ramas gruesas apilados, con el literal "Ramas" en Piso para '
    'distinguir el origen, igual que en Access. Ahora trae Turno con valor — en Access venía '
    'de 0101_Diametros y salía NULL en el 100% de las filas por el join de H-01. Las filas de '
    'ramas bajan porque el grano correcto es la planta, no la rama (N-1).';
