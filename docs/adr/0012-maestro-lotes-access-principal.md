# ADR-0012 · `M_Lotes` de Access como maestro primario

- **Estado:** aceptado
- **Fecha:** 2026-08-28
- **Alcance:** precedencia entre las dos fuentes de lotes
- **Relacionado con:** [ADR-0003](0003-identidad-de-lote.md)

## Contexto

La migración conserva dos fuentes que contienen una entidad llamada `M_Lotes`:

- `raw.m_lotes`: tabla de `BD_AQUANQA_26.accdb`, snapshot Access `1`, 882 filas;
- `raw.m_lotes_maestro`: `M_Lotes.xlsx`, snapshot Excel `2`, 879 filas.

La conciliación del 2026-08-28 usó `(Fundo, Modulo, Lote)` como clave. Las 879 claves del
Excel existen en Access; no hay filas exclusivas de Excel. Access agrega tres lotes de
`Aqu Anqa 5` y los campos comunes coinciden, salvo diferencias mínimas de precisión en dos
áreas de `Aqu Anqa 6`.

## Decisión

`M_Lotes` de Access es el **maestro primario de identidad** para `stg/core`. El ETL debe
resolver los hechos desde `raw.v_m_lotes_principal_vigente`, una vista explícita sobre el
snapshot Access publicado.

`M_Lotes.xlsx` se conserva en `raw.m_lotes_maestro` como fuente externa de contraste. No se
fusiona, no reemplaza a Access y no puede eliminar ni sobrescribir filas del maestro primario
de forma automática.

Esta decisión cambia la precedencia de la fuente, pero no cambia la regla de identidad de
[ADR-0003]: la clave sigue siendo `(empresa, módulo, lote)` y nunca se debe resolver por un
alias ambiguo de fundo.

## Consecuencias

- La carga de `core` podrá continuar aunque el Excel no esté disponible.
- La cobertura primaria actual es de 882 lotes, incluidos los tres lotes adicionales de
  Access.
- Cada nueva versión de Excel debe compararse contra Access y generar diferencias auditables.
- Las diferencias de fuente no se corrigen en `raw`; cualquier normalización o cuarentena
  ocurrirá en `stg/core` con el origen conservado.
- Los contratos de conteos de `core` y `reporting` deberán rebaselinarse cuando se ejecute la
  primera carga de esas capas; no se deben reutilizar ciegamente los contratos construidos
  sobre 879 filas de Excel.
