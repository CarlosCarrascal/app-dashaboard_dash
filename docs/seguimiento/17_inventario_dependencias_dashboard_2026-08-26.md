# Inventario de dependencias del dashboard — 2026-08-26

## Objetivo y alcance

Este inventario responde a una pregunta concreta: **qué parte del dashboard depende de
PostgreSQL y qué parte sigue dependiendo de Excel o de archivos locales**. Se hizo sobre el
working tree actual, mediante lectura estática del código y contraste con el estado local de
la base. No se ejecutaron cargas, migraciones ni cambios sobre PostgreSQL.

El checkout está en la rama `codex/refactor-analitica`, con `HEAD` corto `1ca2b89`, pero el
working tree tiene cambios sin confirmar tanto en dashboard como en SQL, ETL y analítica. Por
eso, este inventario describe el código que actualmente se está inspeccionando, no únicamente
el commit base.

## Conclusión ejecutiva

El dashboard no tiene una sola fuente:

1. El **panel histórico y de impacto** se construye desde Excel mediante `PANEL_STORE`.
2. La **plataforma analítica** (`/analitica/*`) lee resultados versionados de PostgreSQL y,
   para algunos detalles, archivos Parquet asociados a las corridas.
3. **Proyección** lee PostgreSQL directamente y es la parte más sensible a cambios en
   `analytics`, `reporting`, `stg` y `dim`.
4. **Oleadas Bhattacharya** lee directamente las tablas operativas `core`.
5. Las páginas `/modelo/*` y la proyección legacy solo se exponen cuando se habilita el modo
   legacy.

Por tanto, una carga v2 puede cambiar una parte del dashboard y dejar otra sin cambiar. Eso
explica por qué el tablero puede parecer coherente visualmente aunque sus módulos estén
leyendo versiones distintas de los datos.

## Matriz página por página

| Ruta | Fuente efectiva | Dependencias principales | Sensibilidad |
|---|---|---|---|
| `/` | Excel del panel | `PANEL_STORE`; `IA.final.xlsx`, `M_Poda.xlsx`, `DAtos mes.xlsx` | Baja frente a cambios en PostgreSQL; alta frente a cambios en esos Excel |
| `/datos-calidad` | Excel del panel | `PANEL_STORE` y cálculos de `analitica.nucleo` | Baja frente a PostgreSQL |
| `/impacto/evidencia` | Excel del panel | `PANEL_STORE` y módulos de clima/impacto | Baja frente a PostgreSQL |
| `/impacto/por-modulo` | Excel del panel | `PANEL_STORE` | Baja frente a PostgreSQL |
| `/impacto/frutos-peso` | Excel del panel | `PANEL_STORE` | Baja frente a PostgreSQL |
| `/impacto/descubrimientos` | Contenido estático | No consulta datos | Nula |
| `/metodologia` | Contenido y archivos locales | Catálogo local de referencias | Nula frente a PostgreSQL |
| `/analitica/relaciones` | PostgreSQL + artefactos Parquet | `analytics.*`, vistas `reporting.*`, artefactos de la corrida | Alta |
| `/analitica/descubrimientos` | PostgreSQL | `analytics.evidence_claim` y contrato común analítico | Alta |
| `/analitica/modelo` | PostgreSQL | `analytics.model_decision`, `analytics.metric`, corridas y snapshots | Alta |
| `/analitica/explicacion` | PostgreSQL + artefactos | Estado de corrida, evidencia de variables y artefactos | Alta |
| `/analitica/backtesting` | PostgreSQL | Métricas, predicciones, replay y vistas históricas | Alta |
| `/analitica/trazabilidad` | PostgreSQL | Corridas, snapshots, calidad, ensamblaje, fuentes y artefactos | Muy alta |
| `/analitica/fundamento` | PostgreSQL + catálogo local | Estado de corrida y catálogo científico | Media |
| `/analitica/proyeccion` | PostgreSQL | Releases, predicciones, R09, cosecha real, nowcast y dimensiones | Muy alta |
| `/analitica/bhattacharya` | PostgreSQL `core` | Cosecha, poda, campaña, lote, módulo, fundo y turno | Muy alta |
| `/modelo/*` | Excel del panel | `PANEL_STORE`; solo con `AQUANQA_ENABLE_LEGACY_MODEL=true` | Baja frente a PostgreSQL |
| Proyección legacy | PostgreSQL/Excel según ruta antigua | Código fuera del flujo oficial | No debe considerarse contrato vigente |

## Contratos de datos detectados

### 1. Panel Excel

`apps/dashboard/servicios/carga.py` inicializa el panel desde las rutas configuradas en
`packages/analitica/settings.py`. La configuración por defecto apunta a:

- `docs/data/IA.final.xlsx`;
- `docs/data/M_Poda.xlsx`;
- `docs/data/DAtos mes.xlsx`.

Las páginas que reciben `PANEL_STORE` operan sobre ese objeto en memoria. No leen `raw`,
`stg`, `core` ni `reporting` para construir sus gráficos principales.

