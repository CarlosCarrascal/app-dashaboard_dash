# Perfilado de `H01_Detalle_Cosecha`

**Fecha:** 2026-08-30  
**Base:** `aquanqa_migracion`  
**Snapshot:** Access `4`, `BD_AQUANQA_26(1).accdb`  
**Decisión actual:** `raw_only`; no promover a `core` todavía.

El perfilado es reproducible y de solo lectura:

```powershell
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/perfil_h01_detalle_cosecha.sql
```

## Evidencia observada

| Control | Resultado |
|---|---:|
| Filas en `raw` | 24.086 |
| Hashes de origen distintos | 24.086 |
| Filas extra por hash | 0 |
| Fecha mínima / máxima | 2025-01-02 / 2026-08-12 |
| Filas con números inválidos | 0 |
| Filas con valores negativos | 0 |
| Inconsistencias `kg_cosechados ≠ kg_entierro + kg_ingreso_planta` | 0 |
| Inconsistencias `kg_exportable ≠ ingreso - descarte - descarte_congelado` | 0 |

Las dos reglas aritméticas cierran dentro de una tolerancia de `0,01` kg. Esto demuestra que
las métricas internas son coherentes; no demuestra todavía que sean el mismo hecho que
`H01_ProdHistorica`.

## Grano y claves

El candidato de grano que conserva el campo `grupo` y todos los identificadores de origen tiene
24.086 grupos para 24.086 filas: no hay duplicados exactos a ese nivel.

Al quitar `grupo` aparecen 4.512 filas adicionales dentro de grupos repetidos. Por tanto, no se
puede cargar H01 agregando únicamente por fecha, módulo, turno y lote sin perder información.

La normalización genérica de texto también fusiona una pareja que debe revisarse: `GRUPO N` y
`GRUPO Ñ`. El grupo original debe conservarse y no debe normalizarse como clave de negocio hasta
que se confirme si ambos valores representan el mismo grupo.

## Identidad de ubicación

Los pares de campos que parecen equivalentes no coinciden siempre:

| Comparación | Filas diferentes |
|---|---:|
| `fundo_campo` vs `fundo_planta` | 646 |
| `modulo` vs `modulo_planta` | 800 |
| `turno` vs `turno_planta` | 763 |

La lectura segura es conservar ambos grupos de atributos. Para resolver el lote contra el maestro
principal se utilizó `fundo_campo + modulo + lote`, permitiendo que el alias ambiguo de fundo se
desambigüe mediante el módulo:

- 24.060 filas resuelven a un único `core.m_lote`.
- 26 filas no resuelven.
- 0 filas quedan ambiguas.

Las 26 filas no resueltas son `Arena Azul / M04 / L078` (17), `Arena Azul / M04 / L079` (4),
`Arena Azul / M04 / L080` (4) y `Kawsay Allpa / módulo vacío / L000` (1). No se agregaron lotes
centinela ni aliases inventados.

La campaña se puede derivar para 24.012 de las filas resueltas; 48 no obtienen campaña mediante
`core.fn_campania_de_lote`. Eso debe resolverse o quedar explícito antes de una carga a `core`.

## Conciliación contra H01 existente

La comparación se hizo después de resolver el lote y agregar el detalle a
`lote + fecha + turno`:

| Control | Resultado |
|---|---:|
| Grupos de detalle | 19.548 |
| Grupos con H01 histórico comparable | 19.241 |
| Grupos sin H01 histórico | 307 |
| Filas de detalle en grupos sin H01 | 353 |
| `kg_exportable` del detalle | 19.921.508,47 |
| `kg` H01 histórico en grupos comparables | 19.921.633,91 |
| Diferencia total en grupos comparables | -125,45 |
| Grupos con diferencia ≤ 0,01 kg | 13.800 |
| Grupos con diferencia ≤ 1 kg | 17.519 |
| Mayor diferencia absoluta | 9.297,78 kg |

Los totales comparables son cercanos, pero la distribución por lote/fecha/turno no coincide. Por
ejemplo, el 2026-01-15 para Ayllu Allpa, M12, L026, el detalle registra 397,97 kg exportables y
H01 histórico registra 9.695,75 kg. Esto impide tratar H01_DetalleCosecha como una simple recarga
de `core.op_cosecha` o como sustituto de H01 histórico.

## Decisión y siguiente validación

H01_DetalleCosecha queda completo y auditable en `raw`, pero sigue como `raw_only` porque todavía
faltan tres decisiones de negocio:

1. confirmar qué significan `campo` y `planta` y por qué sus ubicaciones pueden diferir;
2. confirmar si `grupo` es parte del hecho, una cuadrilla, un lote de proceso o una categoría de
   captura;
3. explicar los 26 lotes no resueltos, las 48 fechas sin campaña y la diferencia de distribución
   contra `H01_ProdHistorica`.

La siguiente etapa no es crear otra tabla `core` por intuición. Es revisar esas excepciones con el
responsable operativo y, con esa definición aprobada, diseñar un posible destino dedicado —por
ejemplo un hecho de detalle de cosecha— manteniendo separado el hecho consolidado
`core.op_cosecha`.
