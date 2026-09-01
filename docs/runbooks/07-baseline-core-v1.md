# Línea base `core_baseline_v1`

**Estado:** capturada y validada  
**Fecha:** 2026-08-30  
**Base:** `aquanqa_migracion`  
**Alcance:** únicamente el modelo físico de `core` y su control de migración. La base `aquanqa`, utilizada por el dashboard, queda fuera de esta línea base.

## Qué queda congelado

La línea base corresponde al snapshot Access vigente:

| Elemento | Valor |
|---|---|
| Snapshot publicado | `4` |
| Archivo | `BD_AQUANQA_26(1).accdb` |
| SHA-256 | `93c52d2167c39b5f8d2e9a577b9419fc37eadc30d0298fdbc9fdb90c6c7af76b` |
| Contrato de extracción | `access-complete-v5` |
| Modelo vigente | `access-c2026-2026-08-28.v2` |
| Run de migración | `8` |

El archivo de conteos reproducible se generó en:

`data/salida/guardas/core_baseline_v1.json`

SHA-256 de esa captura: `F6F307074659249D6206190D8949EA994ACE5434EA205E7A4D0D6837EA68B7CD`.

## Resultado de la auditoría física

Se ejecutó:

```powershell
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/auditoria_core_baseline.sql
```

Resultado:

```text
OK core_baseline_v1: 34 tablas, 46 FK (45 internas + 1 linaje), 0 huerfanos.
```

Las 34 tablas de `core` tienen clave primaria y cumplen los prefijos semánticos aprobados. Las
46 claves foráneas se distribuyen así:

- 45 relaciones internas entre tablas `core`.
- 1 relación técnica de linaje: `core.ev_evaluacion_baya → raw.source_snapshot`.
- 0 huérfanos en las 45 relaciones internas.

Las únicas tablas sin ninguna FK de negocio son las esperadas: `core.op_clima`,
`core.t_calendario` y `core.t_semana_evaluacion`. No se aprobaron relaciones candidatas por
inferencia: las 48 relaciones del perfilado continúan en estado `candidata`.

El ERD recibido en `C:\Users\CCARRASCAL\Downloads\erd.pgerd` contiene 34 tablas `core` y 45
enlaces, por lo que coincide con el DER relacional interno validado. La FK de linaje hacia `raw`
no forma parte del DER de negocio `core` y por eso no se dibuja en el ERD core-only.

## Qué significa respecto a Access

Las 34 tablas físicas no significan 34 tablas Access ya migradas. El ledger vigente registra 23
fuentes Access:

- 18 fuentes con destino aprobado en `core`.
- 5 fuentes conservadas como `raw_only`: `h01_detalle_cosecha`, `m_presupuesto_mo`,
  `r08_forecast_campania_24`, `r08_forecast_campania_25` y `r09_forecast_semanal_25`.

Una fuente puede producir varias tablas `core` —por ejemplo, `M_Lotes` alimenta el bloque de
identidad— y una tabla `core` puede consolidar varias fuentes —por ejemplo, `core.op_cosecha`
consolida H00 y H01. Por eso el avance oficial sigue siendo el ledger
`raw.v_migracion_tablas`, no el número de tablas que aparecen en el navegador de pgAdmin.

## Reglas para no perder esta línea base

Antes de cada nuevo Access:

1. ejecutar la auditoría de `core`;
2. generar un baseline nuevo de `core` con `node scripts/run.mjs py baseline --database aquanqa_migracion --schema core`;
3. cargar el archivo nuevo únicamente como snapshot en `raw`;
4. comparar tablas, columnas, hashes y conteos contra el snapshot publicado;
5. promover y ejecutar bloques solo después de validar el nuevo snapshot;
6. cerrar el check-to-check por fuente con `raw/stg/core/qua`, duplicados, huérfanos, rechazos y linaje.

No se debe ejecutar una reconstrucción completa de `core` solo porque el archivo Access tenga
una tabla nueva o una columna nueva. Primero se actualiza el contrato, se perfila el grano y se
aprueba explícitamente el destino.

## Aislamiento del dashboard

No se ejecutó ningún DDL ni carga sobre `aquanqa`. Los esquemas `dim`, `fact`, `reporting`,
`analytics` y `mlflow` tampoco pertenecen a esta migración. La visualización actual continúa
operando con su propia base mientras `aquanqa_migracion` se valida por etapas.
