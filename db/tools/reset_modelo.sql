-- ============================================================================
-- Herramienta de desarrollo · reconstruir el modelo desde cero
--
-- Borra core, stg, qua, dim, fact y reporting, y los deja listos para que `npm run build`
-- los vuelva a crear. **No toca `raw`**, así que no hay que repetir la extracción del .accdb.
--
-- No forma parte del pipeline: vive fuera de db/sql para que no se ejecute por accidente.
-- Se lanza a mano:
--
--     npm run db:reset
--
-- Mientras `db/sql` siga siendo la fuente de verdad del esquema (ADR-0006), reconstruir desde
-- cero es la forma normal de aplicar un cambio de DDL en local: ver
-- `docs/runbooks/03-cambiar-el-esquema.md`.
-- ============================================================================

DROP SCHEMA IF EXISTS reporting CASCADE;
DROP SCHEMA IF EXISTS fact CASCADE;
DROP SCHEMA IF EXISTS dim CASCADE;
DROP SCHEMA IF EXISTS qua CASCADE;
DROP SCHEMA IF EXISTS stg CASCADE;
DROP SCHEMA IF EXISTS core CASCADE;

CREATE SCHEMA core;
CREATE SCHEMA stg;
CREATE SCHEMA qua;
CREATE SCHEMA dim;
CREATE SCHEMA fact;
CREATE SCHEMA reporting;

\echo 'Esquemas recreados. `raw` sigue intacto: ejecuta `npm run build`.'
