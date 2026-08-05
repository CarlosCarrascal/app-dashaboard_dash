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
    -- CONFIGURACIÓN parámetros de negocio (core.config_decision), no describe una
    --              entidad del dominio agronómico.
    CASE c.relname
        WHEN 'empresa' THEN 'MAESTRO' WHEN 'fundo' THEN 'MAESTRO'
        WHEN 'fundo_alias' THEN 'MAESTRO' WHEN 'modulo' THEN 'MAESTRO'
        WHEN 'turno' THEN 'MAESTRO' WHEN 'lote' THEN 'MAESTRO'
        WHEN 'variedad' THEN 'MAESTRO' WHEN 'variedad_alias' THEN 'MAESTRO'
        WHEN 'calibre' THEN 'MAESTRO' WHEN 'productor_equivalencia' THEN 'MAESTRO'
        WHEN 'version_forecast' THEN 'MAESTRO'
        WHEN 'evaluador' THEN 'MAESTRO' WHEN 'rol' THEN 'MAESTRO'
        WHEN 'usuario' THEN 'MAESTRO' WHEN 'muestra_requerida' THEN 'MAESTRO'
        WHEN 'calendario' THEN 'TIEMPO' WHEN 'campania' THEN 'TIEMPO'
        WHEN 'semana_evaluacion' THEN 'TIEMPO'
        WHEN 'poda' THEN 'EVENTO'
        WHEN 'evaluacion_ramas' THEN 'MOVIMIENTO' WHEN 'rama_medicion' THEN 'MOVIMIENTO'
        WHEN 'flores' THEN 'MOVIMIENTO' WHEN 'estados' THEN 'MOVIMIENTO'
        WHEN 'brotes' THEN 'MOVIMIENTO' WHEN 'baya_medicion' THEN 'MOVIMIENTO'
        WHEN 'cosecha' THEN 'MOVIMIENTO' WHEN 'clima' THEN 'MOVIMIENTO'
        WHEN 'packing' THEN 'MOVIMIENTO' WHEN 'forecast_campania' THEN 'MOVIMIENTO'
        WHEN 'forecast_semanal' THEN 'MOVIMIENTO' WHEN 'tareo' THEN 'MOVIMIENTO'
        WHEN 'config_decision' THEN 'CONFIGURACIÓN'
        ELSE '(sin clasificar)'
    END AS tipo,
    CASE c.relname
        WHEN 'empresa'      THEN 1 WHEN 'fundo'       THEN 1 WHEN 'fundo_alias' THEN 1
        WHEN 'modulo'       THEN 1 WHEN 'turno'       THEN 1 WHEN 'lote'        THEN 1
        WHEN 'calendario'   THEN 2 WHEN 'campania'    THEN 2 WHEN 'semana_evaluacion' THEN 2
        WHEN 'poda'         THEN 2
        WHEN 'evaluador'    THEN 3 WHEN 'usuario'     THEN 3 WHEN 'rol'          THEN 3
        WHEN 'tareo'        THEN 3
        WHEN 'evaluacion_ramas' THEN 4 WHEN 'rama_medicion' THEN 4 WHEN 'flores' THEN 4
        WHEN 'estados'      THEN 4 WHEN 'brotes'      THEN 4 WHEN 'baya_medicion' THEN 4
        WHEN 'muestra_requerida' THEN 4
        WHEN 'cosecha'      THEN 5 WHEN 'clima'       THEN 5 WHEN 'packing'      THEN 5
        WHEN 'calibre'      THEN 5 WHEN 'productor_equivalencia' THEN 5
        WHEN 'forecast_campania' THEN 5 WHEN 'forecast_semanal'  THEN 5
        WHEN 'version_forecast'  THEN 5
        WHEN 'variedad'     THEN 6 WHEN 'variedad_alias' THEN 6
        WHEN 'config_decision'   THEN 7
        ELSE 99
    END AS orden_dominio,
    CASE c.relname
        WHEN 'empresa' THEN 'Ubicación' WHEN 'fundo' THEN 'Ubicación'
        WHEN 'fundo_alias' THEN 'Ubicación' WHEN 'modulo' THEN 'Ubicación'
        WHEN 'turno' THEN 'Ubicación' WHEN 'lote' THEN 'Ubicación'
        WHEN 'calendario' THEN 'Tiempo' WHEN 'campania' THEN 'Tiempo'
        WHEN 'semana_evaluacion' THEN 'Tiempo' WHEN 'poda' THEN 'Tiempo'
        WHEN 'evaluador' THEN 'Identidad' WHEN 'usuario' THEN 'Identidad'
        WHEN 'rol' THEN 'Identidad' WHEN 'tareo' THEN 'Identidad'
        WHEN 'evaluacion_ramas' THEN 'Evaluación fenológica'
        WHEN 'rama_medicion' THEN 'Evaluación fenológica'
        WHEN 'flores' THEN 'Evaluación fenológica' WHEN 'estados' THEN 'Evaluación fenológica'
        WHEN 'brotes' THEN 'Evaluación fenológica' WHEN 'baya_medicion' THEN 'Evaluación fenológica'
        WHEN 'muestra_requerida' THEN 'Evaluación fenológica'
        WHEN 'cosecha' THEN 'Operación comercial' WHEN 'clima' THEN 'Operación comercial'
        WHEN 'packing' THEN 'Operación comercial' WHEN 'calibre' THEN 'Operación comercial'
        WHEN 'productor_equivalencia' THEN 'Operación comercial'
        WHEN 'forecast_campania' THEN 'Operación comercial'
        WHEN 'forecast_semanal' THEN 'Operación comercial'
        WHEN 'version_forecast' THEN 'Operación comercial'
        WHEN 'variedad' THEN 'Variedad' WHEN 'variedad_alias' THEN 'Variedad'
        WHEN 'config_decision' THEN 'Configuración'
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
