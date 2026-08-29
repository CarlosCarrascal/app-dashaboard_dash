# Acta de conciliación de `raw` — Access C2026

**Fecha de revisión:** 2026-08-28
**Base revisada:** `aquanqa_migracion`
**Base del dashboard:** `aquanqa` (fuera de alcance y sin cambios)
**Fuente:** `C:\Users\CCARRASCAL\Downloads\BD_AQUANQA_26.accdb`
**Snapshot Access:** `1`
**SHA-256:** `ec14eb01d897d89b67f26182617a4fd0058dec0d945ce0ea57b1702ac258a16b`
**Estado técnico:** `aprobado` y publicado como snapshot vigente

## Decisión de esta etapa

Se **aprueba técnicamente la carga de Access en `raw`**. Las diferencias que aparecen en
`raw.carga_log` no son diferencias entre Access y PostgreSQL: son diferencias contra el
baseline histórico generado el 2026-08-02. El archivo Access actualmente utilizado fue
modificado el 2026-08-28 y contiene un alcance y un estado de datos distintos.

La aprobación significa lo siguiente:

- las 23 tablas del catálogo Access fueron extraídas;
- las 23 tablas se cargaron en `raw` con sus filas, hashes y metadatos;
- para cada tabla, las filas del CSV, el manifiesto y PostgreSQL coinciden;
- repetir el mismo snapshot no inserta filas adicionales;
- no se corrigen, deduplican ni eliminan datos en `raw`.

Esta aprobación **no** significa que las reglas de negocio, las relaciones, los duplicados
de origen o la selección de una única fuente para `core` estén resueltos. Esos temas se
tratarán después, conservando siempre el registro original en `raw`.

El snapshot Access `1` fue promovido después de esta revisión y ahora es el snapshot vigente
de Access para `C2026`. La promoción solo actualizó las vistas de `raw` en
`aquanqa_migracion`; no modificó `aquanqa`.

## Evidencia técnica

| Control | Resultado |
|---|---:|
| Tablas Access en el manifiesto | 23 de 23 |
| Filas Access cargadas en `raw` | 888.514 |
| Filas del maestro externo `M_Lotes.xlsx` | 879 |
| Controles `source_table_snapshot` de Access | 23 |
| CSV/manifiesto/`raw` por tabla | Coinciden |
| Recarga del mismo manifiesto | 0 filas duplicadas por ETL |
| Esquemas posteriores creados | Ninguno: solo `public` y `raw` |

El snapshot se extrajo con `solo_lectura=true`, `alcance=completo` y `snapshot_completo=true`.
El archivo físico tenía fecha de modificación `2026-08-28T03:17:41Z`; la extracción se
registró a las `2026-08-28T03:54:28Z`.

## Conciliación contra el baseline histórico

El baseline histórico no es un segundo snapshot fila a fila: solo contiene conteos de una
versión anterior de Access. Por ello se usa para detectar cambios, no como una restricción
que obligue a recortar el archivo actual.

