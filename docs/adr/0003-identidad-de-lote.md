# ADR-0003 · La identidad de un lote es (empresa, módulo, lote)

- **Estado:** aceptado
- **Fecha:** 2026-08-03
- **Origen:** hallazgos N-3, N-4 y N-5 de `../historico-access/05_ADDENDA_TECNICA.md`

## Contexto

H-01 es el hallazgo crítico de la auditoría: el fundo se escribe de cuatro formas incompatibles y
por eso el 100% de `E01_Ramas` no enlaza con el maestro. La solución propuesta
(`04_PLAN_MIGRACION.md` §4.2) es resolver el fundo por alias y luego bajar a módulo y lote:

```sql
JOIN dim.fundo_alias fa ON fa.alias = trim(s.fundo)
JOIN dim.modulo m ON m.fundo_id = fa.fundo_id AND ...
```

Dos hechos verificados lo invalidan:

1. **El alias no determina el fundo.** `Aqu Anqa II - Kawsay Allpa` corresponde a `Aqu Anqa 3`
   en 211 lotes y a `Aqu Anqa 5` en 44. Un join por alias duplicaría filas.
2. **`(Modulo, Lote)` tampoco identifica un lote.** El maestro vigente tiene 879 filas y 870
   pares distintos: los módulos M01–M04 existen en las dos empresas a la vez.

Y un tercero, previo a cualquier join: los códigos de lote **no están normalizados** entre
fuentes (`L11B` en los hechos, `L011B` en el maestro).

## Decisión

**La clave de negocio de un lote es `(empresa, módulo, lote)`; la clave técnica es `lote_id`.**
El alias de fundo es un atributo descriptivo, nunca una clave de join.

Toda resolución pasa por una sola función, y siempre después de normalizar:

```sql
stg.fn_norm_lote(text)    -- 'L11B' | '11B' | 'l011b'  →  'L011B'
stg.fn_norm_modulo(text)  -- ' m10a ' → 'M10A' ;  '2' | 'Módulo 02' → 'M02'
stg.fn_resolver_lote(empresa, modulo, lote) → lote_id
```

`fn_resolver_lote` sigue tres reglas, en orden:

1. Si hay empresa determinable, resuelve por `(empresa, módulo, lote)`.
2. Si no la hay, acepta `(módulo, lote)` **solo cuando es único en todo el maestro** — lo es en
   861 de los 870 pares.
3. En los 9 pares ambiguos sin empresa, devuelve `NULL` y la fila va a cuarentena.

**Nunca adivina.** Una fila sin identidad resoluble se aparta con su motivo, no se fuerza a un
lote plausible.

La empresa se deriva del vocabulario de origen mediante `core.fundo_alias`, que registra los seis
vocabularios observados (los cuatro de Access más los dos que aportan `R08`/`R09`), cada uno con
su `tipo` (empresa / físico / operativo) y su `origen`.

## Consecuencias

- H-01 se resuelve sin depender de ninguna decisión de negocio: **D-4 queda cerrada por los
  datos**. El maestro vigente sustituye el vocabulario comercial antiguo (`Ampliacion`,
  `Vivadis`, `Sta.Teresa`) y `R08`/`R09`, que ya usan la nomenclatura nueva en el 96% de sus
  filas, confirman la equivalencia.
- Tras normalizar, el maestro cubre el **100%** de los `(Modulo, Lote)` del `M_Lotes` de Access y
  deja **~732 filas huérfanas de ~280.000 (0,26%)**, todas identificables una por una.
- `dim_lote` expone la clave compuesta, lo que corrige de raíz el defecto B-2 del modelo de
  Power BI, donde `LOTE` era una lista de códigos sin módulo y mezclaba lotes homónimos.
- Coste: dos funciones más que mantener y una regla que respetar en cada carga. A cambio, la
  lógica de identidad existe **en un solo lugar** y es testeable.

## Alternativas descartadas

- **Join por alias de fundo** (el plan original): duplica filas donde el alias es ambiguo.
- **`UNIQUE (modulo, lote)` global**: rechazaría 9 lotes reales del maestro.
- **Normalizar los códigos en el origen**, editando Access: la base no se modifica, es el
  compromiso de la auditoría.
- **Asignar por proximidad los lotes huérfanos**: inventa datos. Van a cuarentena con la fila
  íntegra para que Agronomía decida.
