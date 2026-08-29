# Orquestador de refresco Access

## Alcance

Este flujo opera únicamente sobre `aquanqa_migracion`. La base `aquanqa` queda fuera de
alcance y continúa disponible para el dashboard existente.

El orquestador no mezcla el Excel de contraste ni los datos de la aplicación móvil con
Access. El Excel puede seguir comparándose con `M_Lotes`, pero no se carga automáticamente
como parte de este refresco.

## Flujo controlado

1. Extraer la copia Access completa en un snapshot identificado por SHA-256.
2. Cargar solo las 23 tablas Access a `raw` en modo append-only.
3. Repetir la misma copia es idempotente: el SHA y el snapshot existente impiden duplicar.
4. Validar conteos, hashes, catálogo técnico y controles de tabla.
5. Comparar `raw.source_table_delta` y `schema_hash` contra el snapshot Access publicado.
6. Calcular el bloque directo y el cierre de dependencias del modelo vigente.
7. Publicar y ejecutar core únicamente cuando la autorización y la estrategia de refresco son
   compatibles con el estado físico actual.
8. Cerrar con preflight, linaje, cuarentena y auditoría final.

## Comandos

Planificar sin modificar PostgreSQL:

```powershell
node scripts/run.mjs py refresh plan `
  --database aquanqa_migracion `
  --campania C2026 `
  --json `
  --output data/salida/refresh_plan.json
```

Recargar una copia Access, validar y dejarla sin publicar si afecta core:

```powershell
node scripts/run.mjs py refresh run `
  --database aquanqa_migracion `
  --campania C2026 `
  --access-path C:/ruta/BD_AQUANQA_26.accdb
```

La salida anterior es intencionalmente detenida cuando hay cambios para `core`: deja el
snapshot cargado y validado en `raw`, pero no cambia la vista vigente.

Para autorizar un refresco completo del core actualmente poblado:

```powershell
node scripts/run.mjs py refresh run `
  --database aquanqa_migracion `
  --campania C2026 `
  --access-path C:/ruta/BD_AQUANQA_26.accdb `
  --promote `
  --execute-core `
  --allow-full-core-rebuild `
  --usuario etl `
  --motivo "Refresco operativo C2026"
```

## Por qué puede reconstruir todos los bloques

El core actual no está versionado por snapshot y los procedimientos físicos de B01–B05
reconstruyen tablas con `TRUNCATE`/`DELETE`, además de protegerse contra la existencia de
hechos dependientes. Por eso el plan muestra dos listas:

- `bloques_requeridos`: mínimo semántico según el cambio y sus dependencias;
- `bloques_ejecucion`: lo que realmente puede ejecutarse de forma segura con la arquitectura
  actual.

Si el core ya tiene datos y cambia una fuente core, `bloques_ejecucion` es B01 → B05 dentro
de una sola transacción. No se simula un incremental selectivo que pueda dejar maestros y
hechos de snapshots diferentes.

Antes de publicar se crea un `pg_dump` y un baseline. Si preflight, algún bloque o la
auditoría falla, la transacción del core se revierte y el orquestador registra rollback al
snapshot anterior. La restauración manual del dump queda como contingencia adicional.

## Criterios de aceptación

- `aquanqa_migracion` es la base efectiva de la conexión.
- El snapshot Access está validado y contiene las 23 tablas.
- La recarga del mismo SHA produce cero filas nuevas.
- No existen tablas modificadas fuera del modelo aprobado.
- Para core, todos los bloques se ejecutan en orden y la auditoría final cierra el run.
- Las fuentes `raw_only` se conservan en raw y no inventan destinos core.
- `aquanqa` no aparece en ninguna operación de carga o reconstrucción.
