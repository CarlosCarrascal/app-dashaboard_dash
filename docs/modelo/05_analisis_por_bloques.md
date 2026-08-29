# Análisis por bloques: acotar las preguntas a lo que está bien medido

**Fecha:** 2026-08-19 · **Estado:** en ejecución

## Por qué se reorganiza el análisis

El análisis venía tratando todas las variables como si tuvieran la misma calidad de
medición, y no la tienen. El resultado era un techo artificial: ninguna relación superaba
0,35 después de descontar el calendario, y eso se leía como «el cultivo es impredecible»
cuando en realidad era «la medición no da para más».

La prueba llegó al incorporar el packing. Con calibre medido en línea, la relación entre
calibre y peso del fruto sale **0,66** sobre 98 semanas. La misma pregunta, medida con el
censo de bayas de campo —dos fechas en total—, daba 0,26 con seis observaciones.

No es un problema de ruido aleatorio sino de **estructura de medición**, y cada limitación
tiene una consecuencia concreta sobre qué unidad de análisis es legítima:

| Limitación medida | Consecuencia |
|---|---|
| Una estación meteorológica para 5 fundos | El clima no varía entre lotes de una misma semana. La unidad real es **semana**, no lote: 181 observaciones independientes, no 30.000 |
| Packing en 15 de 26 módulos, al grano de módulo | No se puede repartir un calibre de módulo entre sus lotes sin inventar variación |
| Censo de bayas: 2 fechas, 36 lotes | Imposible construir series ni desfases a nivel de lote |
| Fenología solo 2026, cosecha 2022–2026 | Sin réplica temporal para validar que una relación se repite |

Forzar un modelo único sobre todo eso produce correlaciones espurias. La alternativa no es
renunciar al análisis: es **declarar la unidad de cada pregunta** y responder solo las que
los datos sostienen.

## Los tres bloques

Cada uno con su unidad, su cobertura y su nivel de confianza declarados.

### Bloque A · Clima → peso

- **Unidad:** semana. El clima es común a todos los fundos.
- **Soporte:** ~181 semanas con clima y cosecha.
- **Uso legítimo:** dirección y magnitud gruesa de la influencia climática.
- **Uso ilegítimo:** ajuste fino por lote, o atribuir a un lote un efecto climático propio.

### Bloque B · Packing → peso y descarte

- **Unidad:** módulo × semana.
- **Cobertura:** 15 de 26 módulos, 3 campañas, 117.536 registros.
- **Uso legítimo:** la mejor descripción disponible del tamaño de fruto y de la pérdida por
  calidad. Es el núcleo duro del análisis del peso.
- **Uso ilegítimo:** extrapolar a los 11 módulos sin packing.

### Bloque C · Fenología → componentes del rendimiento

- **Unidad:** lote × semana.
- **Cobertura:** hasta ahora solo 2026. **Con la carga de 2025 pasa a dos campañas**, que es
  lo que permite comprobar si una relación se repite entre años.
- **Uso legítimo:** explorar qué anticipa la carga, con la advertencia de cuántas campañas
  la sostienen.
- **Uso ilegítimo:** tratar como establecido lo que solo se vio en un año.

## Qué se ejecuta

### 1. Cargar la campaña 2025 de fenología

`BD_AQUANQA_25_v2.accdb` contiene censos que no están en la base:

| Tabla | Cargado hoy (BD_26) | En BD_25_v2 | Rango de la v2 |
|---|---:|---:|---|
| `E02_ConteoFlores` | 43.490 | **49.567** | 2025-02-11 → 2026-02-19 |
| `E03_ConteoEstados` | 18.714 | **41.479** | 2025-03-18 → 2026-03-02 |
| `E01_Ramas` | 94.236 | 87.913 | 2024-12-18 → 2026-02-23 |
| `H02_Cosecha2025` | — | 6.915 | desglose de entierro, descarte y exportable |

El ETL existente (`etl/src/aquanqa_etl/extract/access.py`) ya sabe leer Access en solo
lectura y hay driver ODBC disponible. La carga apunta a `raw` y sube por `stg` sin tocar el
contrato: `raw` copia tal cual, `stg` normaliza y tipa.

**Criterio de solape:** las dos bases comparten fechas de 2026. Se cargan en tablas `raw`
separadas por origen y `stg` deduplica por la clave natural del censo, conservando el
registro de la base más reciente. Sin esa deduplicación, un censo contado dos veces
inflaría los conteos por planta.

### 2. Reorganizar el módulo de Relaciones por bloques

Cada bloque en su propia sección, con una cabecera que declara unidad, cobertura y
confianza. El lector debe poder responder «¿a qué parte de la operación aplica esto?» sin
preguntar.

### 3. Declarar la base y el esquema en la interfaz

La página de trazabilidad ya lista las fuentes; se añade de qué base y esquema salen, para
que quede explícito que el análisis corre sobre PostgreSQL y no sobre los Access de origen.

## Lo que este plan deja explícitamente fuera

- **Afirmaciones causales.** El manejo responde al estado del cultivo: si se riega más
  cuando el lote viene flojo, el riego aparecerá asociado a peor resultado por mucho que la
  correlación sea alta. Solo un ensayo con tratamientos asignados resuelve eso.
- **Series de bayas y brotes con desfases largos.** Dos y 2,1 evaluaciones por lote no dan
  para una serie temporal.
- **Nutrición, polinización, suelo y sanidad.** No existen en ninguna tabla.

## Verificación

1. Los censos de 2025 aparecen en `stg` con sus fechas correctas y sin duplicar 2026.
2. El panel de relaciones muestra tres bloques, cada uno con su unidad declarada.
3. Las relaciones de fenología declaran sobre cuántas campañas se sostienen.
4. `pytest` completo en verde.