### 2. Contrato común de analítica

Las páginas analíticas salvo Proyección y Bhattacharya pasan por
`apps/dashboard/pages/analitica/_comun.py`, que llama a
`apps/dashboard/servicios/analytics.py`. Este servicio abre PostgreSQL con
`settings.postgres_dsn()` y consulta, entre otros, estos objetos:

**Tablas `analytics`:**

- `analytics.forecast_run`;
- `analytics.dataset_snapshot`;
- `analytics.metric`;
- `analytics.prediction`;
- `analytics.artifact`;
- `analytics.projection_scenario`;
- `analytics.quality_result`.

**Vistas y funciones `reporting`:**

- `reporting.trazabilidad_modelo`;
- `reporting.comparacion_modelos_historica`;
- `reporting.curva_historica_modelos`;
- `reporting.validacion_modelo_operativo`;
- `reporting.evidencia_analitica`;
- `reporting.evidencia_features_modelo`;
- `reporting.fuente_operativa_access`;
- `reporting.proyeccion_vigente`;
- `reporting.proyeccion_operativa_detalle`;
- `reporting.proyeccion_operativa_fundo_semana`;
- `reporting.cosecha_real_fundo_semana`.

**Dependencias directas adicionales:**

- `stg.v_h01_cosecha`;
- `dim.lote`.

El servicio también consulta `analytics.artifact.uri` y luego lee los Parquet desde disco.
Una restauración de la base sin restaurar el directorio de artefactos puede dejar las tablas
de trazabilidad disponibles, pero vaciar relaciones, importancia de variables o detalles de
explicabilidad.

### 3. Proyección operativa y replay

`apps/dashboard/servicios/proyeccion.py` es un contrato separado y más expuesto a los cambios
de v2. Consulta directamente:

- `analytics.forecast_run`;
- `analytics.dataset_snapshot`;
- `analytics.model_series_release`;
- `analytics.evaluation_contract`;
- `analytics.prediction`;
- `reporting.proyeccion_operativa_detalle`;
- `reporting.nowcast_cierre_semanal`;
- `reporting.fundo_operativo(...)`;
- `stg.v_r09_forecast`;
- `stg.v_h01_cosecha`;
- `dim.lote`.

Esto significa que cambiar la estructura, filtros o contenido de `stg.v_r09_forecast`,
`analytics.prediction`, `analytics.model_series_release` o las vistas `reporting.proyeccion_*`
puede cambiar o romper la página `/analitica/proyeccion` aunque el panel Excel siga igual.

### 4. Oleadas Bhattacharya

La página `/analitica/bhattacharya` no usa el contrato común de resultados persistidos. Su
servicio consulta directamente:

- `core.op_cosecha`;
- `core.evt_poda`;
- `core.t_campania`;
- `core.m_lote`;
- `core.m_modulo`;
- `core.m_fundo`;
- `core.m_turno`.

Cambios en la resolución de identidad o en la carga de `core` sí pueden cambiar el universo,
los filtros y las curvas que muestra esta página.

## Cómo afecta una carga v2

La cadena más sensible identificada es:

```text
Access v2
  -> raw.r09_forecast_semanal / raw snapshots
  -> raw.v_r09_forecast_semanal_historico
  -> stg.v_r09_forecast
  -> proyección / replay / comparaciones
```

La definición del histórico R09 está en `db/sql/10_raw/060_forecast.sql` y su vista de
staging en `db/sql/30_stg/040_vistas.sql`. Los contratos de resultados y reporting están en:

- `db/sql/80_analytics/010_modelo.sql`;
- `db/sql/80_analytics/020_reporting.sql`;
- `db/sql/80_analytics/030_estado_consistente.sql`.

La clasificación correcta de los cambios es:

- **Cambiar `raw`**: no afecta directamente a la interfaz, pero sí puede afectar todas las
  vistas derivadas cuando se reconstruyen.
- **Cambiar `stg`**: afecta directamente a Proyección, al motor analítico y a cualquier vista
  que lo utilice.
- **Cambiar `core`**: afecta Bhattacharya y los cálculos que se alimentan de entidades
  operativas.
- **Cambiar `analytics`**: afecta las páginas analíticas que consumen resultados persistidos.
- **Cambiar `reporting`**: afecta directamente el contrato visible del dashboard; cambiar
  nombres o columnas es especialmente riesgoso.
- **Cambiar Excel**: afecta el panel histórico/impacto, aunque PostgreSQL no cambie.
- **Cambiar artefactos Parquet**: afecta el detalle de relaciones y explicabilidad, aunque las
  tablas de PostgreSQL permanezcan intactas.

## Capacidad actual del ETL frente a varias versiones y Excel

### Varias bases Access

El ETL puede leer una copia `.accdb` por ejecución y registra en el manifiesto el nombre,
hash, tamaño, fecha de modificación y campaña. La configuración contempla actualmente una
ruta para `C2025` y otra para `C2026`, y permite sobrescribirlas con `ACCESS_DB_PATH`.

