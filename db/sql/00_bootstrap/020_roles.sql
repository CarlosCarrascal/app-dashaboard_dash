-- ============================================================================
-- 020 · Roles y permisos
--
-- Tres identidades con el mínimo privilegio que necesitan:
--   aquanqa_app  la aplicación Next.js  → escribe en core, lee reporting
--   aquanqa_bi   Power BI               → solo lectura sobre reporting
--   aquanqa_etl  el pipeline            → escribe en raw/stg/qua/dim/fact
--
-- Las contraseñas NO están aquí: las asigna `npm run setup` desde .env, para que este
-- archivo pueda versionarse sin secretos.
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aquanqa_app') THEN
        CREATE ROLE aquanqa_app LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aquanqa_bi') THEN
        CREATE ROLE aquanqa_bi LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aquanqa_etl') THEN
        CREATE ROLE aquanqa_etl LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aquanqa_analytics') THEN
        CREATE ROLE aquanqa_analytics LOGIN;
    END IF;
END
$$;

-- MLflow crea sus tablas sin prefijo de esquema. El rol analítico mantiene `mlflow` como
-- primer search_path; el código de negocio siempre referencia stg/analytics explícitamente.
ALTER ROLE aquanqa_analytics SET search_path = mlflow, public;

-- Conexión --------------------------------------------------------------------
-- current_database() en lugar de un nombre literal: el script sirve igual en local y en RDS.
DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO aquanqa_app, aquanqa_bi, aquanqa_etl, aquanqa_analytics',
        current_database()
    );
END
$$;

-- La aplicación: dueña funcional de core, lectora de reporting -----------------
GRANT USAGE ON SCHEMA core, reporting TO aquanqa_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO aquanqa_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO aquanqa_app;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO aquanqa_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA core
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aquanqa_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA core
    GRANT USAGE, SELECT ON SEQUENCES TO aquanqa_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA reporting GRANT SELECT ON TABLES TO aquanqa_app;

-- El motor analítico: lee fuentes normalizadas, registra experimentos y publica resultados.
GRANT USAGE ON SCHEMA stg, core, dim, fact, reporting, analytics, mlflow TO aquanqa_analytics;
GRANT CREATE ON SCHEMA analytics, mlflow TO aquanqa_analytics;
GRANT SELECT ON ALL TABLES IN SCHEMA stg, core, dim, fact, reporting TO aquanqa_analytics;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA analytics, mlflow TO aquanqa_analytics;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA analytics, mlflow TO aquanqa_analytics;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics, mlflow
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aquanqa_analytics;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics, mlflow
    GRANT USAGE, SELECT ON SEQUENCES TO aquanqa_analytics;

-- Power BI: solo lectura, y solo del contrato ---------------------------------
-- Deliberadamente NO ve raw, stg ni core: si un informe necesita un dato, se expone
-- como vista en reporting (ADR-0004).
GRANT USAGE ON SCHEMA reporting TO aquanqa_bi;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO aquanqa_bi;
ALTER DEFAULT PRIVILEGES IN SCHEMA reporting GRANT SELECT ON TABLES TO aquanqa_bi;

-- El ETL: escribe las capas de carga -----------------------------------------
GRANT USAGE, CREATE ON SCHEMA raw, stg, qua, dim, fact TO aquanqa_etl;
GRANT USAGE ON SCHEMA core, reporting TO aquanqa_etl;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
    ON ALL TABLES IN SCHEMA raw, stg, qua, dim, fact TO aquanqa_etl;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO aquanqa_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA raw, stg, qua, dim, fact, core TO aquanqa_etl;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, stg, qua, dim, fact
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO aquanqa_etl;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, stg, qua, dim, fact, core
    GRANT USAGE, SELECT ON SEQUENCES TO aquanqa_etl;

-- El ETL puede consultar los resultados para controles de cierre, pero no modificarlos.
GRANT USAGE ON SCHEMA analytics TO aquanqa_etl;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO aquanqa_etl;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO aquanqa_etl;
