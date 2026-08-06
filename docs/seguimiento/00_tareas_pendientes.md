# Tareas pendientes del proyecto

**Generado:** 2026-08-06, a partir del tablero de tareas de la sesión de Claude Code, del plan
de migración (`docs/historico-access/04_PLAN_MIGRACION.md` §8) y del runbook de cierre
(`docs/runbooks/02-cierre-de-migracion.md` §3). Es una fotografía de un momento, no un tablero
vivo — la fuente de verdad para el estado técnico sigue siendo `npm run validate`.

---

## 1 · Tablero de tareas (fases E0–E9)

| # | Tarea | Estado |
|---|---|---|
| 1 | E0 · Andamiaje del monorepo `aquanqa-data-platform` | ✅ completada |
| 2 | E1 · Extraer Access/xlsx y cargar capa `raw` | ✅ completada |
| 3 | E2 · Funciones de normalización e identidad en `stg` | ✅ completada |
| 4 | E3 · `core` y dimensiones maestras | ✅ completada |
| 5 | **E4 · `core` como código en `domain/` (sin Drizzle)** | ⬜ pendiente |
| 6 | E5 · Cargar hechos con las correcciones aplicadas | ✅ completada |
| 7 | E6 · Capa `reporting` y 40 vistas de compatibilidad | ✅ completada |
| 8 | E7 · Contrato de aceptación ejecutable | ✅ completada |
| 9 | **E8 · Modelo estrella de BI y reapuntado de informes** | ⬜ pendiente |
| 10 | **E9 · `backend/campo-api` (FastAPI) para Flutter** | ⬜ pendiente |
| 11 | Cerrar los nulos de FK con filas centinela (ADR-0005) | ✅ completada |
| 12 | Escribir runbook de cierre de nulos/QA | ✅ completada |
| 13 | Investigar anomalías de git antes de comitear | ✅ completada |
| 14 | Comitear trabajo pendiente de ADR-0005 | ✅ completada |
| 15 | Mover `packages/db` → `db/` | ✅ completada |
| 16 | Retirar `packages/shared` y `apps/web` | ✅ completada |
| 17 | Crear andamiaje de `domain/` y `backend/campo-api/` | ✅ completada |
| 18 | Renombrar `docs/auditoria` y escribir ADR-0006 | ✅ completada |
| 19 | Reescribir `README.md` raíz y agregar `CODEOWNERS` | ✅ completada |
| 20 | Actualizar CI (`ci.yml`) con `paths:` por módulo | ✅ completada |
| 21 | Verificación end-to-end de la reestructuración | ✅ completada |
| 22 | Contabilidad fila por fila Access → `core` → cuarentena | ✅ completada |
| 23 | Corregir N-16 · separar `peso_kg` de `peso_kg_lote` | ✅ completada |
| 24 | Corregir N-17 · cargar `E03.F16` como `estados.hora` | ✅ completada |
| 25 | Corregir N-19 · rescatar el programa de las 390 filas | ✅ completada |
| 26 | Corregir N-22 · comentarios obsoletos de N-9 | ✅ completada |
| 27 | Resolver los nulos pendientes de la migración | ✅ completada |
| 28 | Generar el HTML de auditoría monocromático | ✅ completada |
| 29 | E6 · Bloque 1: flores/ramas (01xx + 02xx) | ✅ completada |
| 30 | E6 · Bloque 2: estados/brotes (03xx + 04xx) | ✅ completada |
| 31 | E6 · Bloque 3: cosecha/clima/maestros (H0xxx + M_) | ✅ completada |
| 32 | E6 · Bloque 4: forecast (R0xxx) | ✅ completada |
| 33 | E6 · Checks del contrato para las 36 vistas nuevas | ✅ completada |

### Lo inmediato

**#33** quedó completada (2026-08-06): las 36 vistas de `reporting` de los bloques 1-4 tienen
su cifra de control en `db/sql/90_checks/010_contrato.sql` (grupo `reporting`) y su propia
sección en el informe (`090_informe.sql`). `npm run validate` corre entero: 83 comprobaciones,
0 falla, 0 error — CONTRATO CUMPLIDO. Ya no se verifican ad-hoc.

