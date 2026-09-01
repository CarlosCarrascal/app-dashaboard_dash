-- ============================================================================
-- 30_stg · 025 · Permisos de resolución de ubicación para la API
--
-- Se ejecuta después de 020_resolucion_identidad.sql, que crea la función.
-- ============================================================================

GRANT USAGE ON SCHEMA stg TO aquanqa_app;
GRANT EXECUTE ON FUNCTION stg.fn_resolver_lote(text, text, text) TO aquanqa_app;
