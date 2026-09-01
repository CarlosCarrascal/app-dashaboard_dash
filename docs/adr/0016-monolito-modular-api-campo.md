# ADR-0016 · Monolito modular para la API de campo

- **Estado:** aceptado
- **Fecha:** 2026-08-31
- **Supera:** la parte de [ADR-0006](0006-un-solo-lenguaje-de-backend.md) que ubicaba reglas y
  persistencia en un paquete compartido `domain/`. Mantiene Python como lenguaje de backend y
  la separación física entre ETL de Windows y API desplegable en Linux.

## Contexto

La primera API funcional concentró esquemas, reglas, catálogos, identidad y todas las consultas
PostgreSQL en `domain/`. Se justificó como código compartido entre ETL y API, pero la revisión de
imports demostró que el ETL nunca lo consumió. El único consumidor real era `campo-api`.

Mantener esa extracción prematura producía una dependencia adicional, un repositorio PostgreSQL
de más de quinientas líneas con responsabilidades distintas y documentación que no coincidía con
el código. La app Flutter ya consume nueve operaciones `/v1`; la refactorización debe preservar
ese contrato.

## Decisión

`backend/campo-api` será un monolito modular organizado por capacidad funcional:

```text
api/v1/router.py
modules/{evaluaciones,catalogos,identidad,health}/
    router.py -> service.py -> repository.py (Protocol)
infrastructure/postgres/
    connection.py + un adaptador por módulo
core/
    settings.py, errors.py, logging.py, openapi.py
```

Las rutas solo traducen HTTP; los servicios expresan casos de uso; los puertos `Protocol`
definen qué persistencia necesitan; los adaptadores psycopg contienen SQL explícito. El DDL de
`db/sql` sigue siendo la fuente de verdad. No se introducen ORM, Alembic, carpetas CRUD,
microservicios ni infraestructura distribuida sin una necesidad comprobada.

Las reglas puras viven junto al módulo que las usa. Si aparece un segundo consumidor real, solo
se extraerán los contratos y reglas puras que ambos necesiten; no se compartirá el adaptador de
PostgreSQL por defecto.

## Contrato y documentación

Se conservan las nueve operaciones `/v1`, los payloads compatibles con Flutter y la semántica de
idempotencia. FastAPI publica Swagger en `/docs`, ReDoc en `/redoc` y OpenAPI en
`/openapi.json`. Cada operación declara `operation_id`, descripción, respuestas de error y
ejemplos. `docs/api/openapi-v1.json` es la copia versionada y una prueba falla si el esquema se
modifica sin regenerarlo conscientemente.

## Consecuencias

- Los cambios de catálogos, identidad y evaluaciones quedan aislados por módulo.
- Los servicios se prueban sin FastAPI ni PostgreSQL.
- La API deja de depender de un paquete compartido que no tenía un segundo consumidor.
- El SQL sigue visible y auditable, con transacciones e idempotencia intactas.
- La autenticación JWT/OAuth2 continúa pendiente del panel administrativo; la resolución por DNI
  sigue documentada como mecanismo interno temporal.

## Alternativas descartadas

- **Microservicios por módulo:** añaden despliegues y coordinación sin equipos ni cargas que lo
  justifiquen.
- **SQLAlchemy/SQLModel y Alembic ahora:** duplicarían el gobierno de un esquema que ya vive en
  `db/sql`, sin mejorar el caso de uso actual.
- **Conservar `domain/` por si acaso:** una frontera compartida se crea cuando existe el segundo
  consumidor, no antes.
