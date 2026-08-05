-- ============================================================================
-- 60_dim_fact · 010 · Dimensiones
--
-- Son VISTAS sobre `core`, no copias: el modelo dimensional no debe tener su propia versión
-- de la verdad. Solo se materializa lo que cuesta calcular (ver 70_reporting).
--
-- Estas dimensiones existen para sustituir a las que ambos informes de Power BI fabrican con
-- SUMMARIZECOLUMNS sobre las tablas de hechos (hallazgo B-2). La diferencia importa: la
-- dimensión `LOTE` de Power BI es una lista de códigos sin módulo, así que el L001 de M01 y
-- el L001 de M05 son la misma fila y filtrar por lote mezcla lotes físicos distintos.
-- ============================================================================

CREATE OR REPLACE VIEW dim.empresa AS
SELECT empresa_id, nombre AS empresa, activo, es_sentinel
FROM core.empresa;

COMMENT ON VIEW dim.empresa IS
    'La fila con es_sentinel=true ("Sin identificar") existe para que ninguna FK de una '
    'tabla de hechos quede NULL cuando la identidad no resuelve (ADR-0005). En Power BI: '
    'filtrar es_sentinel=false para el análisis normal, o dejarla visible para auditar '
    'cuánto volumen no se pudo identificar.';

CREATE OR REPLACE VIEW dim.fundo AS
SELECT f.fundo_id,
       f.codigo            AS fundo,
       f.alias_operativo   AS fundo_operativo,
       e.empresa_id,
       e.nombre            AS empresa,
       f.codigo || ' · ' || coalesce(f.alias_operativo, '') AS etiqueta,
       f.activo,
       f.es_sentinel
FROM core.fundo f
JOIN core.empresa e USING (empresa_id);

COMMENT ON VIEW dim.fundo IS
    'Los seis fundos físicos con su empresa. Sustituye a la columna calculada en DAX que '
    'asignaba fundo por módulo y que manda M01-M04 entero a Arena Azul y deja M17-M24 en '
    'blanco (hallazgo B-3). La fila es_sentinel=true es "Sin identificar" (ADR-0005).';

CREATE OR REPLACE VIEW dim.modulo AS
SELECT m.modulo_id,
       m.codigo      AS modulo,
       f.fundo_id,
       f.codigo      AS fundo,
       f.alias_operativo AS fundo_operativo,
       e.empresa_id,
       e.nombre      AS empresa,
       -- El código de módulo no es único: M01 a M04 están en dos fundos (N-4).
       m.codigo || ' (' || f.codigo || ')' AS etiqueta,
       m.es_sentinel
FROM core.modulo m
JOIN core.fundo f USING (fundo_id)
JOIN core.empresa e ON e.empresa_id = f.empresa_id;

COMMENT ON VIEW dim.modulo IS
    'La fila es_sentinel=true ("Sin identificar") es donde apuntan las 624 filas de '
    'forecast_campania cuyo módulo no resolvía contra el maestro vigente (ADR-0005, N-15).';

CREATE OR REPLACE VIEW dim.turno AS
SELECT turno_id, codigo AS turno, es_sentinel FROM core.turno;

CREATE OR REPLACE VIEW dim.lote AS
SELECT l.lote_id,
       l.codigo        AS lote,
       m.modulo_id,
       m.codigo        AS modulo,
       t.turno_id,
       t.codigo        AS turno,
       f.fundo_id,
       f.codigo        AS fundo,
       f.alias_operativo AS fundo_operativo,
       e.empresa_id,
       e.nombre        AS empresa,
       v.nombre        AS variedad,
       l.area_ha,
       l.n_plantas,
       l.fecha_siembra,
       l.maceta,
       l.tipo_fibra,
       l.key_map,
       l.es_ficticio,
       -- Clave de negocio legible. Es lo que hay que usar como identificador en Power BI:
       -- el código de lote a secas no identifica un lote (B-2).
       e.nombre || '/' || m.codigo || '/' || l.codigo AS clave_negocio,
       m.codigo || '-' || l.codigo AS etiqueta,
       m.codigo || t.codigo        AS mod_turno,
       l.es_sentinel
FROM core.lote l
JOIN core.modulo m USING (modulo_id)
JOIN core.fundo f  ON f.fundo_id = m.fundo_id
JOIN core.empresa e ON e.empresa_id = f.empresa_id
JOIN core.turno t  ON t.turno_id = l.turno_id
LEFT JOIN core.variedad v ON v.variedad_id = l.variedad_id;

