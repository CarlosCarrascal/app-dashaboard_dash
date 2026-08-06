---
name: plataforma-datos-aquanqa
description: Contexto de negocio y consumo real del BI de Aqu Anqa (arándano) tras la auditoría de BD_AQUANQA_26.accdb
metadata:
  node_type: memory
  type: project
  originSessionId: 141cb603-6181-44a5-a1c9-1122f53ba6b4
  modified: 2026-08-03T21:35:33.179Z
---

Aqu Anqa produce arándano (829 ha, 4,7 M plantas, campañas C2022–C2026). Desde 2026-08-03 se
migra `BD_AQUANQA_26.accdb` a PostgreSQL 18 + app Next.js/Drizzle, en el monorepo
`C:\Users\CCARRASCAL\Proyectos\aquanqa-data-platform`.

Contexto que **no** está en el repo de auditoría y que descubrí inspeccionando el TMDL de los
dos informes Power BI (`SEGUIMIENTO DE CAMPAÑA`, `SEGUIMIENTO DE PERSONAL`):

- Ambos informes leen `C:\Users\gsanchez\Downloads\BD_AQUANQA_26.accdb` — el reporting de
  gerencia depende de un Access en la carpeta Descargas de una laptop personal.
- `SEGUIMIENTO DE PERSONAL` mide productividad de evaluadores y cruza las tablas de evaluación
  con `Query Tareo 2026.xlsx`, en la biblioteca SharePoint *Oficinas Prize Peru - Cosecha y
  Operaciones* del mismo usuario. Ese archivo **no está sincronizado** en el equipo de
  CCARRASCAL: hay que pedirlo para migrar ese dominio.
- El maestro vigente de lotes es `C:\Users\CCARRASCAL\Downloads\M_Lotes.xlsx` (879 lotes,
  6 fundos `Aqu Anqa 1..6`, módulos M01–M24), no el `M_Lotes` de Access (860 lotes).

**Why:** los cuatro documentos de auditoría midieron el linaje solo dentro de Access, así que
dan por no consumidas tablas que Power BI sí lee y por no respondidas preguntas que los
tableros sí responden.

**How to apply:** ante cualquier duda sobre qué se consume realmente, mirar el TMDL de
`docs/auditoria/pbi/`, no solo las 40 consultas de Access. Ver
[[preferencia-estructura-profesional]].

> **Nota de vigencia (al copiar este archivo a `docs/`, 2026-08-06):** `docs/auditoria/` ya se
> renombró a `docs/historico-access/` (tarea #18); el TMDL de Power BI vive ahora en `pbi/` en
> la raíz del repo, no dentro de `docs/`. La referencia a Next.js/Drizzle también quedó
> superada por ADR-0006 (backend Python en vez de Next.js).
