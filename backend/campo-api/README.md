# backend/campo-api · API de campo

Monolito modular FastAPI que recibe las evaluaciones de Flutter y las persiste en PostgreSQL
`core`. El contrato móvil se mantiene en `/v1`; la estructura interna sigue ADR-0016.

## Flujo

```text
Flutter -> Router HTTP -> Servicio -> Puerto (Protocol) -> Adaptador psycopg -> PostgreSQL
```

- `main.py` compone FastAPI y el router versionado.
- `api/v1/router.py` reúne las nueve operaciones públicas.
- `modules/*/router.py` traduce HTTP y documenta errores.
- `modules/*/service.py` implementa los casos de uso.
- `modules/*/repository.py` declara los puertos que necesita cada módulo.
- `infrastructure/postgres/*` contiene las consultas SQL explícitas.
- `core/` centraliza configuración, errores, logging y OpenAPI.

La API no importa el ETL ni extrae Access. Las reglas de evaluaciones permanecen dentro de su
módulo hasta que exista un segundo consumidor real. El esquema se gobierna en `db/sql`; no se
duplica con un ORM ni con migraciones Alembic.

## Contrato y Swagger

Con el servidor levantado:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Copia versionada: `docs/api/openapi-v1.json`

Para regenerar la copia después de un cambio deliberado de contrato:

```powershell
python backend/campo-api/scripts/export_openapi.py
python -m pytest backend/campo-api/tests/contract -q
```

## Levantar en local

La configuración rechaza cualquier base distinta de `aquanqa_migracion` para evitar escrituras
accidentales sobre la base del dashboard.

```powershell
python -m pip install -e "backend/campo-api[dev]"
$env:AQUANQA_API_DATABASE_URL = "postgresql://aquanqa_app:<password>@localhost:5432/aquanqa_migracion"
python -m uvicorn aquanqa_campo_api.main:app --host 0.0.0.0 --port 8000
```

Variables opcionales:

- `AQUANQA_API_PREFIX` (por defecto `/v1`)
- `AQUANQA_API_ENVIRONMENT` (por defecto `local`)
- `AQUANQA_API_PUBLIC_URL` (URL que Swagger mostrará como servidor)
- `AQUANQA_API_LOG_LEVEL` (por defecto `INFO`)

## Pruebas

```powershell
python -m pytest backend/campo-api/tests -q
python -m ruff check backend/campo-api/src backend/campo-api/tests backend/campo-api/scripts
$env:AQUANQA_RUN_DB_TESTS = "1"
python -m pytest backend/campo-api/tests/integration -q
```

La resolución del evaluador por DNI es temporal y no equivale a autenticación. JWT/OAuth2 se
incorporará cuando el panel administrativo defina usuarios, credenciales y asignaciones.
