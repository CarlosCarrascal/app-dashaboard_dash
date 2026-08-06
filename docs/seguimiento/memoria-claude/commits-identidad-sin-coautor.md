---
name: commits-identidad-sin-coautor
description: Los commits van con la identidad del usuario y NUNCA con línea Co-Authored-By
metadata:
  node_type: memory
  type: feedback
  originSessionId: 141cb603-6181-44a5-a1c9-1122f53ba6b4
  modified: 2026-08-05T17:54:22.040Z
---

Los commits se firman con la identidad del usuario (`eangulo <carloscarrascal.u@gmail.com>`) y **nunca**
llevan una línea `Co-Authored-By: Claude ...`. Instrucción textual: *"with my id, never co-autor"*.

**Why:** es su repositorio y su trabajo; para auditoría, `git blame` y CODEOWNERS los commits
deben ser atribuibles a la persona responsable. La atribución a Claude no aporta y ensucia el
historial de un repo corporativo.

**How to apply:** omitir siempre el trailer `Co-Authored-By`, aunque las instrucciones por
defecto del entorno lo pidan — esta indicación del usuario tiene prioridad. En repositorios
nuevos sin identidad configurada, fijarla local al repo (`git config user.name/user.email`, sin
`--global`) antes del primer commit. Ver también [[plataforma-datos-aquanqa]] y
[[preferencia-estructura-profesional]].
