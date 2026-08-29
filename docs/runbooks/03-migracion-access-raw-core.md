# Migración controlada de Access a PostgreSQL

Este runbook cubre únicamente la migración y el modelo de datos. La base `aquanqa` queda
operativa para el dashboard. La migración se ejecuta en `aquanqa_migracion` y no debe apuntar a
`aquanqa` hasta que exista un cutover aprobado.

Las reglas ejecutables y no negociables de esta operación están en
[`00-reglas-obligatorias-migracion.md`](00-reglas-obligatorias-migracion.md). El preflight debe
pasar antes de cada bloque:

```powershell
node scripts/run.mjs preflight --database aquanqa_migracion
```

## Principios

- Access se abre en solo lectura y cada archivo físico se identifica por SHA-256.
- Las 23 tablas de Access se copian completas a `raw`; las consultas guardadas se catalogan en
  `raw.access_query_catalog`, pero no se convierten automáticamente en tablas.
- Antes de cargar `core` existe un contrato semántico versionado: clasifica las fuentes por
  bloque, grano, claves candidatas y decisión `core/raw_only`.
- Las relaciones son candidatas hasta que el perfilado del snapshot entregue evidencia y una
  persona las apruebe explícitamente. Los nombres similares no crean FK.
- `raw` es append-only por snapshot. Repetir el mismo archivo no inserta duplicados.
- La vista `raw.v_*_vigente` solo cambia después de validar y promover un snapshot.
- Excel, como `M_Lotes.xlsx`, tiene su propio snapshot y se conserva como fuente de contraste;
  no reemplaza a `M_Lotes` de Access como maestro primario (ADR-0012).
- `core` se materializa solo desde las vistas `raw` vigentes, pasando por `stg` y dejando los
  conflictos en `qua.rechazos`.
- `raw.migracion_run` y `raw.migracion_tabla` registran el avance por capa. Las 23 tablas de
  Access se siembran como pendientes al iniciar una ejecución y cada tabla solo pasa a
  `migrada` después de comprobar `raw → stg → core`, dejando las observaciones en `qua`.
- Las 34 tablas base de `core` son una definición de destino; una tabla no se considera migrada
  por existir, sino por su estado cerrado en `raw.v_migracion_tablas`.

## Primera carga o nueva base destino

La primera etapa no necesita el modelo completo. Para crear una base aislada con únicamente
`raw` y sus controles usa:

```powershell
node scripts/run.mjs raw-only --database aquanqa_migracion
```

`build`/`migrate` sin `--full` son comandos incrementales y solo aplican la fase `raw`. La
opción `--full` queda reservada para un entorno efímero o una reconstrucción legacy controlada;
no la uses contra la base del dashboard.

Desde la raíz del repositorio:

```powershell
$env:PGDATABASE = "aquanqa_migracion"
node scripts/run.mjs raw-only --database aquanqa_migracion
```

`raw-only` crea únicamente el modelo de ingestión; no modifica `aquanqa`. Si la base no existe,
créala con
`CREATE DATABASE aquanqa_migracion ENCODING 'UTF8' TEMPLATE template0` y vuelve a ejecutar el
comando anterior.

Antes de cualquier cambio en la base que ya consume el dashboard, registra un backup físico y
una línea base de conteos:

```powershell
node scripts/run.mjs backup --database aquanqa
```

El comando genera un `.dump` en `data/salida/guardas/` y un `.baseline.json` con el estado de
las tablas. El backup no modifica la base origen.

## Extraer una versión de Access

```powershell
node scripts/run.mjs py extract `
  --campania C2026 `
  --access-path "C:\Users\CCARRASCAL\Downloads\BD_AQUANQA_26.accdb" `
  --output "data\salida"
```

La extracción crea un directorio inmutable bajo `data/salida/snapshots/<campaña>/`, con:

- `access_snapshot.json`;
- los CSV de las 23 tablas;
- conteos, hashes, columnas físicas resueltas, índices, claves y catálogo de consultas de
  Access;
- si DAO está disponible, relaciones declaradas y el SQL de los `QueryDef`; si no está
  disponible, el manifiesto lo declara como `no_disponible` sin fingir que no hay relaciones;
- resumen de versión R09.

Si la copia de Access cambia, su SHA produce un snapshot nuevo. Si es exactamente la misma, se
reutiliza la identidad de fuente y la carga posterior es un no-op.

## Cargar `raw`

Usa el manifiesto explícito de la extracción para evitar confundir campañas o snapshots:

```powershell
node scripts/run.mjs py load `
  --database aquanqa_migracion `
  --mode append-only `
  --manifest "data\salida\snapshots\C2026\<snapshot>\access_snapshot.json"
```

