# backend/campo-api · API de campo

Monolito modular FastAPI que recibe las evaluaciones de Flutter y las persiste en PostgreSQL
`core`. El contrato móvil se mantiene en `/v1`; la estructura interna sigue ADR-0016.

## Flujo

```text
Flutter -> Router HTTP -> Servicio -> Puerto (Protocol) -> Adaptador psycopg -> PostgreSQL
```

- `main.py` compone FastAPI y el router versionado.
- `api/v1/router.py` reúne las operaciones públicas de Flutter y la superficie administrativa.
- `modules/*/router.py` traduce HTTP y documenta errores.
- `modules/*/service.py` implementa los casos de uso.
- `modules/*/repository.py` declara los puertos que necesita cada módulo.
- `infrastructure/postgres/*` contiene las consultas SQL explícitas.
- `core/` centraliza configuración, errores, logging y OpenAPI.
- `modules/seguridad` implementa JWT corto + refresh y RBAC por permiso para el panel Angular.

La API no importa el ETL ni extrae Access. Las reglas de evaluaciones permanecen dentro de su
módulo hasta que exista un segundo consumidor real. El esquema se gobierna en `db/sql`; no se
duplica con un ORM ni con migraciones Alembic.

La superficie administrativa expone lecturas paginadas de evaluaciones, maestros, cuarentena,
usuarios, roles y `GET /v1/admin/cargas`. Las correcciones, altas y decisiones de QA del panel
pasan por funciones allowlisted `SECURITY DEFINER`, con validación de permisos y auditoría
append-only. Las cargas
masivas siguen `POST /v1/admin/evaluaciones/previsualizar` y `POST /v1/admin/evaluaciones/cargar`:
el primer paso guarda un manifiesto en `core.admin_carga` y el segundo confirma por UUID + SHA-256
en una transacción única sobre las tablas `ev_*`.

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
- `AQUANQA_JWT_SECRET` (obligatorio fuera de `local` y `test`)
- `AQUANQA_JWT_ACCESS_MINUTES` (por defecto `15`)
- `AQUANQA_JWT_REFRESH_DAYS` (por defecto `7`)

Para crear el primer usuario del panel, usa una conexión privilegiada separada de la conexión
normal de la API:

```powershell
$env:AQUANQA_PROVISION_DATABASE_URL = "postgresql://postgres:<password>@localhost:5432/aquanqa_migracion"
python backend/campo-api/scripts/provision_user.py --email admin@empresa.local `
    --nombre "Administrador" --rol admin
```

Para un rol no administrador, el alta exige al menos un alcance de datos; por ejemplo:

```powershell
python backend/campo-api/scripts/provision_user.py --email agronomo@empresa.local `
    --nombre "Agrónomo" --rol agronomo --scope-empresa-id 1
```

El provisioning privilegiado solo es necesario para crear la primera identidad cuando todavía no
existe una sesión administrativa. Después, el panel puede crear, editar, desactivar usuarios y
reemplazar sus alcances mediante las funciones allowlisted; la conexión de la API sigue sin DML
directo sobre las tablas de identidad/RBAC. El backend aplica los permisos aunque el frontend
oculte una opción del menú.

## Pruebas

```powershell
python -m pytest backend/campo-api/tests -q
python -m ruff check backend/campo-api/src backend/campo-api/tests backend/campo-api/scripts
$env:AQUANQA_RUN_DB_TESTS = "1"
python -m pytest backend/campo-api/tests/integration -q
```

La resolución del evaluador por DNI sigue siendo el mecanismo de identidad de captura móvil; no se
usa como contraseña ni reemplaza la autenticación administrativa.