| Tabla | Actual en `raw` | Baseline 02-ago | Delta | Resolución para `raw` |
|---|---:|---:|---:|---|
| `e01_ramas` | 94.236 | 94.236 | 0 | Aceptada; los duplicados de origen quedan preservados. |
| `e02_conteo_flores` | 54.099 | 43.490 | +10.609 | Aceptada como evolución del Access actual. Hay 9.407 filas con fecha posterior al 02-ago. |
| `e03_conteo_estados` | 24.001 | 18.714 | +5.287 | Aceptada como evolución del Access actual. Hay 5.288 filas con fecha posterior al 02-ago. |
| `e04_brotes` | 3.385 | 3.385 | 0 | Aceptada. |
| `e05_diametros_bayas` | 4.193 | 4.193 | 0 | Aceptada; conserva duplicados presentes en el origen. |
| `h00_volumen_campo` | 32.399 | 30.812 | +1.587 | Aceptada como versión actual; el aumento es igual al de H01. |
| `h01_prod_historica` | 32.213 | 30.626 | +1.587 | Aceptada como versión actual; la relación H00/H01 queda pendiente para `core`. |
| `h02_bd_elifab` | 142.413 | 117.536 | +24.877 | Aceptada como alcance actual de Access; requiere tipado y reglas en `core`. |
| `h05_clima` | 155.274 | 155.588 | -314 | Aceptada como versión actual; el origen actual no contiene duplicados de timestamp. |
| `m_equivalencia_elifab` | 15 | 15 | 0 | Aceptada. |
| `m_evaluadores` | 40 | 31 | +9 | Aceptada como revisión del maestro; hay 31 activos y 9 inactivos. |
| `m_lotes` | 882 | 860 | +22 | Aceptada como revisión del maestro; las 882 claves `(Fundo, Modulo, Lote)` son distintas. |
| `m_n_muestra` | 681 | 681 | 0 | Aceptada. |
| `m_poda` | 2.156 | 2.159 | -3 | Aceptada como versión actual; no hay evidencia de pérdida en el ETL. |
| `m_time` | 2.555 | 2.189 | +366 | Aceptada como revisión de calendario; el actual cubre 2022-01-03 a 2028-12-31. |
| `r08_forecast_campania` | 117.593 | 101.715 | +15.878 | Aceptada como alcance/versiones actuales; se separan tablas históricas `_24` y `_25`. |
| `r09_forecast_semanal` | 46.519 | 48.368 | -1.849 | Aceptada como alcance actual; el archivo actual separa además `r09_forecast_semanal_25`. |

### Tablas Access sin línea comparable en el baseline

Las siguientes tablas llegaron en el catálogo Access actual y no tienen `filas_esperadas`
en el baseline histórico. No se consideran faltantes ni desviaciones:

| Tabla | Filas actuales |
|---|---:|
| `e05_seguimiento` | 1.161 |
| `h01_detalle_cosecha` | 24.086 |
| `m_presupuesto_mo` | 1.272 |
| `r08_forecast_campania_24` | 6.932 |
| `r08_forecast_campania_25` | 75.383 |
| `r09_forecast_semanal_25` | 67.026 |

Estas tablas se cargan en `raw` porque forman parte del Access actual completo. Su uso en
`core` se decidirá por separado.

## Conciliación de `M_Lotes`: Access versus Excel

Se comparó `raw.m_lotes` del snapshot Access `1` contra `raw.m_lotes_maestro` del snapshot
Excel `2`, usando como clave de comparación `(Fundo, Modulo, Lote)`.

| Control | Access | Excel | Resultado |
|---|---:|---:|---|
| Filas | 882 | 879 | Access tiene 3 filas adicionales |
| Claves `(Fundo, Modulo, Lote)` | 882 | 879 | Todas son únicas en cada fuente |
| Claves comunes | 879 | 879 | Coinciden todas |
| Filas solo en Access | 3 | — | `Aqu Anqa 5 / M16 / L000`, `M17 / L000`, `M18 / L000` |
| Filas solo en Excel | — | 0 | No existen |
| Fundos distintos | 6 | 6 | Coinciden |
| Módulos distintos | 25 | 25 | Coinciden |

En las 879 claves comunes, todos los campos de negocio coinciden exactamente salvo la
representación numérica de `area`. La diferencia textual se debe a precisión de flotante del
origen: 877 áreas son iguales con tolerancia menor a `0,000001` ha. Solo dos áreas presentan
una diferencia numérica medible, ambas en `Aqu Anqa 6`:

| Fundo | Módulo | Access | Excel | Diferencia ha |
|---|---|---:|---:|---:|
| Aqu Anqa 6 | M19 | 55,805809020996094 | 55,8058052062988 | +0,0000038147 |
| Aqu Anqa 6 | M20 | 55,805809020996094 | 55,8058052062988 | +0,0000038147 |

Los tres registros adicionales de Access son:

