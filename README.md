# Plataforma de datos Aqu Anqa

Migración de `BD_AQUANQA_26.accdb` a PostgreSQL, con la aplicación de captura que sustituye al
Excel de origen y el modelo semántico de Power BI versionado.

El punto de partida está documentado en [`docs/auditoria/`](docs/auditoria/): 18 tablas,
41 consultas, 683.180 filas y 12 hallazgos —3 críticos— cuya raíz común es que **el motor
nunca tuvo permiso para rechazar un dato inválido**. Este repositorio declara las
restricciones que Access no tenía.

## Arranque

```bash
cp .env.example .env        # y poner la contraseña de PostgreSQL

npm run setup               # entorno conda + dependencias + base de datos y roles
npm run extract             # .accdb + xlsx  →  CSV en data/salida/  (origen en solo lectura)
npm run load                # CSV            →  esquema raw
npm run build               # raw → stg → core → dim/fact → reporting
npm run validate            # contrato de aceptación: cada cifra contra la auditoría
```

Eso es todo lo necesario. `scripts/run.mjs` localiza `psql.exe` y el Python del entorno conda
por su cuenta: no hace falta activar nada ni tocar el PATH.

## Capas

| Esquema | Qué contiene | Quién lo escribe |
|---|---|---|
| `raw` | copia fiel del origen, tipos permisivos, sin restricciones | ETL |
| `stg` | normalización y resolución de identidad | SQL |
| `qua` | cuarentena: toda fila rechazada, íntegra, con su motivo | SQL |
| `core` | modelo operativo normalizado — la aplicación escribe aquí | Drizzle |
| `dim` / `fact` | modelo dimensional | SQL |
| `reporting` | vistas base + las 40 consultas con su nombre original | SQL |

La regla que sostiene el diseño: **cada transformación vive en una sola capa**. Nada de limpiar
en Power Query lo que ya se limpió en SQL.

## Estructura

```
docs/          auditoría original congelada · ADRs · runbooks · diccionario de datos
packages/db/   el esquema como código: SQL por capas + Drizzle para core
packages/shared/  tipos y validaciones Zod que comparten la app y el ETL
etl/           extracción y carga (Python) con sus tests
apps/web/      Next.js: captura de evaluaciones de campo
bi/            modelo semántico TMDL, medidas DAX, reapuntado de origen
infra/         despliegue en AWS (fase posterior)
```

## Documentos de referencia

| Documento | Para quién |
|---|---|
[`docs/auditoria/01_AUDITORIA.md`](docs/auditoria/01_AUDITORIA.md) | los 12 hallazgos con su evidencia
[`docs/auditoria/02_LOGICA_NEGOCIO.md`](docs/auditoria/02_LOGICA_NEGOCIO.md) | qué hace cada consulta y por qué existe
[`docs/auditoria/03_GUIA_REPORTES.md`](docs/auditoria/03_GUIA_REPORTES.md) | qué cambia en los tableros y cómo explicarlo
[`docs/auditoria/04_PLAN_MIGRACION.md`](docs/auditoria/04_PLAN_MIGRACION.md) | plan técnico original
[`docs/auditoria/05_ADDENDA_TECNICA.md`](docs/auditoria/05_ADDENDA_TECNICA.md) | **hallazgos posteriores que corrigen el plan — leer antes de tocar el DDL**
[`docs/adr/`](docs/adr/) | por qué el modelo es como es
