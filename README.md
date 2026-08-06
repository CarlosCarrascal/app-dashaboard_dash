# Plataforma de datos Aqu Anqa

PostgreSQL como fuente única de la información del cultivo, con la API que recibe la captura de
campo y el modelo semántico de Power BI versionado. Access queda como archivo histórico de solo
lectura.

El punto de partida está en [`docs/historico-access/`](docs/historico-access/): 18 tablas,
41 consultas, 683.180 filas y 12 hallazgos —3 críticos— cuya raíz común es que **el motor nunca
tuvo permiso para rechazar un dato inválido**. Cero claves foráneas, dos de tres claves primarias
mal elegidas, ningún índice único. Este repositorio declara las restricciones que Access no tenía.

## Arranque

```bash
cp .env.example .env        # y poner la contraseña de PostgreSQL

npm run setup               # entorno conda, paquetes Python, base de datos y roles
npm run extract             # .accdb + xlsx  →  CSV en data/salida/  (origen en solo lectura)
npm run load                # CSV            →  esquema raw
npm run build               # raw → stg → core → dim/fact → reporting
npm run validate            # contrato de aceptación: cada cifra contra la auditoría
```

Solo hacen falta **Python y PostgreSQL**. `scripts/run.mjs` localiza `psql.exe` y el Python del
entorno conda por su cuenta: no hay que activar nada ni tocar el `PATH`. Node actúa únicamente de
lanzador de tareas — no hay dependencias npm ni código TypeScript (ADR-0006).

## Los módulos

```
db/            PostgreSQL como código: las capas SQL y el contrato de aceptación
domain/        reglas de negocio y acceso tipado a core — la importan el ETL y el backend
etl/           ingesta por lotes del histórico de Access y de los Excel (solo Windows)
backend/       campo-api: la API que reciben la app Flutter y las proyecciones en Excel
bi/            modelo semántico TMDL, medidas DAX, reapuntado del origen
docs/          auditoría congelada · ADR · runbooks · diccionario de datos
infra/         despliegue en AWS (fase posterior)
```

`db/` y `domain/` son el terreno común; los otros tres se apoyan en ellos:

```
etl/         backend/campo-api/
   \                |
    ▼               ▼
          domain/  ──▶  db/  (PostgreSQL)  ──▶  bi/
```

Tres reglas sostienen esa frontera, y CI las verifica: `domain/` no importa `fastapi` ni
`pyodbc`; `backend/` no define reglas de negocio propias; `etl/` y `backend/` no se importan entre
sí. El porqué está en [ADR-0006](docs/adr/0006-un-solo-lenguaje-de-backend.md).

## Las capas de la base

| Esquema | Qué contiene | Quién lo escribe |
|---|---|---|
| `raw` | copia fiel del origen, tipos permisivos, sin restricciones | ETL |
| `stg` | normalización y resolución de identidad | SQL |
| `qua` | cuarentena: toda fila apartada, íntegra, con su motivo | SQL |
| `core` | modelo operativo normalizado — la API escribe aquí | SQL (`db/sql/20_core`) |
| `dim` / `fact` | modelo dimensional, en vistas sobre `core` | SQL |
| `reporting` | vistas base + las 40 consultas con su nombre original | SQL |

La regla que sostiene el diseño: **cada transformación vive en una sola capa**. Nada de limpiar en
Power Query lo que ya se limpió en SQL.

Y una que no se negocia: **las invariantes viven en el motor.** `NOT NULL`, `UNIQUE`, las claves
foráneas y las filas centinela de [ADR-0005](docs/adr/0005-filas-centinela-sin-null-en-fk.md) están
en el esquema, no en el código de aplicación. La validación de `domain/` es la primera línea —da un
error legible antes de tocar la base—, no la garantía: esa tiene que valer también para un `UPDATE`
manual o un consumidor que aparezca en tres años.

La numeración de `db/sql` (`00_bootstrap` … `90_checks`) es el **orden de ejecución**, no el flujo
del dato. `20_core` va antes de `30_stg` porque las funciones de `stg` resuelven identidad contra
los maestros de `core`; el dato sigue fluyendo `raw → stg → core`.

## Documentos de referencia

| Documento | Para quién |
|---|---|
| [`docs/adr/`](docs/adr/) | por qué el modelo es como es |
| [`docs/runbooks/02-cierre-de-migracion.md`](docs/runbooks/02-cierre-de-migracion.md) | **qué significa "migrado con éxito", y qué decisiones siguen abiertas** |
| [`docs/modelo/01_mapeo_access_core.md`](docs/modelo/01_mapeo_access_core.md) | **dónde vive hoy cada una de las 235 columnas de Access, y por qué hay cada nulo** |
| [`docs/runbooks/03-cambiar-el-esquema.md`](docs/runbooks/03-cambiar-el-esquema.md) | cómo tocar el DDL sin romper el contrato |
| [`docs/historico-access/05_ADDENDA_TECNICA.md`](docs/historico-access/05_ADDENDA_TECNICA.md) | **hallazgos que corrigen el plan original — leer antes de tocar el DDL** |
| [`docs/historico-access/01_AUDITORIA.md`](docs/historico-access/01_AUDITORIA.md) | los 12 hallazgos con su evidencia |
| [`docs/historico-access/02_LOGICA_NEGOCIO.md`](docs/historico-access/02_LOGICA_NEGOCIO.md) | qué hace cada consulta de Access y por qué existe |
| [`docs/historico-access/03_GUIA_REPORTES.md`](docs/historico-access/03_GUIA_REPORTES.md) | qué cambia en los tableros y cómo explicarlo |
| [`docs/historico-access/04_PLAN_MIGRACION.md`](docs/historico-access/04_PLAN_MIGRACION.md) | plan técnico original |

## Estado

| Etapa | | |
|---|---|---|
| E0–E3 | Andamiaje, `raw`, `stg`, `core` y maestras | ✅ |
| E5 | Hechos cargados con las correcciones aplicadas | ✅ |
| E7 | Contrato de aceptación ejecutable | ✅ |
| — | Cierre de nulos de FK con filas centinela (ADR-0005) | ✅ |
| E4 | `core` como código en `domain/` | pendiente |
| E6 | Las 40 vistas de compatibilidad en `reporting` | 12 de 40 |
| E8 | Modelo estrella de BI y reapuntado de los dos informes | pendiente |
| E9 | `backend/campo-api` para la app Flutter | pendiente |

Hoy la base pasa 39 de 42 comprobaciones de su contrato. Las 3 restantes son diferencias
**esperadas y documentadas** entre el maestro de lotes vigente y el histórico de Access —más lotes
y más fundos que el origen—, no errores. El detalle está en el
[runbook de cierre](docs/runbooks/02-cierre-de-migracion.md).

La app Flutter vive en **su propio repositorio** y consume `backend/campo-api` solo por contrato
(el OpenAPI que publica). El ciclo de release de una app móvil no comparte ritmo con el de un
backend de datos.
