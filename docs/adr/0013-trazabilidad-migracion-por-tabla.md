# ADR-0013 · Trazabilidad de migración por tabla

**Estado:** aceptado
**Fecha:** 2026-08-28

## Decisión

La migración de Access se controla en dos niveles distintos:

1. `raw.source_table_snapshot` demuestra que cada tabla llegó completa desde Access a `raw`.
2. `raw.migracion_run` y `raw.migracion_tabla` demuestran el avance de una ejecución desde
   `raw` hacia `stg` y `core`.

Cada ejecución se vincula a un `source_snapshot_id` Access publicado y se inicia con las 23
fuentes registradas como `pendiente`. Una fuente pasa a `migrada` o
`migrada_con_observaciones` cuando se comprueban sus conteos de origen, staging, destino y
cuarentena. Si no existe un destino `core` aprobado, puede cerrarse como `raw_only` cuando su
conteo y justificación quedan registrados; no se fuerza una tabla `core` solo para completar el
conteo físico de Access.

## Estados y consulta operativa

- `raw.v_migracion_resumen`: avance agregado, por ejemplo `18/23` fuentes publicadas en `core`,
  `5/23` cerradas como `raw_only` y porcentaje de publicación.
- `raw.v_migracion_tablas`: detalle de cada tabla, sus destinos y conteos `raw/stg/core/qua`.
- `migrada_con_observaciones`: llegó a core, pero conserva diferencias explicadas en `qua`.
- `fallida`: la etapa no pasó el control; no se presenta como migrada.

La primera aplicación de esta decisión es la ejecución `1` de C2026: `M_Lotes` se publicó con
`882 = 882 = 882`; posteriormente se publicaron los bloques B02 a B05 y se cerró B06 como
`raw_only`. El resultado es `18/23` fuentes en `core`, `5/23` en `raw_only`, sin pendientes ni
fallos.

## Consecuencia

El script completo `50_carga_core/090_ejecutar.sql` no debe ejecutarse durante la migración por
bloques. Cada bloque debe abrir o reanudar una ejecución, cargar únicamente sus tablas aprobadas,
registrar el check-to-check y dejar el resto pendiente.