El siguiente paso natural es una de las tres fases grandes sin iniciar (#5, #9 o #10) — ninguna
tiene prioridad técnica sobre las otras; la elección depende de qué necesite el negocio primero.

### Fases grandes sin iniciar

- **#5 — E4:** `core` como código en `domain/` — acceso tipado a `core` desde Python, sin
  Drizzle (decisión tomada en ADR-0006). Lo importarían `etl/` y `backend/campo-api/`.
- **#9 — E8:** modelo estrella de BI y reapuntado de los informes de Power BI. Hoy
  `SEGUIMIENTO DE CAMPAÑA` y `SEGUIMIENTO DE PERSONAL` siguen leyendo
  `C:\Users\gsanchez\Downloads\BD_AQUANQA_26.accdb`, no la base nueva.
- **#10 — E9:** `backend/campo-api` (FastAPI) para la app Flutter y la subida de Excels de
  proyecciones. Hoy solo existe el andamiaje (`pyproject.toml` + paquete vacío).

---

## 2 · Decisiones de negocio abiertas (no técnicas)

De `docs/runbooks/02-cierre-de-migracion.md` §3. Ninguna bloquea el uso de la base — todas
están implementadas con un supuesto explícito y reversible — pero el cierre **funcional** de la
migración no se puede declarar hasta que alguien con autoridad las confirme.

| Punto | Qué falta decidir | Dueño sugerido | Supuesto vigente |
|---|---|---|---|
| D-1 | Qué columna de kilos usa `R0902_Forecast_Sem_vs_Camp` | Planeamiento | `KG Exp`, parametrizado en `core.config_decision` |
| D-2 | La regla de asignación de campaña por poda | Planeamiento | `campania.origen_fechas = 'derivado'` |
| N-12 | 29 ramas y 3 bayas con diámetros físicamente imposibles — ¿decimales perdidos o se descartan? | Agronomía | Cargadas con `sospechoso = true`, en cuarentena |
| N-14 | 276 + 90 filas de cosecha de lotes retirados del maestro vigente — ¿vuelven, se reasignan, o quedan fuera? | Agronomía | En cuarentena, motivo `LOTE_INEXISTENTE` |
| N-18 | El turno se descarta en 5 tablas (H01, E05, M_Poda, M_nMuestra, R09) — ¿es derivable del lote? | Sin dueño asignado | No se carga; nadie lo ha comprobado |
| N-21 | 6 columnas de packing/Elifab sin significado documentado (`ENSAYO`, `S26`, `S271`, `Packet`, `Clasificación`, `ACDT 2`) | Operaciones de packing | Ni cargadas ni justificadas |
| — | 105 filas de cosecha (0,34%) con kilos discrepantes entre H00 y H01 — ¿cuál vale? | Agronomía | Se conservan ambas cifras en paralelo (`kg` y `kg_h01`) |

**Nota de vigencia:** el runbook de cierre ya se refrescó (2026-08-06) — el punto 5 de §2 ya no
dice que N-16/N-17/N-19/N-22 estén pendientes; documenta que las cuatro están corregidas
(tareas #23-26) y que solo N-18 y N-21 quedan como hallazgos de documentación/decisión, ambos
en esta tabla.

---

## 3 · Pendiente de datos externos (no derivable del código, viene de memoria de sesiones previas)

- **`Query Tareo 2026.xlsx`** — vive en SharePoint *Oficinas Prize Peru - Cosecha y
  Operaciones* (cuenta de `gsanchez`), no sincronizado en este equipo. Bloquea cargar
  `fact.tareo` y por tanto todo el dominio de `SEGUIMIENTO DE PERSONAL`. Hay que pedirlo.
- Los dos informes Power BI de gerencia (`SEGUIMIENTO DE CAMPAÑA`, `SEGUIMIENTO DE PERSONAL`)
  siguen apuntando al `.accdb` en la laptop de `gsanchez` — lo resuelve la fase #9 (E8).

---

## 4 · Reestructuración del monorepo — ya ejecutada

El plan completo de reestructuración de carpetas (mover `packages/db` → `db/`, retirar
`packages/shared`/`apps/web`, crear `domain/` y `backend/campo-api/`, renombrar
`docs/auditoria` → `docs/historico-access`, ADR-0006, CI por `paths:`) está **100% ejecutado y
verificado** (tareas #12-21). Se conserva una copia literal del plan original en
[`01_plan_reestructuracion_ejecutado.md`](01_plan_reestructuracion_ejecutado.md) de esta misma
carpeta, como registro histórico de la decisión — no como trabajo pendiente.
