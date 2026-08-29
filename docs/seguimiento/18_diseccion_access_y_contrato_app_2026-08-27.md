# Disección de Access y contrato inicial para la app — 2026-08-27

## Alcance

Este documento separa tres cosas que en Access están mezcladas:

1. tablas de captura y maestros que pueden alimentar la aplicación;
2. históricos operativos que deben migrarse para trazabilidad y análisis;
3. consultas guardadas y resultados derivados que no deben convertirse automáticamente en tablas.

La inspección de `C:\Users\CCARRASCAL\Downloads\BD_AQUANQA_26.accdb` fue de solo lectura. No se cargó este archivo en PostgreSQL ni se modificó la base que consume el dashboard.

## Hallazgo principal

El archivo vigente tiene 23 tablas locales y aproximadamente 51 consultas guardadas. El catálogo actual del ETL solo conoce 18 tablas Access. Además, los conteos de varias tablas cambiaron respecto a las cifras históricas del catálogo.

Por eso el primer problema no es “cargar más rápido”: es reconciliar el catálogo del ETL con el contrato real de la fuente. Si se ejecuta el ETL actual sin esa reconciliación, puede ocurrir cualquiera de estas situaciones:

- omitir tablas nuevas;
- rechazar el archivo por desviación de filas;
- cargar columnas con una estructura antigua;
- reemplazar `raw` con una fotografía parcial;
- confundir una nueva versión de la misma campaña con otra fuente;
- preservar la ausencia de claves y relaciones de Access en PostgreSQL.

Algunas diferencias cuantitativas relevantes frente al catálogo actual son `E02_ConteoFlores` (54.099 frente a 43.490 esperadas), `E03_ConteoEstados` (24.001 frente a 18.714), `H02_BDElifab` (142.413 frente a 117.536), `R08_Forecast_Campaña` (117.593 frente a 101.715) y `M_Evaluadores` (40 frente a 31). No deben aceptarse con `--allow-row-drift` sin explicar primero qué cambió.

## Inventario del Access vigente

| Grupo | Tablas principales | Observación |
|---|---|---|
| Captura fenológica | `E01_Ramas`, `E02_ConteoFlores`, `E03_ConteoEstados`, `E04_Brotes`, `E05_DiametrosBayas`, `E05_Seguimiento` | Núcleo para la aplicación y el análisis agronómico. |
| Maestros/contexto | `M_Evaluadores`, `M_Lotes`, `M_nMuestra`, `M_Poda`, `M_Time`, equivalencia | Permiten resolver persona, ubicación, campaña y muestreo. |
| Cosecha/packing/clima | `H00_VolumenCampo`, `H01_Detalle_Cosecha`, `H01_ProdHistorica`, `H02_BDElifab`, `H05_Clima` | Histórico y fuentes para análisis posteriores. |
| Forecast/presupuesto | `R08_*`, `R09_*`, presupuesto de MO | Fuentes de reportes y proyecciones; algunas variantes son de años anteriores. |
| Consultas guardadas | `0101_*`, `0201_*`, `0301_*`, `0401_*`, `0501_*`, `BI*`, `H*`, `R*`, `S*`, etc. | Son lógica derivada/reportes, no tablas fuente. Varias referencias están rotas o desactualizadas. |

Tablas detectadas que no están en el catálogo ETL actual:

- `E05_Seguimiento`;
- `H01_Detalle_Cosecha`;
- tabla de presupuesto de mano de obra (`M_PresupuestoMO`/nombre ortográfico equivalente en la copia);
- `R08_Forecast_Campaña_24`;
- `R08_Forecast_Campaña_25`;
- `R09_Forecast_Semanal_25`.

También se observó que no todas las consultas guardadas son ejecutables: hay referencias a objetos inexistentes, nombres de columnas antiguos y consultas que Access interpreta como parámetros. Deben tratarse como lógica a revisar, no como evidencia de un modelo relacional correcto.

## Tablas de Access que corresponden a la app

