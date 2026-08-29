-- ============================================================================
-- Prepara únicamente las capas necesarias para avanzar desde raw hacia core.
-- No crea dim, fact, reporting, analytics ni mlflow.
-- ============================================================================

\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS qua;
CREATE SCHEMA IF NOT EXISTS core;

COMMENT ON SCHEMA stg IS
    'Normalización y resolución de identidad: códigos canónicos, casts y funciones de resolución.';
COMMENT ON SCHEMA qua IS
    'Cuarentena. Toda fila rechazada se conserva íntegra con su motivo.';
COMMENT ON SCHEMA core IS
    'Modelo operativo normalizado. La API de campo escribe aquí.';
