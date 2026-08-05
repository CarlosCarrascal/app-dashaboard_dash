# ADR-0005 · Ninguna FK de un hecho queda NULL: filas centinela "Sin identificar"

- **Estado:** aceptado
- **Fecha:** 2026-08-04
- **Origen:** hallazgo N-15 de `../historico-access/05_ADDENDA_TECNICA.md`

## Contexto

Un inventario completo de las 41 claves foráneas declaradas en `core` mostró que solo 4
tenían nulos reales, pero al verificarlas una por una aparecieron dos inconsistencias que no
eran una decisión, sino un descuido:

| Columna | Nulos | Qué pasaba |
|---|---|---|
| `forecast_campania.modulo_id` | 624 de 101.714 | Quedaban con `modulo_id` NULL y **nunca se registraban en cuarentena** — a diferencia de todos los demás hechos, donde una identidad sin resolver siempre deja rastro en `qua.rechazos` |
| `forecast_semanal.lote_id` | 23 de 48.368 | Se registraban en cuarentena **y además** quedaban en `core` con `lote_id` NULL — doble contabilidad, sin excluirlas como al resto |
| `cosecha.variedad_id` | 4 de 30.540 | Legítimo: son filas que solo existen en `H01_ProdHistorica`, que nunca tuvo columna de variedad. No es un fallo de identidad, es una columna que el origen no capturó ahí |
| `fundo_alias.fundo_id` | 7 de 23 | Por diseño: la tabla existe precisamente para registrar alias que no determinan un fundo físico. La columna `ambiguo` ya gobierna ese comportamiento |

Los primeros tres son el mismo problema de fondo: una FK nula en una tabla de hechos es
frágil. Un `INNER JOIN` la hace desaparecer sin aviso; un `LEFT JOIN` bien construido la
conserva pero con una categoría vacía que nadie puede filtrar ni explicar en Power BI. Es
estructuralmente la misma clase de defecto que documenta H-01 en el origen: el motor nunca
tuvo permiso para exigir una relación completa.

## Decisión

**Ninguna FK de una tabla de hechos vuelve a ser NULL.** Cuando la identidad no resuelve, la
fila apunta a una fila centinela `es_sentinel = true` ("Sin identificar") en la dimensión
correspondiente, en lugar de dejar la columna vacía.

```sql
-- Antes
modulo_id smallint REFERENCES core.modulo(modulo_id)          -- puede ser NULL

-- Ahora
modulo_id smallint NOT NULL REFERENCES core.modulo(modulo_id)  -- el motor garantiza que nunca lo es
```

Cada dimensión que participa en una FK con nulos reales lleva su propia fila centinela:
`empresa`, `fundo`, `modulo`, `turno`, `variedad`, `lote`. Un índice único parcial garantiza
que solo pueda existir una:

```sql
CREATE UNIQUE INDEX ... ON core.modulo ((true)) WHERE es_sentinel;
```

La cadena se crea en `core.sp_cargar_ubicacion()`, antes de cargar los datos reales:
`empresa → fundo → modulo` y `turno`, `variedad` en paralelo, y `lote` al final (necesita
`modulo_id`, `turno_id` y `variedad_id` ya resueltos). Las cargas de hechos usan
`COALESCE(id_resuelto, (SELECT id FROM dimension WHERE es_sentinel))`.

**La cuarentena sigue registrando el motivo.** Apuntar al centinela no sustituye a
`qua.rechazos`: sigue existiendo el registro de *por qué* no resolvió, con la fila íntegra.
El centinela resuelve el problema de integridad referencial; la cuarentena resuelve el de
trazabilidad. Son complementarios, no alternativos.

**`fundo_alias.fundo_id` se queda como excepción, documentada.** No es una tabla de hechos:
es un diccionario donde "no determina un fundo" es un resultado válido y ya gobernado por la
columna `ambiguo`. Convertirlo a centinela sería redundante.

## Consecuencias

- Ningún `LEFT JOIN` de `dim`/`fact`/`reporting` puede perder una fila por una FK nula: la
  fila centinela siempre está ahí para que el join se resuelva.
- Power BI puede tratar "Sin identificar" como una categoría visible y filtrable —
  `es_sentinel = false` para el análisis normal, o dejarla para auditar cuánto volumen no se
  pudo ubicar — en vez de una categoría en blanco sin explicación.
- Los recuentos de filas en `core.forecast_campania` (101.714), `core.forecast_semanal`
  (48.368) y `core.cosecha` (30.540) **no cambian**: el centinela repuebla el valor, no
  excluye la fila. Lo que cambia es que ahora se puede saber cuántas filas de cada hecho
  quedaron sin identidad completa: `SELECT count(*) FROM fact.x JOIN dim.y USING(id) WHERE
  y.es_sentinel`.
- Coste: seis filas más por base, una función de coalescencia más en cada `INSERT` que las
  necesita, y un dato nuevo (`es_sentinel`) que cualquier vista de `dim` debe recordar
  exponer. A cambio, `NOT NULL` deja de ser una promesa vigilada a mano y pasa a ser una
  garantía del motor.

## Alternativas descartadas

- **Dejar la FK nula y documentarla bien** (lo que había): funciona hasta que alguien escribe
  un `INNER JOIN` o filtra sin saber que existe el hueco. La garantía debe estar en el
  esquema, no en la memoria de quien consulta.
- **Excluir de `core` toda fila sin identidad completa** (el patrón que ya usan
  ramas/flores/estados/brotes/bayas/cosecha-por-lote): válido para hechos donde la fila
  entera pierde sentido sin esa dimensión. No es correcto para forecast: una proyección de
  624 filas sigue siendo información real de producción aunque no se sepa a qué módulo
  corresponde exactamente — descartarla perdería la cifra, no solo la ubicación.
- **Usar `-1` o `0` fijo como id centinela** en lugar de dejar que la secuencia lo asigne:
  obliga a `OVERRIDING SYSTEM VALUE` en cada `INSERT` y a hardcodear el número en cada
  consulta. Resolver el id con `WHERE es_sentinel` es una línea más larga pero no depende de
  que nadie recuerde un número mágico.
