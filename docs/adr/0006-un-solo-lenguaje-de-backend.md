# ADR-0006 · Un solo lenguaje de backend: `domain/` en Python, sin Drizzle ni Next.js

- **Estado:** aceptado
- **Fecha:** 2026-08-05
- **Supera:** la tabla de capas de [ADR-0001](0001-monorepo-por-capas.md), en lo que asignaba a
  Drizzle, Zod y Next.js. El resto de ADR-0001 —un solo repositorio, una regla por capa, el
  esquema como código— sigue vigente y es lo que sostiene esta decisión.

## Contexto

ADR-0001 repartió las responsabilidades entre dos runtimes: SQL y Python para los datos,
TypeScript para `core` (Drizzle), las validaciones compartidas (Zod) y la app de captura
(Next.js). Era coherente **mientras la app de captura fuera web**.

Dejó de serlo. La captura de campo se va a hacer con una app **Flutter** nativa, en su propio
repositorio. Eso vació de contenido a las tres piezas TypeScript a la vez:

| Pieza | Para qué existía | Qué queda de eso |
|---|---|---|
| `apps/web` (Next.js) | La app de captura | Nada. Flutter la reemplaza. La carpeta estaba **vacía**, sin un solo archivo |
| `packages/shared` (Zod) | Validaciones que compartían la app web y el ETL | Nada. Su único consumidor TypeScript era `apps/web`; el `package.json` declaraba un `main` que **nunca existió** y nadie lo importaba |
| `packages/db/drizzle` | Gobernar `core` desde TS | Nada. Nunca se implementó: la carpeta solo tenía un `.gitkeep`, y `core` lo gobierna el DDL de `db/sql/20_core` |

Quedaba entonces un monorepo que exigía Node, npm workspaces, conda y Python para contribuir,
donde el único trabajo real de Node era `scripts/run.mjs` —un lanzador de tareas de 240 líneas
que solo usa built-ins—. Las 18 entradas de `node_modules` eran, todas, dependencias de las tres
piezas abandonadas.

Al mismo tiempo aparecieron dos consumidores nuevos que **sí** necesitan un backend vivo: la app
Flutter, y los Excel de proyecciones que los ingenieros calibran a mano y hoy nadie consolida
salvo copiando y pegando.

## Decisión

**Un solo lenguaje de backend: Python.** Se retiran Next.js, Drizzle, Zod, los workspaces npm y
el lockfile. Lo que hacían pasa a tres paquetes Python, con una frontera explícita entre ellos:

```
etl/         backend/campo-api/        (el que venga después)
   \                |                         /
    \               |                        /
     ▼              ▼                       ▼
              domain/     reglas de negocio + acceso tipado a core
                 │        sin HTTP, sin pyodbc, sin nada de un cliente concreto
                 ▼
              db/sql/     PostgreSQL: core, qua, dim/fact, reporting
```

| Paquete | Qué es | Qué NO puede importar |
|---|---|---|
| `domain/` | Librería compartida: reglas de negocio y acceso tipado a `core`. Sustituye a Drizzle **y** a Zod | `fastapi`, `pyodbc` |
| `etl/` | Ingesta por lotes de fuentes de baja confianza: el Access histórico y los Excel. Solo Windows | `backend/*` |
| `backend/campo-api/` | Fachada HTTP para la app Flutter y la subida de Excel. Contenedor Linux en AWS | `etl/`, y no define ninguna regla propia |

Tres reglas de dependencia sostienen la frontera:

1. **`domain/` no importa `fastapi` ni `pyodbc`.** Si algún día no importa sin ellos, algo se
   filtró donde no debía. Verificable: `python -c "import aquanqa_domain"` en un entorno sin esas
   dos librerías.
2. **`backend/*` no define reglas de negocio.** Una ruta recibe, llama a `domain/`, devuelve.
   Cuando aparezca un segundo consumidor, importa la misma validación en vez de reescribirla.
3. **`etl/` y `backend/*` no se importan entre sí.** Si uno necesita algo del otro, esa lógica
   pertenecía a `domain/`.

**`scripts/run.mjs` se queda.** Node sobrevive solo como lanzador de tareas: localiza `psql` y el
Python de conda para que nadie tenga que activar entornos a mano. No tiene dependencias npm y no
se despliega a ningún sitio.

**`packages/db/sql` pasa a `db/sql`.** Sin Drizzle ni `package.json`, no era un paquete npm; era
SQL en una carpeta con dos niveles de anidación de más.