| Fundo | Módulo | Lote | Área ha | N plantas | Fecha siembra | `key_map` |
|---|---|---|---:|---:|---|---|
| Aqu Anqa 5 | M16 | L000 | 34,72999954223633 | 197.324 | 2025-12-29 | `AQ2M16L000` |
| Aqu Anqa 5 | M17 | L000 | 31,59000015258789 | 178.979 | 2026-02-25 | `AQ2M17L000` |
| Aqu Anqa 5 | M18 | L000 | 35,709999084472656 | 196.098 | 2026-03-26 | `AQ2M18L120` |

Por eso, los totales difieren únicamente por esas tres filas y por el redondeo numérico:

| Total | Access | Excel | Diferencia Access - Excel |
|---|---:|---:|---:|
| Área ha | 1.242,102973 | 1.140,072967 | +102,030006 |
| N plantas | 7.015.542 | 6.443.141 | +572.401 |

### Decisión recomendada para `core`

Para esta migración, `M_Lotes` de Access debe ser el **maestro primario**, porque es la
fuente que se está migrando, contiene todas las claves presentes en Excel y agrega tres
lotes. `M_Lotes.xlsx` debe conservarse en `raw` como fuente externa de contraste y no debe
fusionarse ni reemplazar silenciosamente a Access.

Antes de materializar el maestro en `core`, se debe confirmar con el área responsable que
los tres lotes de `Aqu Anqa 5` son válidos y que las diferencias mínimas de área de `M19` y
`M20` son solo precisión de origen. Técnicamente no hay razón para bloquear la migración de
`raw` por estas diferencias.

## Diferencia de fuente versus duplicación del ETL

La existencia de hashes repetidos en algunas tablas no demuestra una duplicación causada
por el ETL. Son repeticiones que ya existen dentro del archivo Access y se conservan para
trazabilidad. En la carga actual se observaron, entre otros:

| Tabla | Filas excedentes por `source_row_hash` repetido |
|---|---:|
| `e01_ramas` | 23.141 |
| `e02_conteo_flores` | 160 |
| `e05_diametros_bayas` | 290 |
| `h02_bd_elifab` | 3.102 |
| `r08_forecast_campania` | 5.756 |

El caso histórico de `h05_clima` es distinto: el baseline documentaba 2.079 grupos de
timestamps duplicados; en el Access actual los 155.274 timestamps son distintos. Esto es
compatible con una revisión del archivo fuente, no con filas descartadas silenciosamente
por la carga. La deduplicación de negocio, cuando corresponda, se hará en `stg/core` y se
registrará en `qua`.

También se preservan en `raw` las filas subtotal que ya existían en H00/H01 (una y dos
filas con dimensiones nulas, respectivamente). No se eliminan en esta etapa.

## Decisiones que quedan para la siguiente etapa

La etapa `raw` queda cerrada desde el punto de vista técnico. Antes de construir `core` se
deben documentar estas decisiones funcionales:

1. cuál es la fuente de verdad para kilos de cosecha entre H00 y H01 en C2023/C2024;
2. qué versión/campaña de R08 y R09 es la vigente para cada indicador;
3. cómo se resolverán los alias de `Fundo`, el enlace por DNI de evaluadores y los
   duplicados de mediciones;
4. qué tablas de Access son necesarias para la aplicación y cuáles solo son históricos o
   insumos de reportes.

Hasta que esas decisiones existan, no se crea `dim`, `fact`, `reporting` ni `analytics`, y
no se modifica `aquanqa`. El siguiente paso operativo es validar funcionalmente los tres
lotes adicionales de Access y luego diseñar `stg/core` tomando Access como maestro primario.

## Referencias de evidencia

- `docs/historico-access/evidencia/04_metricas_validacion.txt`
- `docs/historico-access/01_AUDITORIA.md`
- `data/salida/snapshots/C2026/20260828T035330Z_ec14eb01d897d89b/access_snapshot.json`
- `docs/runbooks/03-migracion-access-raw-core.md`
- `data/salida/guardas/aquanqa_migracion_pre_raw_reset_20260828.baseline.json`
