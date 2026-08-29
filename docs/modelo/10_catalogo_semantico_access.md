# Catálogo semántico de la migración Access

La migración se gobierna por el contrato versionado
`access-c2026-2026-08-28.v1`, no por el nombre de una tabla ni por el hecho de que exista un
objeto en PostgreSQL. El catálogo técnico describe cómo viene Access; este catálogo decide
qué significa cada fuente, cuál es su grano, qué dependencias tiene y si merece un destino en
`core`.

## Regla de cobertura

Las 23 fuentes Access deben aparecer una sola vez en el modelo, distribuidas en un bloque.
Eso no significa que PostgreSQL vaya a terminar con 23 tablas: una fuente puede alimentar cero,
uno o varios objetos `stg/core`, y una fuente `raw_only` se conserva en `raw` hasta que exista
una decisión de negocio y un modelo destino aprobado.

| Bloque | Fuentes | Decisión actual |
| --- | --- | --- |
| `B01_IDENTIDAD` | `m_lotes` | `core`; maestro principal de lotes |
| `B02_CONTEXTO` | `m_evaluadores`, `m_time`, `m_n_muestra`, `m_poda`, `m_equivalencia_elifab` | `core`, después de B01 |
| `B03_FENOLOGIA` | `e01_ramas`, `e02_conteo_flores`, `e03_conteo_estados`, `e04_brotes`, `e05_diametros_bayas`, `e05_seguimiento` | `core`, después de B01+B02 |
| `B04_OPERACION` | `h00_volumen_campo`, `h01_prod_historica`, `h02_bd_elifab`, `h05_clima` | `core`, después de B01+B02 |
| `B05_PRONOSTICO` | `r08_forecast_campania`, `r09_forecast_semanal` | `core`, después de B01+B02 |
| `B06_PENDIENTES` | `h01_detalle_cosecha`, `m_presupuesto_mo`, `r08_forecast_campania_24`, `r08_forecast_campania_25`, `r09_forecast_semanal_25` | solo `raw` por ahora |

## Flujo obligatorio

1. Catalogar la copia Access en solo lectura. DAO captura relaciones y `QueryDef.SQL`; ODBC
   queda como compatibilidad para columnas, índices y extracción.
2. Extraer cada copia a un snapshot identificado por SHA-256.
3. Cargar el snapshot completo a `raw`, conservando el histórico y registrando el control por
   tabla.
4. Ejecutar el perfilado de nulidad, duplicidad, claves candidatas y relaciones.
5. Aprobar explícitamente las relaciones con evidencia. La ausencia de huérfanos no aprueba una
   FK automáticamente.
6. Abrir un bloque; materializar solo sus fuentes a `stg`, validar y publicar sus destinos de
   `core` de forma atómica. El ledger debe mostrar el check-to-check y el estado por tabla.

Comandos principales:

```powershell
node scripts/run.mjs py modelo validate
node scripts/run.mjs py modelo register --database aquanqa_migracion
node scripts/run.mjs py catalogo-access --campania C2026 `
  --access-path "C:\Users\CCARRASCAL\Downloads\BD_AQUANQA_26.accdb" `
  --output "data\salida" --require-dao
node scripts/run.mjs py perfil --database aquanqa_migracion --snapshot-id <id-access> --detalle
node scripts/run.mjs preflight --database aquanqa_migracion
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/migrar_maestro_lotes.sql
```

La ejecución `1` de C2026 ya publicó B01 a B05 y cerró B06 como `raw_only`. No se repite un
bloque publicado sobre el mismo snapshot: para reconstruir se necesita un snapshot nuevo o una
nueva versión del modelo. Los intentos fallidos/cancelados se conservan para poder reintentarlos
sin borrar la evidencia.

## Relaciones y Excel

La copia actual devuelve 0 relaciones declaradas por DAO, por lo que no se fabrican FK a partir
de nombres parecidos. Las 24 relaciones del modelo son hipótesis de negocio documentadas y se
perfilan con el snapshot; las relaciones de ubicación requieren un mapa de identidad en `stg`.

`M_Lotes` de Access es el maestro principal. Un `M_Lotes.xlsx` puede cargarse como snapshot
independiente para contraste, pero no reemplaza a Access ni se mezcla con sus filas sin un
adaptador y una decisión registrada.

## Rastreo de avance

- `raw.migracion_modelo_version`: contrato usado.
- `raw.migracion_modelo_tabla`: una fila por fuente Access y su decisión `core/raw_only`.
- `raw.migracion_perfil_tabla`: evidencia de calidad por snapshot y tabla.
- `raw.migracion_relacion_evidencia`: evidencia reproducible para relaciones candidatas.
- `raw.migracion_bloque_ejecucion`: check-to-check del bloque.
- `raw.migracion_run` y `raw.migracion_tabla`: avance global y detalle de 23 fuentes; el hecho
  de que una fila exista en `core` no la marca como migrada por sí solo.
