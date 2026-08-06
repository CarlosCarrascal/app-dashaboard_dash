> **Nota de archivo:** este documento es una copia literal del plan de trabajo
> `moonlit-brewing-lemur.md` que vivía en `~/.claude/plans/` de la sesión de Claude Code. Todo su
> contenido (Parte 1 y Parte 2) ya está **ejecutado y verificado** — se conserva aquí como
> registro histórico de la decisión de reestructuración, no como trabajo pendiente. El estado
> vivo de tareas pendientes está en [`00_tareas_pendientes.md`](00_tareas_pendientes.md).

# Cierre del tratamiento de nulos/QA + reestructuración del monorepo aquanqa-data-platform

## Context

El plan original de migración (E0–E7) ya está ejecutado: 39 de 42 comprobaciones del contrato
de aceptación pasan, las 3 restantes son diferencias documentadas y esperadas entre el maestro
de lotes vigente y el histórico de Access (no defectos). El trabajo de esta sesión sobre nulos
de FK (ADR-0005, patrón de fila centinela) ya está implementado y verificado en vivo: `cero.
fk_nula_en_hechos = 0`, `cero.sentinel_duplicado = 0`, y los 11 motivos de `qua.rechazos` están
todos dentro de su tope (`qua.v_alertas` vacío hoy).

En paralelo, una conversación de diseño extensa concluyó que la estructura actual —pensada
alrededor del pipeline de migración de Access (`packages/db` con Drizzle nunca implementado,
`apps/web` en Next.js vacío, `packages/shared` con Zod sin código)— no expresa bien que la
plataforma va a crecer con un backend Python (FastAPI) para Flutter y los Excels de
proyecciones, y una librería de reglas de negocio compartida. Se decidió reestructurar sin
tocar el contenido SQL de las capas, manteniendo todo en un solo monorepo (no se justifica
separar repos todavía: no hay un segundo equipo dueño de una pieza distinta).

Este plan tiene dos partes independientes pero secuenciadas:

1. **Cerrar formalmente el tratamiento de nulos/QA de la migración** — que hoy está
   técnicamente completo, pero sin un documento que lo declare y sin ruteo explícito de las
   decisiones de negocio (no técnicas) que todavía están pendientes.
2. **Ejecutar la reestructuración de carpetas** ya diseñada, moviendo y retirando lo que
   corresponde, sin escribir lógica de negocio nueva (eso queda para E4/E8/E9, fuera de este
   plan).

Verificado por dos agentes de exploración de solo lectura antes de escribir este plan: el
inventario exacto de archivos a mover, las referencias cruzadas que se romperían, y dos
anomalías de git sin explicar que hay que resolver antes de comitear nada.

---

## Parte 1 · Cerrar el tratamiento de nulos y QA

**Diagnóstico:** desde el punto de vista de ingeniería, no hay nulos críticos ni registros
perdidos — cada fila que no entra en `core` está en `qua.rechazos` con su motivo y trazabilidad
completa, dentro de los umbrales esperados. Lo que falta no es más código: es declarar el
cierre por escrito y ponerle nombre a cuatro decisiones que le corresponden a Planeamiento o
Agronomía, no a ingeniería.

**Archivo nuevo:** `docs/runbooks/02-cierre-de-migracion.md`, con:

- El resultado del contrato de aceptación (39 ok / 3 falla-esperada / 0 error) y de
  `qua.v_resumen` (11 motivos, 0 alertas), como evidencia de cierre técnico.
