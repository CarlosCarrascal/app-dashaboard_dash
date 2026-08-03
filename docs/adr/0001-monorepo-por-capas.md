# ADR-0001 · Monorepo por capas con el esquema como código

- **Estado:** aceptado
- **Fecha:** 2026-08-03

## Contexto

Access dejó de ser suficiente por una razón concreta: **no tenía dónde declarar las reglas**. Sin
FK, sin PK correctas y sin índices únicos, cada defecto entraba en silencio y llegaba a los
tableros (`docs/auditoria/01_AUDITORIA.md`). Y las reglas que sí existían estaban repartidas: SQL
dentro de Access, `Table.ReplaceValue` dentro de Power Query, `SWITCH` dentro de DAX, y un
proceso de carga externo del que no queda rastro.

La migración solo sirve si además de mover los datos **cambia dónde viven las reglas**. Si acaban
repartidas otra vez, en dos años el problema es el mismo con otro motor.

## Decisión

Un solo repositorio, dividido por capas con ciclo de vida propio, y **una regla por capa**:

| Capa | Responsable | Regla |
|---|---|---|
| `packages/db/sql` | SQL versionado | estructura de `raw`, `stg`, `qua`, `dim`, `fact`, `reporting` |
| `packages/db/drizzle` | Drizzle | `core`: tablas, claves y restricciones del modelo operativo |
| `packages/shared` | TypeScript + Zod | validaciones que comparten la app y el ETL |
| `etl` | Python | extracción, carga y perfilado; **no** decide reglas de negocio |
| `apps/web` | Next.js | captura; valida contra `packages/shared`, no contra reglas propias |
| `bi` | TMDL versionado | medidas y presentación; **nunca** limpieza estructural |

Cada capa se verifica sola: los `.sql` con `90_checks`, el ETL con pytest, `core` con
`drizzle-kit check`, la app con typecheck.

## Consecuencias

- Corregir una regla es cambiar un archivo, no auditar tres herramientas.
- El diff de un cambio de esquema es revisable: `git log packages/db/` cuenta la historia del
  modelo.
- El coste es la disciplina de la frontera: es tentador arreglar un dato en Power Query porque
  es más rápido. Ver [ADR-0004](0004-frontera-de-transformacion.md).
- CI puede impedir que una migración entre sin su verificación.

## Alternativas descartadas

- **Repositorios separados** (db, etl, app, bi). Un cambio de columna toca cuatro repos y cuatro
  PR; nada garantiza que se desplieguen juntos.
- **Todo en el repositorio de auditoría** (`Downloads\Bd_Analisis`). Mezcla el análisis con el
  producto y arrastra el `.accdb` de 138 MB y los scripts temporales al proyecto.
- **Reproducir el esquema de Access en PostgreSQL y seguir con Access de fuente.** Es lo que
  `04_PLAN_MIGRACION.md` §1 descarta con razón: migrar la estructura tal cual conserva el único
  defecto que garantiza que todos los demás vuelvan.