| Pantalla/módulo | Origen Access | Estado del encaje |
|---|---|---|
| Conteo de ramas | `E01_Ramas` | Encaja. El origen repite datos de contexto por cada rama; en PostgreSQL ya se separó cabecera por planta y detalle por rama. |
| Conteo de flores | `E02_ConteoFlores` | Encaja en flores, cuajo, YA y YP. Hay campos del origen adicionales (`YMuertas`, `BrtTiernos`, `Des1`) que deben conservarse en `raw` aunque no todos estén aún en `core`. |
| Conteo de estados | `E03_ConteoEstados` | Encaja en E1–E5 y total. `total` debe recalcularse en PostgreSQL y conservar `Total` de Access como valor auditable. |
| Conteo de brotes | `E04_Brotes` | Encaja. La fecha debe formar parte de la identidad para permitir varias evaluaciones de una misma planta. |
| Crecimiento/madurez de baya | `E05_Seguimiento` | Es el origen más cercano: contiene `D01..D25` y `E01..E25`, que una consulta Access convierte en posiciones de fruto. Debe normalizarse en PostgreSQL. |
| Diámetro de baya | `E05_DiametrosBayas` | Encaja para diámetro agregado por muestra, pero no identifica planta ni fruto individual. No debe confundirse con `E05_Seguimiento`. |
| Peso de baya | No existe un encaje directo | `E05_Seguimiento` solo tiene diámetros y estados; `E05_DiametrosBayas` solo tiene diámetro. El peso de campo de la pantalla requiere una nueva medición o confirmar otro origen. `H02_BDElifab` es peso de packing, no peso de baya de campo. |
| Evaluador y unidad asignada | `M_Evaluadores`, `M_Lotes`, `M_nMuestra`, `M_Poda`, `M_Time` | Son tablas de apoyo. La unidad debe resolverse por ubicación/campaña y no por texto libre aislado. |

### Decisión de diseño para la app

La app no debería escribir directamente en una tabla ancha heredada de Access. El contrato debe tener:

- una cabecera de evaluación: tipo, fecha, evaluador, lote/unidad, estado de sincronización y timestamps;
- un detalle según el tipo de evaluación: métricas por planta, rama o fruto;
- una identidad técnica de captura y una clave idempotente;
- trazabilidad de origen para distinguir una captura móvil de una fila migrada desde Access.

El modelo actual ya contiene una buena base para cuatro módulos:

- `core.ev_evaluacion_ramas` + `core.ev_rama_medicion`;
- `core.ev_flores`;
- `core.ev_estados`;
- `core.ev_brotes`;
- `core.ev_baya_medicion` para diámetro.

`E05_Seguimiento` requiere una tabla normalizada adicional o una ampliación explícita del modelo de bayas. La estructura recomendada es una fila por fruto y evaluación, no 25 pares de columnas repetidas. Debe verificarse además la diferencia entre la pantalla que muestra 25/50 frutos y el Access que almacena 25 posiciones por fila; puede tratarse de dos bloques de 25, pero no debe asumirse en silencio.

## Relaciones: qué existe y qué debe construirse

Access no ofrece claves foráneas de negocio confiables en esta copia. Las relaciones se deducen de las consultas y de los valores:

```text
evaluación.Evaluador             -> M_Evaluadores.DNI
evaluación.Fundo/Modulo/Lote     -> M_Lotes.FundoPPto/Modulo/Lote
evaluación.Fecha                 -> M_Time.Fecha
evaluación + ubicación           -> M_nMuestra
ubicación + campaña              -> M_Poda / calendario operativo
```

En PostgreSQL estas asociaciones deben quedar como reglas explícitas:

- resolver el lote mediante una clave normalizada `(fundo, modulo, lote)` y, cuando corresponda, campaña/turno;
- resolver evaluadores por DNI, no por el código `Cod`;
- dejar en cuarentena las filas con identidad inexistente o ambigua;
- no asociar por “parecido” ni por nombre de lote aislado;
- conservar el valor original y la versión de la regla usada para resolverlo.

## Revisión del ETL actual

| Capacidad | Estado actual | Implicación |
|---|---|---|
| Una copia Access por ejecución | Sí | Puede procesar manualmente `C2026`, pero no descubre versiones por carpeta. |
| C2025/C2026 | Parcial | Hay una ruta configurada por campaña; no hay consolidación general de fuentes. |
| `v1`, `v2`, `v3` | No | El texto del nombre no se interpreta como versión funcional. |
| Hash del archivo y manifiesto | Sí, parcial | Es una buena base de trazabilidad, pero el manifiesto y CSV actuales se sobrescriben. |
| Evitar duplicación al repetir la carga | Sí por `TRUNCATE` | Es idempotente para una foto, pero no conserva histórico completo ni hace incremental real. |
| Carga incremental | No | La carga reemplaza cada tabla `raw` completa. |
| Excel | Parcial | Solo están declarados `M_Lotes.xlsx` y `Query Tareo 2026.xlsx`; no es un cargador genérico. |
| Diferenciar filas modificadas | No plenamente | Sin claves estables, una edición parece una baja y un alta; no se puede afirmar cuál fue modificada. |