COMMENT ON VIEW dim.lote IS
    'Los 879 lotes del maestro + 1 fila centinela "Sin identificar" (ADR-0005), con su '
    'jerarquía completa: empresa, fundo, módulo y turno. `clave_negocio` es el identificador '
    'correcto — (empresa, módulo, lote), ADR-0003. El área viene de aquí y NO debe sumarse '
    'desde un hecho: sumar core.cosecha.area repetiría la superficie una vez por paña y es '
    'el error de la medida KG/HA (hallazgo B-4).';

CREATE OR REPLACE VIEW dim.tiempo AS
SELECT c.fecha,
       c.anio,
       c.mes,
       c.dia,
       c.trimestre,
       'T' || c.trimestre     AS trimestre_etiqueta,
       c.semana,
       c.dia_semana,
       c.mes_abrev,
       c.anio_mes,
       c.anio_semana,
       c.sem_ev_conteo,
       c.mes_sem,
       c.campanias_activas,
       c.anio * 100 + c.mes   AS anio_mes_num
FROM core.calendario c;

COMMENT ON VIEW dim.tiempo IS
    'Dimensión de tiempo con grano de día. Reemplaza a M_Time y a la tabla BD_Calendario que '
    'ambos informes construyen en DAX: incluye el trimestre que a M_Time le faltaba (H-04 '
    'caso 5) y las columnas anio_semana y anio_mes que aportaba BD_Calendario. NO tiene '
    'campaña, porque las campañas se solapan y una fecha no la determina (N-11).';

CREATE OR REPLACE VIEW dim.semana_evaluacion AS
SELECT anio, sem_ev_conteo, fecha_inicio, fecha_fin, dias,
       anio || '-S' || lpad(sem_ev_conteo::text, 2, '0') AS etiqueta
FROM core.semana_evaluacion;

COMMENT ON VIEW dim.semana_evaluacion IS
    'Grano SEMANAL. Unir aquí y nunca contra dim.tiempo por sem_ev_conteo: eso es lo que '
    'multiplicó por 54 las filas de 01_Flores_C2025 (H-05).';

CREATE OR REPLACE VIEW dim.campania AS
SELECT campania_id, codigo AS campania, fecha_inicio, fecha_fin, origen_fechas,
       (fecha_fin - fecha_inicio) + 1 AS dias
FROM core.campania;

CREATE OR REPLACE VIEW dim.evaluador AS
SELECT e.evaluador_id,
       e.dni,
       coalesce(nullif(btrim(coalesce(e.nombres, '') || ' ' || coalesce(e.apellidos, '')), ''),
                'DNI ' || e.dni) AS nombre,
       split_part(coalesce(e.nombres, ''), ' ', 1) AS nombre_corto,
       e.codigo,
       e.zona,
       e.inicio_labores,
       e.activo,
       e.en_maestro
FROM core.evaluador e;

COMMENT ON VIEW dim.evaluador IS
    'Los evaluadores, enlazados por DNI (H-09). `en_maestro` = false marca a quienes capturan '
    'datos sin ficha en el maestro. Es la dimensión que permite medir la variabilidad entre '
    'evaluadores desde el modelo, en lugar de reconstruirla en cada informe (B-5).';

CREATE OR REPLACE VIEW dim.calibre AS
SELECT calibre_id, etiqueta AS calibre, mm, orden, es_descarte
FROM core.calibre;

COMMENT ON VIEW dim.calibre IS
    'Calibre comercial ORDENADO por `orden`: en el origen era texto y se ordenaba '
    'alfabéticamente, con 10 antes que 2 (H-10).';

CREATE OR REPLACE VIEW dim.variedad AS
SELECT variedad_id, nombre AS variedad, es_sentinel FROM core.variedad;

COMMENT ON VIEW dim.variedad IS
    'La fila es_sentinel=true ("Sin identificar") es donde apuntan las 4 filas de cosecha '
    'que solo existen en H01_ProdHistorica, que nunca tuvo columna de variedad (ADR-0005, '
    'N-15) — no es un fallo de resolución, el dato no existe en el origen.';

CREATE OR REPLACE VIEW dim.version_forecast AS
SELECT version_id, sistema, codigo AS version, semana_emision, iteracion, es_presupuesto
FROM core.version_forecast;

COMMENT ON VIEW dim.version_forecast IS
    'Escenarios de proyección. TODA medida sobre forecast debe filtrar una versión: sin filtro '
    'se suman escenarios distintos del mismo periodo, y de ahí salen los 648 M de kg de R08 '
    'frente a los ~32,45 M de cosecha real de las cinco campañas.';