Por ejemplo, se puede seleccionar explícitamente `BD_AQUANQA_26_v2.accdb` como fuente de
`C2026`. Sin embargo, el ETL **no escanea una carpeta, no decide automáticamente cuál versión
es la correcta y no combina v1/v2/v3 de una misma campaña**. Una nueva ejecución reemplaza la
foto vigente de `raw`; el histórico especial de R09 sí tiene archivado de snapshots, pero eso
no equivale a conservar todas las tablas Access completas.

La forma segura de trabajar varias versiones es tratarlas como snapshots explícitos:

```text
C2026_v1.accdb → snapshot Access C2026 v1 → candidato
C2026_v2.accdb → snapshot Access C2026 v2 → candidato
C2026_v3.accdb → snapshot Access C2026 v3 → candidato
```

Después se elige una versión publicada por campaña y por fuente. No se deben unir las tres
copias sin una regla, porque R09, cosecha o evaluaciones pueden repetir las mismas filas y
producir duplicados.

### Datos Excel

El ETL no acepta cualquier Excel de forma genérica. Hoy reconoce explícitamente:

- `M_Lotes.xlsx` → `raw.m_lotes_maestro`: maestro vigente de identidad. Se asocia a los
  hechos por la combinación normalizada de fundo, módulo y lote.
- `Query Tareo 2026.xlsx` → `raw.tareo`: fuente opcional de personal. Requiere una columna
  identificable como documento/DNI para poder enlazarla con evaluadores.

El archivo Access también contiene su propia tabla histórica `M_Poda`, que se extrae como una
tabla Access; no debe confundirse con el `M_Poda.xlsx` utilizado por el panel actual.

Otros Excel como `IA.final.xlsx`, `M_Poda.xlsx` y `DAtos mes.xlsx` alimentan actualmente el
panel o cálculos analíticos, pero **no son fuentes externas genéricas del ETL**. Si aparece un
nuevo Excel de cosecha, riego, personal o cualquier otra operación, hay que registrar su
estructura, definir sus claves y crear un extractor y una tabla `raw`/`stg` específicos antes
de asociarlo.

La asociación no debe basarse solo en el nombre del lote. Para hechos agrícolas se necesita,
como mínimo, `fundo + módulo + lote`, y normalmente también campaña y fecha. Para personas se
necesita documento/DNI. Si una fila no encuentra una identidad única, debe quedar en
cuarentena con el motivo, no enlazarse por aproximación silenciosa.

## Riesgos actuales

1. El dashboard consulta `reporting`, pero todavía consulta también `stg`, `dim`, `core` y
   `analytics` directamente. Por eso `reporting` aún no es una frontera completa de
   compatibilidad.
2. El código de dashboard, el SQL de `analytics` y parte de la analítica están sin confirmar
   en Git. La versión que se ejecuta localmente puede no coincidir con la versión desplegada.
3. En la revisión local de la base se observaron diferencias entre los archivos CSV, las
   tablas `raw` y los controles de calidad. En particular, los conteos de flores y estados no
   están alineados, y `qua.fn_validar()` mantiene errores en capas core, reporting y
   reproducibilidad.
4. El histórico R09 v2 es una dependencia real de Proyección, pero que R09 esté cargado no
   significa que el modelo v2 haya sido promovido como modelo operativo. El estado de la
   release y su contrato (`analytics.model_series_release` y
   `analytics.evaluation_contract`) deben decidir qué se muestra.

## Decisión operativa recomendada

Hasta cerrar la migración, tratar la base PostgreSQL actual como **entorno mutable de trabajo**
y no como una fuente certificada del dashboard.

El siguiente procedimiento seguro es:

1. Guardar un snapshot de la base actual y de los artefactos asociados.
2. Registrar el commit, archivos Excel, variables de conexión no secretas y conteos por tabla.
3. Clonar la base para una variante `v2`.
4. Ejecutar allí ETL, controles de calidad y consultas de contrato.
5. Probar cada ruta sensible del dashboard contra esa copia.
6. Promover una versión solamente cuando los resultados y los contratos de columnas coincidan.

La estabilización posterior debe crear vistas explícitas del tipo
`reporting.dashboard_*`. El dashboard debería depender de esas vistas y no de tablas internas
de `stg` o `core`; así, una nueva versión del ETL puede cambiar internamente sin romper la
interfaz.

## Archivos revisados

- `apps/dashboard/app.py`;
- `apps/dashboard/servicios/carga.py`;
- `apps/dashboard/servicios/analytics.py`;
- `apps/dashboard/servicios/proyeccion.py`;
- `apps/dashboard/pages/analitica/_comun.py`;
- `apps/dashboard/pages/analitica/*.py`;
- `packages/analitica/settings.py`;
- `packages/analitica/proyeccion/fuentes.py`;
- `packages/analitica/servicios/servicio_bhattacharya.py`;
- `db/sql/10_raw/060_forecast.sql`;
- `db/sql/30_stg/040_vistas.sql`;
- `db/sql/80_analytics/*.sql`.
