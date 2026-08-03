-- ============================================================================
-- 010 · Esquemas
--
-- Seis capas, cada una con una responsabilidad y una prohibición (ADR-0004).
-- Re-ejecutable: IF NOT EXISTS en todo.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS raw;
COMMENT ON SCHEMA raw IS
    'Copia fiel del origen (Access, xlsx). Tipos permisivos, sin restricciones. '
    'Prohibido interpretar, tipar o corregir aquí.';

CREATE SCHEMA IF NOT EXISTS stg;
COMMENT ON SCHEMA stg IS
    'Normalización y resolución de identidad: códigos canónicos, casts, funciones de '
    'resolución de lote. Prohibido inventar filas o descartar en silencio.';

CREATE SCHEMA IF NOT EXISTS qua;
COMMENT ON SCHEMA qua IS
    'Cuarentena. Toda fila rechazada se conserva íntegra con su motivo. '
    'Ninguna fila se descarta sin registro.';

CREATE SCHEMA IF NOT EXISTS core;
COMMENT ON SCHEMA core IS
    'Modelo operativo normalizado. La aplicación escribe aquí. Gobernado por Drizzle. '
    'Prohibido agregar para reportes.';

CREATE SCHEMA IF NOT EXISTS dim;
COMMENT ON SCHEMA dim IS
    'Dimensiones del modelo analítico, con sus claves reales.';

CREATE SCHEMA IF NOT EXISTS fact;
COMMENT ON SCHEMA fact IS
    'Hechos del modelo analítico. Los datos llegan ya limpios: prohibido limpiar aquí.';

CREATE SCHEMA IF NOT EXISTS reporting;
COMMENT ON SCHEMA reporting IS
    'Contrato estable de salida para Power BI: vistas base y las 40 consultas de Access '
    'con su nombre original. Prohibidos los filtros fijos de campaña.';

-- Extensiones -----------------------------------------------------------------
-- unaccent: comparar vocabularios de fundo escritos con y sin acento
--           ('Aqu Anqa II - Ampliación' vs '... Ampliacion').
CREATE EXTENSION IF NOT EXISTS unaccent;
-- pg_trgm: búsqueda aproximada para diagnosticar huérfanos, no para resolverlos.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
