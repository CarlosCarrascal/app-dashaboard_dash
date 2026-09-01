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

npm run setup               # entorno conda, paquetes Python, base, roles y tablas raw
npm run extract             # .accdb + xlsx  →  CSV en data/salida/  (origen en solo lectura)
npm run load                # CSV            →  esquema raw
npm run build               # raw → stg → core → dim/fact → reporting
npm run validate            # contrato de aceptación, sobre un clon temporal no mutante
npm run dashboard            # dashboard Dash oficial
```

Solo hacen falta **Python y PostgreSQL**. `scripts/run.mjs` localiza `psql.exe` y el Python del
entorno conda por su cuenta: no hay que activar nada ni tocar el `PATH`. Node actúa únicamente de
lanzador de tareas — no hay dependencias npm ni código TypeScript (ADR-0006).

Para usar el Python instalado aunque `python` no esté en el `PATH` global, se ejecuta siempre con
`python -m`. La instalación reproducible de analítica y dashboard usa las constraints verificadas:

```powershell
python -m pytest --version
python -m pip install -c constraints-analitica.txt -e "packages/analitica[dev,operativo]"
python -m pip install -c constraints-analitica.txt -e "apps/dashboard[dev]"
```

`constraints-analitica.txt` fija las versiones directas del entorno validado; no incluye `pyodbc`
porque el driver Access es opcional y depende de cada equipo Windows.

## Los módulos

```
db/            PostgreSQL como código: las capas SQL y el contrato de aceptación
etl/           ingesta por lotes del histórico de Access y de los Excel (solo Windows)
backend/       campo-api: monolito modular que recibe la app Flutter
packages/      librerías reutilizables de analítica
apps/          aplicaciones desplegables (`dashboard` y, progresivamente, `campo-api`)
bi/            modelo semántico TMDL, medidas DAX, reapuntado del origen
docs/          auditoría congelada · ADR · runbooks · diccionario de datos
infra/         despliegue en AWS (fase posterior)
```

El dashboard ya no vive dentro de `db/`: `apps/dashboard` es una aplicación independiente y
`packages/analitica` contiene únicamente el cálculo que puede reutilizarse desde distintas
interfaces. El dashboard Dash es la única interfaz web mantenida.

```
pipelines/etl/       backend/campo-api/       apps/dashboard/
       |                    |                       |
       └────────────────────┴──▶ db/ ◀─────────────┘
                                                    ▲
                                           packages/analitica
```

La API organiza sus reglas por módulo y no importa `etl/`; el ETL tampoco importa la API.
Solo se extraerá una librería compartida cuando exista un segundo consumidor real. El cambio
queda documentado en [ADR-0016](docs/adr/0016-monolito-modular-api-campo.md).

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
en el esquema, no en el código de aplicación. La validación del módulo de la API es la primera línea —da un
error legible antes de tocar la base—, no la garantía: esa tiene que valer también para un `UPDATE`
manual o un consumidor que aparezca en tres años.

La numeración de `db/sql` (`00_bootstrap` … `90_checks`) es el **orden de ejecución**, no el flujo
del dato. `20_core` va antes de `30_stg` porque las funciones de `stg` resuelven identidad contra
los maestros de `core`; el dato sigue fluyendo `raw → stg → core`.

## Documentos de referencia

| Documento | Para quién |
|---|---|
| [`docs/adr/`](docs/adr/) | por qué el modelo es como es |
| [`docs/adr/0015-arquitectura-actual-analitica.md`](docs/adr/0015-arquitectura-actual-analitica.md) | **qué significa cada carpeta de `packages/analitica` y por qué no todo lo grande debe partirse** |
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
| E4 | Reglas de captura por módulo dentro de `campo-api` | ✅ |
| E6 | Las 40 vistas de compatibilidad en `reporting` | 40 de 40 |
| E8 | Modelo estrella de BI y reapuntado de los dos informes | pendiente |
| E9 | `backend/campo-api` para la app Flutter | API interna v0.1 |

El contrato actual contiene 92 comprobaciones, incluidas las 40 vistas de compatibilidad de
`reporting`. El resultado vigente no se fija en este README: se obtiene ejecutando
`npm run validate` contra una instancia cargada. El comando muestra explícitamente la base
temporal que clona para ejecutar los checks; los `DROP`/`TRUNCATE`/`INSERT` de `90_checks` no
se ejecutan sobre `PGDATABASE`. Si hay una falla, un error o una alerta de cuarentena, el
comando termina con código distinto de cero.

La app Flutter vive en **su propio repositorio** y consume `backend/campo-api` solo por contrato
(el OpenAPI que publica). El ciclo de release de una app móvil no comparte ritmo con el de un
backend de datos.

El dashboard se despliega aparte del resto de la plataforma. El contenedor reproducible está en
[`apps/dashboard/Dockerfile`](apps/dashboard/Dockerfile) y su criterio de retiro de Streamlit en
[`docs/runbooks/04-migracion-dashboard-dash.md`](docs/runbooks/04-migracion-dashboard-dash.md).