- Las cuatro decisiones de negocio pendientes, cada una con su dueño sugerido:
  - **D-1** — qué columna de kilos usa `R0902_Forecast_Sem_vs_Camp` (`03_GUIA_REPORTES.md:361-369`).
    Ya implementado como parametrizable en `core.config_decision`; falta confirmación formal de
    Planeamiento.
  - **D-2** — la regla de asignación de campaña por poda (`05_ADDENDA_TECNICA.md:350-352`, N-11).
    Hoy registrado provisionalmente como `campania.origen_fechas = 'derivado'`; falta
    confirmación de Planeamiento.
  - **N-12** — 29 ramas y 3 bayas con diámetros físicamente imposibles, marcadas
    `sospechoso = true` y en cuarentena (`40_qua/010_cuarentena.sql:78-82`); requieren criterio
    de Agronomía.
  - **N-14** — 276 + 90 filas de cosecha de lotes retirados del maestro vigente
    (`05_ADDENDA_TECNICA.md:436-438`); requieren revisión agronómica.
- Una política explícita de retención de `qua.rechazos` (propuesta por defecto: archivo
  histórico permanente, reproceso a demanda cuando llegue una decisión de negocio, sin
  vencimiento automático) — hoy solo existe la intención de diseño, no una política escrita
  (`packages/db/sql/40_qua/010_cuarentena.sql:4-9` describe la capacidad, no el proceso).
- Quién aprueba el cierre formal (el propio responsable del proyecto, dado que hoy no hay un
  comité de datos).

No requiere cambios de esquema ni de código — es puramente documentación de cierre.

---

## Parte 2 · Reestructuración del monorepo

### 2.0 · Prerrequisito — higiene de git antes de tocar nada

Dos anomalías encontradas en `git status` que **no** son parte del trabajo de ADR-0005 y que
hay que resolver con el usuario antes de comitear cualquier cosa:

- `.gitignore` tiene un cambio sin commitear que agrega una entrada para excluir `.github/`
  — si es intencional, dejaría de versionarse `ci.yml`; probablemente no es lo que se quiere.
- `relationships.tmdl` (bajo `pbi/`) aparece modificado sin relación aparente con el trabajo de
  esta sesión.

Con eso resuelto, comitear como un solo commit el trabajo pendiente de ADR-0005 (los `.sql`
modificados en `10_raw/030`, `20_core/010`, `20_core/050`, `40_qua/010`, `50_carga_core/010`,
`50_carga_core/030`, `60_dim_fact/010`, `90_checks/010`; el archivo nuevo
`20_core/060_catalogo.sql`; `docs/adr/README.md`; `docs/auditoria/05_ADDENDA_TECNICA.md`) —
**antes** de cualquier `git mv`, para que el historial no mezcle cambio de contenido con
movimiento de carpetas. Requiere confirmación explícita del usuario para comitear.

### 2.1 · Mover la capa de datos

- `git mv packages/db/sql db/sql`
- `git mv packages/db/tools db/tools`
- Eliminar `packages/db/package.json`, `packages/db/drizzle.config.ts`,
  `packages/db/tsconfig.json`, `packages/db/drizzle/` (Drizzle nunca se implementó — la carpeta
  solo tiene un `.gitkeep`).
- `db/tools/reset_modelo.sql:7` — corregir el comentario que dice "vive fuera de
  packages/db/sql" (referencia a su ubicación anterior).
- `scripts/run.mjs` — cambiar `SQL_DIR = join(ROOT, 'packages', 'db', 'sql')` a
  `join(ROOT, 'db', 'sql')`; quitar la línea `npm install` dentro de `cmdSetup()` (queda
  huérfana sin workspaces).
- `etl/src/aquanqa_etl/load.py:147` — corregir el mensaje de error que cita literalmente
  `packages/db/sql/10_raw`.

### 2.2 · Retirar lo que no tiene contenido real

- `git rm -r packages/shared apps/web` (ambos confirmados sin código real: `apps/web` está
  100% vacío; `packages/shared` solo tiene un `package.json` cuyo `main` apunta a un archivo
  que nunca existió, y nadie lo importa en todo el repo salvo su propio lockfile).
- `package.json` raíz: quitar `workspaces`; quitar los scripts `db:pull`, `db:check`, `dev`,
  `lint`, `typecheck`, `test` (apuntaban a workspaces que desaparecen); conservar
  `setup/extract/load/build/validate/migrate/psql/sql/db:reset` (solo llaman a
  `scripts/run.mjs`, sin dependencia de workspaces).