El `TRUNCATE` no es malo por sí mismo: sirve para reconstruir una fotografía candidata de forma repetible. Lo peligroso es usarlo como si fuera histórico y compartirlo con una base que también sostiene al dashboard.

## Diseño recomendado para versiones Access y Excel

### 1. Cada archivo es un snapshot explícito

Un archivo no debe identificarse por su nombre solamente. Cada extracción debe registrar:

```text
tipo_fuente       = access | xlsx
campania          = C2026
version_fuente    = v2 (declarada o detectada, nunca inferida solo del nombre)
sha256            = hash del archivo completo
modificado_en     = fecha del archivo
extraido_en       = fecha de lectura
tabla/hoja        = objeto extraído
estado            = candidato | validado | publicado | rechazado
```

La salida debe ser inmutable por ejecución, por ejemplo:

```text
data/salida/snapshots/C2026/2026-08-27_<sha256>/
  manifest.json
  e01_ramas.csv
  e05_seguimiento.csv
  ...
```

El `load` debe leer únicamente los archivos enumerados en ese `manifest.json`, no todos los CSV que encuentre en una carpeta compartida.

### 2. La política de versiones debe elegir, no mezclar

Para `C2026_v1`, `C2026_v2` y `C2026_v3`:

1. extraer cada archivo como snapshot separado;
2. comparar conteos, columnas, rangos de fechas, hashes y claves candidatas;
3. validar cada snapshot en la base candidata;
4. declarar uno como publicado para la campaña;
5. conservar los demás como histórico/auditable.

No se deben unir tres copias completas sin una regla de precedencia. Una copia posterior puede contener correcciones, pero también puede contener filas repetidas de la copia anterior.

### 3. Deduplicación por capa

La deduplicación debe distinguir:

- **duplicado físico:** misma fila, misma fuente, misma clave de contenido;
- **corrección:** misma identidad de negocio, valores distintos;
- **repetición legítima:** misma ubicación en otra fecha, turno o evaluación;
- **conflicto:** misma identidad de negocio con dos valores incompatibles.

La huella de fila sirve para detectar contenido idéntico, pero no reemplaza una clave de negocio. Para las evaluaciones, la clave debe incluir como mínimo:

```text
campaña + tipo_evaluación + fecha + evaluador + fundo/modulo/lote
+ cortina + hilera + planta + número_de_muestra
```

La clave exacta debe variar por grano: una rama, una planta, una baya y un conteo agregado no son la misma entidad.

### 4. Excel asociado

Un Excel adicional sí puede asociarse, pero no automáticamente por aparecer en una carpeta. Para cada Excel se debe declarar un adaptador con:

- archivo y hoja;
- columnas de origen y destino;
- tipos y conversiones;
- claves de asociación;
- prioridad frente a Access;
- reglas de cuarentena.

Reglas iniciales:

- lotes: `(fundo, modulo, lote)` normalizados, con campaña/turno cuando sea necesario;
- personas: DNI/documento;
- operación: fecha + ubicación + actividad, según su grano real.

Las filas no resueltas o ambiguas deben quedar disponibles para revisión, no descartarse ni asociarse por aproximación.

## Alcance de la primera implementación

La primera implementación debe concentrarse en una base candidata separada y en estas fuentes:

1. `M_Lotes` y `M_Evaluadores` como maestros de identidad, dejando clara la precedencia frente a los Excel vigentes;
2. `M_nMuestra`, `M_Time` y `M_Poda` como contexto;
3. `E01_Ramas`;
4. `E02_ConteoFlores`;
5. `E03_ConteoEstados`;
6. `E04_Brotes`;
7. `E05_Seguimiento`;
8. `E05_DiametrosBayas`.

Después se incorporan las tablas de cosecha, clima, packing, forecasts y presupuesto, siempre con su grano y contrato definidos. Las consultas guardadas se recrean como vistas PostgreSQL solo cuando exista una necesidad concreta y la lógica haya sido validada.

## Recomendación final

La idea de empezar por lo que necesita la app es correcta, siempre que no se convierta en una migración parcial sin trazabilidad. La ruta segura es:

```text
Access vigente
  -> snapshot inmutable
  -> raw completo del snapshot
  -> stg normalizado y con cuarentena
  -> core de app con claves y relaciones
  -> validación
  -> publicación independiente
```

La base PostgreSQL actual debe permanecer operativa para el dashboard mientras esto se valida. No se debe usar la base actual como laboratorio ni “calzar” las tablas nuevas sobre ella. La siguiente modificación de código debe ser del ETL y del catálogo de fuentes, no del dashboard: incluir las tablas faltantes, congelar cada snapshot, registrar Excel y hacer que la carga sea atómica y gobernada por manifiesto.