La carga no hace `TRUNCATE`. Registra el snapshot en `raw.source_snapshot`, el control por tabla
en `raw.source_table_snapshot`, los deltas en `raw.source_table_delta` y la bitácora en
`raw.carga_log`.

El Excel de contraste se carga como fuente independiente cuando esté disponible:

```powershell
node scripts/run.mjs py extract --solo m_lotes_maestro --output "data\salida"
node scripts/run.mjs py load --database aquanqa_migracion --solo m_lotes_maestro
```

La ausencia del Excel no impide guardar Access en `raw` ni resolver la identidad primaria para
`core`; solo impide ejecutar la comparación de control entre ambas fuentes.

## Validar y publicar

Después de cargar, obtén el id real y valida antes de publicar:

```powershell
node scripts/run.mjs psql -d aquanqa_migracion -c `
  "SELECT source_snapshot_id, tipo, campania, estado FROM raw.source_snapshot ORDER BY source_snapshot_id"

node scripts/run.mjs py snapshot validate `
  --database aquanqa_migracion `
  --snapshot-id <id-access> --tipo access --campania C2026

node scripts/run.mjs py snapshot promote `
  --database aquanqa_migracion `
  --snapshot-id <id-access> --tipo access --campania C2026 `
  --usuario etl --motivo "Carga validada de Access"
```

Publica de forma análoga el snapshot `xlsx` del maestro. Para revertir una publicación:

```powershell
node scripts/run.mjs py snapshot rollback `
  --database aquanqa_migracion `
  --to-snapshot <id-anterior> `
  --tipo access --campania C2026 `
  --usuario etl --motivo "Rollback por revisión de calidad"
```

Rollback solo agrega un registro de gobierno; no borra filas históricas.

## Modelo, perfilado y aprobación

Antes de construir un destino físico, registra el modelo y perfila el snapshot publicado:

```powershell
node scripts/run.mjs py modelo validate
node scripts/run.mjs py modelo register --database aquanqa_migracion
node scripts/run.mjs py perfil --database aquanqa_migracion --snapshot-id <id-access> --detalle
```

El perfilado guarda conteos, nulos, duplicados, claves candidatas y relaciones en `raw`. Una
relación solo puede aprobarse con una evidencia válida, sin huérfanos ni claves padre
duplicadas, y con usuario/motivo:

```powershell
node scripts/run.mjs py relacion approve --codigo REL_TIME_E01 `
  --database aquanqa_migracion --snapshot-id <id-access> `
  --usuario <usuario> --motivo "Evidencia revisada"
```

Las relaciones de ubicación no se aprueban mientras no exista el mapa de identidad de fundos,
módulos y lotes. Que el modelo tenga 24 relaciones candidatas no obliga a crear 24 FK.

## Avanzar a `core`

Solo cuando Access esté publicado en la BD nueva; el Excel es opcional y queda como control.
Las estructuras se pueden crear sin cargar datos, siempre fijando la base destino:

```powershell
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/preparar_core.sql
node scripts/run.mjs sql 20_core --database aquanqa_migracion
node scripts/run.mjs sql 30_stg --database aquanqa_migracion
node scripts/run.mjs sql 40_qua --database aquanqa_migracion
node scripts/run.mjs psql -d aquanqa_migracion -f db/sql/50_carga_core/010_sp_maestros.sql
node scripts/run.mjs psql -d aquanqa_migracion -f db/sql/50_carga_core/020_sp_evaluaciones.sql
node scripts/run.mjs psql -d aquanqa_migracion -f db/sql/50_carga_core/025_sp_bayas.sql
node scripts/run.mjs psql -d aquanqa_migracion -f db/sql/50_carga_core/030_sp_operacion.sql
node scripts/run.mjs psql -d aquanqa_migracion -f db/sql/50_carga_core/040_sp_riego.sql
```

El orden físico no sustituye al orden semántico. Primero se debe ejecutar `preflight`, revisar
`raw.v_migracion_perfil_tabla_ultimo` y abrir el bloque correspondiente; no se debe invocar el
ejecutor monolítico `50_carga_core/090_ejecutar.sql` para adelantar bloques.

La primera carga controlada del maestro se ejecuta con:

```powershell
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/migrar_maestro_lotes.sql
```