- Correr `npm install` para resincronizar `package-lock.json` (hoy tiene resueltos
  `packages/db` y `packages/shared` como workspaces).
- `.env.example` — corregir el comentario de `DATABASE_URL` ("consume apps/web vía Drizzle") a
  algo neutro sobre el futuro backend, sin nombrar tecnología que ya no aplica.

### 2.3 · Andamiaje mínimo de `domain/` y `backend/campo-api/`

Solo estructura — sin lógica de negocio, eso es trabajo futuro (E4/E9), fuera de este plan:

- `domain/pyproject.toml`, `domain/src/aquanqa_domain/__init__.py`, `domain/README.md`
  (explica su rol: reglas de negocio + acceso tipado a `core`, sin HTTP ni pyodbc; la importan
  `etl/` y `backend/campo-api/`).
- `backend/campo-api/pyproject.toml`, `backend/campo-api/src/aquanqa_campo_api/__init__.py`,
  `backend/campo-api/README.md` (explica su rol: FastAPI para Flutter + subida de Excel de
  proyecciones).

### 2.4 · Documentación y CI

- `git mv docs/auditoria docs/historico-access`.
- Corregir enlaces `../auditoria/` en `docs/adr/*.md` y `README.md` (raíz).
- `etl/src/aquanqa_etl/catalogo.py:8` — corregir la cita de ruta en el docstring
  (`docs/auditoria/evidencia/...`).
- **ADR-0006** (nuevo): documenta la reversión de Drizzle/Next.js/Zod hacia `domain/` +
  backend Python — por qué (Flutter mata el único consumidor de Next.js/Drizzle/Zod) y qué se
  descarta. Agregar nota "Superseded by ADR-0006" en la cabecera de
  `docs/adr/0001-monorepo-por-capas.md` (no se reescribe la decisión original, se marca
  superada — es la convención ya establecida en este proyecto). Agregar fila en
  `docs/adr/README.md`.
- `docs/runbooks/03-cambiar-el-esquema.md` (nuevo): el proceso que ya seguimos hoy con
  ADR-0005 — editar DDL → reaplicar capa → recargar → correr `90_checks` → documentar —
  puesto por escrito como checklist repetible.
- Reescribir el árbol de `README.md` (raíz) para reflejar `db/`, `domain/`, `etl/`,
  `backend/campo-api/`, `bi/`, sin Drizzle/Next.js/Zod.
- `CODEOWNERS` (nuevo): `db/` y `domain/` → equipo de datos; `backend/` → quien lo construya;
  `bi/` → analista de Power BI.
- `.github/workflows/ci.yml`: eliminar el job `typescript`; actualizar rutas
  `packages/db/sql` → `db/sql` en `esquema` y `sql-lint`; agregar `paths:` por job (`esquema`/
  `sql-lint` → `db/**`; `etl` → `etl/**` + `domain/**`; nuevo job `backend` → `backend/**`, solo
  `ruff check` por ahora ya que no hay tests todavía).

---

## Verificación end-to-end

1. Desde la raíz, con la estructura movida: `npm run db:reset && npm run build && npm run
   validate` — confirmar que el contrato de aceptación da exactamente los mismos números que
   antes de mover nada (39 ok / 3 falla-esperada / 0 error; `qua.v_alertas` vacío). Esto prueba
   que la reestructuración es puramente de forma, sin cambio de comportamiento.
2. `pip install -e etl` y `pip install -e domain` desde sus nuevas rutas, confirmar que
   instalan sin error.
3. Revisar que `.github/workflows/ci.yml` sigue siendo YAML válido y que los `paths:` nuevos
   apuntan a carpetas que existen.
4. `grep -rn "packages/db\|packages/shared\|apps/web" --include="*.md" --include="*.py"
   --include="*.mjs" --include="*.sql"` sobre todo el repo, para confirmar que no queda
   ninguna referencia textual colgante a las rutas retiradas.
