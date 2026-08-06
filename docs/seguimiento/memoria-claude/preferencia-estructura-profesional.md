---
name: preferencia-estructura-profesional
description: "El usuario rechaza entregables apiñados en una sola carpeta; pide estructura de monorepo por capas, profesional y escalable"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 141cb603-6181-44a5-a1c9-1122f53ba6b4
  modified: 2026-08-03T21:35:21.780Z
---

Cuando entrego un proyecto, debe tener **estructura profesional y escalable desde el
principio**: monorepo con capas separadas por ciclo de vida (`packages/`, `etl/`, `apps/`,
`bi/`, `docs/`, `infra/`), no todo dentro de una carpeta o un archivo contenido.

Rechazó explícitamente un plan cuyo entregable vivía dentro del repo de análisis existente:
*"siento que la creación de todo esto lo estás haciendo todo en una sola carpeta o archivo
contenido... al final lo que se busca es un desarrollo profesional y escalable"*.

**Why:** lo que valora no es el script que resuelve la tarea, sino **un buen punto de
partida** sobre el que crecer — con ADRs, CI, runbooks, tests y el esquema como código.
Un entregable monolítico le obliga a reorganizarlo antes de poder trabajar.

**How to apply:** al planificar cualquier entregable de software para él, separar por capas
con su propio ciclo de vida y su propia verificación desde la primera etapa. Preguntar dónde
crear el repo en lugar de asumir que va dentro del directorio de trabajo actual. Ver
[[plataforma-datos-aquanqa]].
