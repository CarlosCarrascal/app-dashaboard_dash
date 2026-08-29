-- ============================================================================
-- 20_core · 060 · Catálogo de dominios
--
-- PostgreSQL no tiene un concepto de "dominio" dentro de un esquema: la única
-- agrupación estructural real es el esquema mismo (core, raw, stg...). Esta vista
-- añade esa capa de lectura sin inventar tablas nuevas de metadatos: clasifica las
-- tablas de `core` por dominio de negocio y reutiliza lo que ya existe en el catálogo
-- del motor (pg_class, pg_description) — los mismos COMMENT ON TABLE escritos en
-- 010_ubicacion.sql .. 050_operacion.sql.
--
-- Si se añade una tabla a core y no se incluye aquí, cae en '(sin clasificar)' — la
-- vista avisa en vez de omitirla en silencio.
-- ============================================================================

-- DROP y no CREATE OR REPLACE: el motor no permite insertar una columna en medio de las
-- posiciones existentes de una vista, solo añadirlas al final o renombrarlas.
DROP VIEW IF EXISTS core.v_catalogo;

CREATE VIEW core.v_catalogo AS
SELECT
    -- MAESTRO      catálogo/referencia: pocas filas, cambia poco, no lo genera un evento
    --              de campo (empresa, fundo, lote, variedad, calibre, evaluador...).
    -- TIEMPO       dimensión de tiempo generada (calendario, semana_evaluacion) o el
    --              catálogo de campañas — no las captura nadie, se derivan.
    -- EVENTO       un registro por (lote, campaña): baja frecuencia, pero no es catálogo
    --              porque describe algo que ocurrió una vez, no una entidad estable.
    -- MOVIMIENTO   captura de campo u operación: crece con cada evaluación, cosecha,
    --              medición de clima o proyección. Es lo que en un modelo dimensional
    --              serían los hechos (fact.*).
    -- CONFIGURACIÓN parámetros de negocio (core.cfg_*), no describe una
    --              entidad del dominio agronómico.
    CASE c.relname
        WHEN 'm_empresa' THEN 'MAESTRO' WHEN 'm_fundo' THEN 'MAESTRO'
        WHEN 'm_fundo_alias' THEN 'MAESTRO' WHEN 'm_modulo' THEN 'MAESTRO'
        WHEN 'm_turno' THEN 'MAESTRO' WHEN 'm_lote' THEN 'MAESTRO'
        WHEN 'm_variedad' THEN 'MAESTRO' WHEN 'm_variedad_alias' THEN 'MAESTRO'
        WHEN 'm_calibre' THEN 'MAESTRO' WHEN 'm_productor_equivalencia' THEN 'MAESTRO'
        WHEN 'm_version_forecast' THEN 'MAESTRO'
        WHEN 'm_evaluador' THEN 'MAESTRO' WHEN 'm_rol' THEN 'MAESTRO'
        WHEN 'm_usuario' THEN 'MAESTRO'
        WHEN 't_calendario' THEN 'TIEMPO' WHEN 't_campania' THEN 'TIEMPO'
        WHEN 't_semana_evaluacion' THEN 'TIEMPO'
        WHEN 'evt_poda' THEN 'EVENTO'
        WHEN 'ev_evaluacion_ramas' THEN 'MOVIMIENTO' WHEN 'ev_rama_medicion' THEN 'MOVIMIENTO'
        WHEN 'ev_flores' THEN 'MOVIMIENTO' WHEN 'ev_estados' THEN 'MOVIMIENTO'
        WHEN 'ev_brotes' THEN 'MOVIMIENTO' WHEN 'ev_baya_medicion' THEN 'MOVIMIENTO'
        WHEN 'ev_evaluacion_baya' THEN 'MOVIMIENTO' WHEN 'ev_baya_observacion' THEN 'MOVIMIENTO'
        WHEN 'op_cosecha' THEN 'MOVIMIENTO' WHEN 'op_clima' THEN 'MOVIMIENTO'
        WHEN 'op_packing' THEN 'MOVIMIENTO' WHEN 'op_forecast_campania' THEN 'MOVIMIENTO'
        WHEN 'op_forecast_semanal' THEN 'MOVIMIENTO' WHEN 'op_riego_semanal' THEN 'MOVIMIENTO'
        WHEN 'op_tareo' THEN 'MOVIMIENTO'
        WHEN 'cfg_muestra_requerida' THEN 'CONFIGURACIÓN'
        WHEN 'cfg_decision' THEN 'CONFIGURACIÓN'
        ELSE '(sin clasificar)'
    END AS tipo,
    CASE c.relname
        WHEN 'm_empresa'      THEN 1 WHEN 'm_fundo'       THEN 1 WHEN 'm_fundo_alias' THEN 1
        WHEN 'm_modulo'       THEN 1 WHEN 'm_turno'       THEN 1 WHEN 'm_lote'        THEN 1
        WHEN 'm_calibre'      THEN 1 WHEN 'm_productor_equivalencia' THEN 1
        WHEN 'm_version_forecast' THEN 1 WHEN 'm_evaluador' THEN 1
        WHEN 'm_rol'          THEN 1 WHEN 'm_usuario' THEN 1
        WHEN 't_calendario'   THEN 2 WHEN 't_campania'    THEN 2
        WHEN 't_semana_evaluacion' THEN 2 WHEN 'evt_poda' THEN 2
        WHEN 'op_tareo'       THEN 3
        WHEN 'ev_evaluacion_ramas' THEN 4 WHEN 'ev_rama_medicion' THEN 4
        WHEN 'ev_flores'      THEN 4 WHEN 'ev_estados'      THEN 4
        WHEN 'ev_brotes'      THEN 4 WHEN 'ev_baya_medicion' THEN 4
        WHEN 'ev_evaluacion_baya' THEN 4 WHEN 'ev_baya_observacion' THEN 4
        WHEN 'cfg_muestra_requerida' THEN 7
        WHEN 'op_cosecha'      THEN 5 WHEN 'op_clima'       THEN 5
        WHEN 'op_packing'      THEN 5 WHEN 'op_forecast_campania' THEN 5
        WHEN 'op_forecast_semanal' THEN 5 WHEN 'op_riego_semanal' THEN 5
        WHEN 'm_variedad'     THEN 6 WHEN 'm_variedad_alias' THEN 6
        WHEN 'cfg_decision'       THEN 7
        ELSE 99
    END AS orden_dominio,
    CASE c.relname
        WHEN 'm_empresa' THEN 'Ubicación' WHEN 'm_fundo' THEN 'Ubicación'
        WHEN 'm_fundo_alias' THEN 'Ubicación' WHEN 'm_modulo' THEN 'Ubicación'
        WHEN 'm_turno' THEN 'Ubicación' WHEN 'm_lote' THEN 'Ubicación'
        WHEN 't_calendario' THEN 'Tiempo' WHEN 't_campania' THEN 'Tiempo'
        WHEN 't_semana_evaluacion' THEN 'Tiempo' WHEN 'evt_poda' THEN 'Tiempo'
        WHEN 'm_evaluador' THEN 'Identidad' WHEN 'm_usuario' THEN 'Identidad'
        WHEN 'm_rol' THEN 'Identidad' WHEN 'op_tareo' THEN 'Identidad'
        WHEN 'ev_evaluacion_ramas' THEN 'Evaluación fenológica'
        WHEN 'ev_rama_medicion' THEN 'Evaluación fenológica'
        WHEN 'ev_flores' THEN 'Evaluación fenológica' WHEN 'ev_estados' THEN 'Evaluación fenológica'
        WHEN 'ev_brotes' THEN 'Evaluación fenológica' WHEN 'ev_baya_medicion' THEN 'Evaluación fenológica'
        WHEN 'ev_evaluacion_baya' THEN 'Evaluación fenológica'
        WHEN 'ev_baya_observacion' THEN 'Evaluación fenológica'
        WHEN 'cfg_muestra_requerida' THEN 'Configuración'
        WHEN 'op_cosecha' THEN 'Operación comercial' WHEN 'op_clima' THEN 'Operación comercial'
        WHEN 'op_packing' THEN 'Operación comercial' WHEN 'm_calibre' THEN 'Operación comercial'
        WHEN 'm_productor_equivalencia' THEN 'Operación comercial'
        WHEN 'op_forecast_campania' THEN 'Operación comercial'
        WHEN 'op_forecast_semanal' THEN 'Operación comercial'
        WHEN 'op_riego_semanal' THEN 'Operación agrícola'
        WHEN 'm_version_forecast' THEN 'Operación comercial'
        WHEN 'm_variedad' THEN 'Variedad' WHEN 'm_variedad_alias' THEN 'Variedad'
        WHEN 'cfg_decision' THEN 'Configuración'
        ELSE '(sin clasificar)'
    END AS dominio,
    c.relname AS tabla,
    pg_stat_get_live_tuples(c.oid) AS filas,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS tamano,
    -- Sin recortar: truncar es una decisión de presentación, no del dato. El cliente que
    -- quiera una vista compacta puede pedir left(descripcion, N) o abrir \x en psql; si se
    -- recorta aquí, nadie puede volver a pedir el texto completo sin tocar la vista.
    obj_description(c.oid, 'pg_class') AS descripcion
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'core' AND c.relkind = 'r'
-- El ORDER BY va DENTRO de la vista a propósito: sin él, "SELECT * FROM core.v_catalogo"
-- sale en el orden que decida el plan (aquí, ninguno reconocible). No es una garantía
-- absoluta del estándar SQL para cualquier consulta externa que la envuelva, pero para el
-- uso normal — abrir la vista y mirarla — es lo que hace que salga agrupada sin que cada
-- quien tenga que acordarse de añadir "ORDER BY orden_dominio, tabla".
ORDER BY orden_dominio, tabla;

COMMENT ON VIEW core.v_catalogo IS
    'Las tablas de core agrupadas por dominio y por tipo (maestro/tiempo/evento/movimiento/'
    'configuración), con filas, tamaño y su COMMENT completo (sin truncar), ya ordenadas por '
    'dominio. Único punto de lectura para "qué hay en core y para qué sirve". Una tabla nueva '
    'sin clasificar aparece en (sin clasificar), nunca se pierde en silencio. En psql, usar '
    '\x on si el ancho de terminal corta "descripcion" al mostrarla — la vista ya entrega el '
    'texto entero.';