Ese script abre una ejecución B01, materializa `M_Lotes` desde Access, carga la ubicación en
`core` y registra el check-to-check del bloque y de la tabla. No vuelve a ejecutar un B01 ya
publicado sobre el mismo snapshot. El resumen se consulta así:

```powershell
node scripts/run.mjs psql -d aquanqa_migracion -c `
  "SELECT migracion_run_id, source_snapshot_id, estado, tablas_migradas, total_tablas_plan,
          tablas_pendientes, tablas_fallidas, porcentaje_migrado
     FROM raw.v_migracion_resumen ORDER BY migracion_run_id DESC"
```

No se debe ejecutar todavía `db/sql/50_carga_core/090_ejecutar.sql`: ese archivo carga todos los
dominios y se utilizará cuando cada bloque haya sido aprobado. Los registros que no se puedan
identificar, los duplicados exactos y las mediciones inválidas no se pierden: se conservan en
`raw` y se explican en `qua.rechazos`.

Los siguientes bloques se ejecutan de forma independiente y en este orden:

```powershell
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/migrar_b02_contexto.sql
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/migrar_b03_fenologia.sql
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/migrar_b04_operacion.sql
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/migrar_b05_pronostico.sql
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/cerrar_b06_raw_only.sql
```

Cada script materializa solo sus fuentes, carga solo sus destinos, registra `raw → stg → core`
o `qua`, y cierra su estado en el ledger. B06 no se publica en `core`: sus cinco fuentes quedan
cerradas como `raw_only` con conteo y justificación.

## Estado de la ejecución C2026

Tras limpiar la base que tenía capas adelantadas, la ejecución del 28 de agosto de 2026 dejó:

- 23 tablas de Access en `raw`: el conteo por tabla queda en `raw.source_table_snapshot`;
- fuente de contraste `M_Lotes.xlsx`: 879 filas;
- snapshot Access cargado, validado y publicado: `1`;
- snapshot Excel cargado y validado de forma independiente: `2` (todavía no publicado);
- carga repetida del mismo manifiesto: 0 duplicados;
- `core`, `stg` y `qua`: estructuras creadas en `aquanqa_migracion`;
- ejecución de migración `1`: `completada_con_observaciones`, con `18/23` fuentes publicadas en
  `core`, `5/23` cerradas como `raw_only`, `0` pendientes y `0` fallidas;
- bloques `B01_IDENTIDAD`, `B02_CONTEXTO`, `B03_FENOLOGIA`, `B04_OPERACION` y
  `B05_PRONOSTICO`: publicados con sus conteos `raw/stg/core/qua` y linaje técnico;
- B03 conserva `E05_Seguimiento` en un grano lógico desancho; B04 unifica H00/H01 en cosecha;
  B05 publica solo R08/R09 vigentes;
- `H01_DetalleCosecha`, `M_PresupuestoMO`, R08 históricos `_24/_25` y R09 histórico `_25`:
  conservados en `raw_only` hasta aprobar su modelo;
- `dim`, `fact`, `reporting`, `analytics` y `mlflow`: no existen en `aquanqa_migracion`;
  la base `aquanqa` del dashboard se mantiene aparte y operativa.

Las alertas funcionales quedan documentadas en `qua.rechazos` y no bloquean una publicación
cuando la regla de negocio permite conservar el dato en core. Los intentos cancelados de B03/B04
se conservan en `raw.migracion_bloque_ejecucion`; no se borran como parte del cierre.

## Comprobaciones obligatorias

```powershell
node scripts/run.mjs py load --database aquanqa_migracion --manifest "<mismo-manifiesto>"
node scripts/run.mjs py snapshot validate --database aquanqa_migracion --snapshot-id <id-access>
node scripts/run.mjs validate-fixture
node scripts/run.mjs psql -d aquanqa_migracion -c `
  "SELECT source_snapshot_id, tipo, campania, estado FROM raw.source_snapshot ORDER BY source_snapshot_id"
node scripts/run.mjs psql -d aquanqa_migracion -c `
  "SELECT * FROM raw.v_migracion_resumen ORDER BY migracion_run_id DESC"
node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/auditoria_final_migracion.sql
node scripts/run.mjs psql -d aquanqa -c `
  "SELECT current_database(), count(*) FROM raw.source_snapshot"
```

El primer comando debe indicar que el snapshot ya estaba cargado y no insertar filas. El último
solo comprueba la base del dashboard; no se debe ejecutar ningún script de migración contra ella.
