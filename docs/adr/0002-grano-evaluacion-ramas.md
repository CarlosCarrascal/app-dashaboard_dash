# ADR-0002 · El grano de la evaluación de ramas: cabecera y detalle

- **Estado:** aceptado
- **Fecha:** 2026-08-03
- **Origen:** hallazgo N-1 de `../auditoria/05_ADDENDA_TECNICA.md`

## Contexto

`04_PLAN_MIGRACION.md` §3.4 declara para `fact.ramas`:

```sql
ramas_total  smallint NOT NULL,
diametro     numeric(6,3) NOT NULL,
UNIQUE (lote_id, fecha, cortina, hilera, planta)
```

La verificación demuestra que esa clave tiene **5.384 combinaciones** para 94.236 filas: el
`UNIQUE` rechazaría el 94% de los datos. La causa es que el grano no es la planta:

- `# Ramas` es el **número de la rama medida** (rango 1–33), no un total.
- `Diametro` es el diámetro **de esa rama**.
- `Ramas <5` y `Ramas >5` son conteos **declarados de la planta**, repetidos en cada fila.

Una planta evaluada produce tantas filas como ramas se le midan.

## Decisión

Dos entidades:

```
core.evaluacion_ramas          una fila por planta evaluada en una fecha        5.384
  ├── lote_id, fecha, cortina, hilera, planta, evaluador_id
  ├── ramas_menor5, ramas_mayor5        conteos declarados por el evaluador
  └── UNIQUE (lote_id, fecha, cortina, hilera, planta)

core.rama_medicion             una fila por rama medida                       71.095
  ├── evaluacion_ramas_id → core.evaluacion_ramas
  ├── nro_rama, diametro
  └── clave sustituta, sin UNIQUE natural
```

**La deduplicación de H-03 se define como fila de origen exactamente idéntica**, que es la única
definición que reproduce las 71.095 filas de aceptación y las 23.141 de exceso que publica la
auditoría.

`rama_medicion` **no** lleva `UNIQUE (evaluacion_ramas_id, nro_rama)`: hay 4.557 filas donde la
misma rama aparece con diámetro distinto. Se cargan todas y se registran en
`qua.rechazos` con motivo `CONFLICTO_DIAMETRO_RAMA` para que Agronomía resuelva. Declarar ese
`UNIQUE` obligaría a elegir un diámetro arbitrariamente.

## Consecuencias

- El total de ramas se calcula, según lo que se quiera medir:
  - **declaradas** → `SUM(ramas_menor5 + ramas_mayor5)` sobre la cabecera = **110.095**
  - **medidas** → `COUNT(*)` sobre el detalle = **71.095**
- **`SUM([# Ramas]) = 730.318` se retira como métrica de control**: es una suma de índices. Toda
  medida de Power BI que hoy sume esa columna está mal y hay que revisarla.
- `AVG(diametro)` sigue siendo válido y comparable: **10,8869165** sobre filas distintas frente a
  10,9776539 con duplicados.
- La app de captura puede registrar rama a rama, que es como se mide en campo.

## Alternativas descartadas

- **Una tabla con `UNIQUE (lote_id, fecha, cortina, hilera, planta)`** — el DDL original: pierde
  el 94% de los datos.
- **Una tabla con `UNIQUE (…, nro_rama)`**: pierde 4.557 filas y esconde un conflicto de captura
  que alguien debería ver.
- **Una tabla plana sin restricciones**: reproduce las cifras pero deja que la próxima recarga
  vuelva a duplicar, que es exactamente H-03.

## Pendiente de confirmación

Que `# Ramas` es el índice de la rama es una lectura de los datos, muy respaldada (secuencia
1…22 correlativa con `Id` consecutivo, `Ramas <5`/`Ramas >5` constantes en el grupo, rango
máximo 33), pero **conviene que Agronomía la confirme** antes de comunicar el cambio de la
métrica de ramas al área de Reportes.