**Y la capa por capas del SQL no se toca.** `raw → stg → qua → core → dim/fact → reporting`
sigue igual, con la misma numeración. Es el patrón estándar de un pipeline ELT (el mismo que dbt
formalizó), y agrupar por dominio de negocio en su lugar rompería el orden de ejecución —que es
un DAG que cruza capas— sin resolver nada.

## Consecuencias

- **Un ingeniero nuevo instala Python y PostgreSQL, y ya puede contribuir a todo el repositorio.**
  Antes necesitaba además Node, npm y entender workspaces. Era la barrera de onboarding más
  grande, y no compraba nada.
- Las reglas de validación se escriben **una vez**, en Pydantic, y valen para la captura desde
  Flutter y para la ingesta de Excel. Con Zod solo valían para lo que pasara por TypeScript, que
  al final iba a ser nada.
- `mismo lenguaje ≠ mismo desplegable`. `etl/` no puede vivir en el contenedor del backend: el
  driver ODBC de Access solo existe en Windows. Por eso son dos paquetes y no dos carpetas del
  mismo — es una restricción física, no una preferencia de organización.
- **Las invariantes siguen en el motor.** `NOT NULL`, `UNIQUE`, las claves foráneas y las filas
  centinela de [ADR-0005](0005-filas-centinela-sin-null-en-fk.md) no se mudan a Pydantic. La
  validación de `domain/` es la primera línea —da un error legible antes de tocar la base—, no
  la garantía. Mover las invariantes al código de aplicación reabriría el defecto raíz que
  documenta la auditoría: *el motor nunca tuvo permiso para rechazar un dato inválido*, y esta
  vez el agujero sería para cualquier vía de escritura que no pase por la API.
- Se pierde el tipado end-to-end TypeScript que Drizzle prometía. No se pierde nada real: nunca
  llegó a existir, y el cliente que lo habría consumido es Dart.
- CI deja de tener un job de TypeScript y gana filtros por `paths`, para que un cambio en `bi/`
  no dispare las pruebas del ETL.

## Alternativas descartadas

- **Mantener Next.js solo como API para Flutter.** Sería sostener un segundo runtime, un segundo
  gestor de dependencias y un segundo lenguaje de validación para exponer JSON, cuando el ETL ya
  vive en Python y las proyecciones —que exigen `pandas`/`openpyxl`— también.
- **Separar `backend/` a su propio repositorio.** La señal para hacerlo no es el tamaño del
  código: es que exista **un equipo distinto** dueño de esa pieza. Hoy no existe. Mientras las
  mismas personas mantienen `db/`, `domain/` y el backend, separar convierte cada cambio de
  esquema en dos PR coordinados a mano, un paquete que versionar y un índice privado que operar
  —y rompe el commit atómico que hoy permite cambiar el DDL, la carga y el contrato de aceptación
  a la vez y verificarlo en una sola corrida—. Cuando aparezca ese equipo, la frontera de
  `domain/` ya está trazada y mover la carpeta será barato.
- **Reorganizar `db/sql` por dominio de negocio** (`domains/mediciones/` con su raw, su stg, su
  core y su carga juntos). Es el patrón correcto para microservicios y el equivocado para un
  pipeline: el orden de ejecución es un DAG que cruza capas —`core.lote` tiene que existir antes
  de que `core.baya_medicion` lo referencie—, y agrupar por dominio no elimina esa dependencia,
  la esconde y obliga a reintroducir el orden *entre* carpetas.
- **Mover `stg`/`qua` a Python "para abaratar cómputo de RDS".** El problema no existe a esta
  escala: la carga completa de packing (117.536 filas) tarda 8,2 s, y forecast (150 K filas)
  8,8 s. Y el coste real de mover las validaciones fuera del motor no es de CPU: es perder la
  garantía frente a toda escritura que no pase por el código de aplicación.
- **Reemplazar `scripts/run.mjs` por Dagster o Prefect.** Un orquestador resuelve reintentos,
  paralelismo, dependencias complejas y alertas. Hoy hay un pipeline, un desarrollador y
  ejecución manual — y el control de fallos que sí importa (`qua.umbral` + el contrato de
  aceptación) está hecho a medida de los defectos de *este* dominio, algo que ningún orquestador
  trae de fábrica. Se reevalúa cuando el backend reciba escrituras concurrentes de Flutter,
  Excel y sincronización de Access a la vez.
