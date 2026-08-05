# Lógica de negocio · BD_AQUANQA_26

**Fecha:** 2026-08-02
**Propósito:** explicar **por qué** existe cada objeto de la base, no solo qué contiene.
**Para:** Agronomía, analistas de datos, área de Reportes.

Este documento acompaña a `01_AUDITORIA.md`. Aquel describe el estado técnico; este
describe el significado agronómico y comercial. Cada una de las 40 consultas está explicada
individualmente en §4.

---

## 1 · El proceso agrícola y cómo se refleja en la base

Aqu Anqa produce arándano en 829,02 hectáreas repartidas en 860 lotes, con 4.711.564
plantas. La base cubre cinco campañas: C2022 a C2026.

El arándano es un cultivo **perenne de cosecha escalonada**. Esto determina toda la
estructura de datos, y conviene entenderlo antes de leer cualquier consulta:

**1 · La planta se poda y reinicia su ciclo cada campaña.** La fecha de poda
(`M_Poda.FInicio`) es el origen del tiempo agronómico. Dos lotes podados con un mes de
diferencia están en estados distintos en la misma fecha calendario. Por eso el análisis
serio no usa fechas absolutas sino días desde poda.

**2 · El fruto no madura de golpe.** En una misma planta conviven frutos en cinco estados
de madurez (E1 a E5). La distribución entre esos estados es lo que permite predecir cuándo
habrá cosecha y de qué volumen.

**3 · La cosecha se hace en varias pasadas.** No se cosecha el lote entero de una vez, sino
que se pasa varias veces recogiendo lo maduro. Cada pasada es una "paña"
(`H01_ProdHistorica.Paña`, `R09_Forecast_Semanal.Pasada`).

**4 · El calibre determina el precio.** La fruta se clasifica por diámetro (12mm a 26mm+) y
ese calibre define a qué mercado va: China y USA pagan más, "ácido" va a industria,
"descarte" es pérdida. Predecir el calibre con anticipación tiene valor comercial directo.

**5 · No se puede medir todo, se muestrea.** Se evalúan plantas individuales
(cortina/hilera/planta) y se extrapola al lote. De ahí que exista `M_nMuestra`, que define
cuántas muestras corresponden por lote.

### Las tres preguntas que la base intenta responder

| Pregunta | Objetos que la responden |
|---|---|
| **¿Cuánto voy a cosechar y cuándo?** | `E02`→`E03`→`0302_ConteoAjustado`, familia `R08`/`R09` |
| **¿Cuánto cosechó realmente?** | `H00`, `H01`, familia `H01xx` |
| **¿Qué calidad y a qué mercado fue?** | `H02_BDElifab`, `H0201_PesoBaya_Elifab` |

Y una cuarta que **la base podría responder y hoy no responde**: ¿el calibre que se midió
en campo predijo el calibre de packing? Los datos existen (`E05_DiametrosBayas` y
`H02_BDElifab`) pero no están conectados — ver H-12.

---

## 2 · Glosario

### Unidades físicas y de gestión

| Término | Significado |
|---|---|
| **Fundo** | Unidad geográfica mayor. **Se nombra de 4 formas incompatibles** — ver H-01. Los nombres quechua (Kawsay Allpa, Ayllu Allpa, Quri Allpa, Arena Azul) son los reales; `Aqu Anqa`/`Aqu Anqa II` son agrupaciones presupuestales |
| **Módulo** | Subdivisión del fundo. 23 módulos (`M01`–`M13`, con variantes `M10A`/`M10B`) |
| **Turno** | Agrupamiento de gestión (riego o labor) dentro del módulo. **No es una unidad física.** Solo `M_Lotes`, `H01` y `E05` lo traen de origen |
| **Lote** | Unidad de gestión productiva. 860 registros, 855 combinaciones distintas de `(Modulo, Lote)` |
| **Cortina** | Subdivisión física del lote. En arándano suele corresponder a una sección delimitada por cortavientos |
| **Hilera** | Línea de plantas dentro de la cortina |
| **Planta** | Individuo. Grano de todas las evaluaciones fenológicas |
| **Piso** | Nivel dentro de la planta (solo en `E04_Brotes`) |

### Términos fenológicos

| Término | Significado | Dónde aparece |
|---|---|---|
| **Poda** | Corte que reinicia el ciclo productivo. `FInicio` es su fecha | `M_Poda` |
| **Brote** | Crecimiento nuevo tras la poda. Primera evaluación del ciclo | `E04_Brotes.Brotes` |
| **Rama** | Estructura leñosa. Se clasifica en `<5` y `>5` mm de diámetro — las mayores a 5 mm son las productivas | `E01_Ramas` |
| **Yema abierta (YA)** | Yema que ya abrió y dará flor | `E02_ConteoFlores.YA` |
| **Yema por abrir (YP)** | Yema aún cerrada. `YA + YP` es el potencial floral pendiente | `E02_ConteoFlores.YP` |
| **Cuajo** | Flor que fue fecundada y se convertirá en fruto. **La tasa de cuajo es el principal predictor de producción** | `E02_ConteoFlores.Cuajo` |
| **Estados E1–E5** | Los cinco estados de madurez del fruto, de verde (E1) a listo para cosecha (E5) | `E03_ConteoEstados` |
| **Diámetro de baya** | Calibre del fruto en mm. Determina el mercado de destino | `E05_DiametrosBayas`, `H02.Calibre` |
| **Paña / Pasada** | Número de pasada de cosecha sobre el mismo lote | `H01.Paña`, `R09.Pasada` |

### Términos de la base (no agronómicos)

| Término | Significado |
|---|---|
| **`KeyMap`** | Clave de ubicación en el mapa del fundo. Formato `<algo>L<lote>`. 53 lotes de 860 la tienen nula |
| **`kk`** | Prefijo de `KeyMap` hasta la letra `L` — se calcula con `left(KeyMap, InStr(1,KeyMap,"L")-1)`. Identifica el bloque de mapa |
| **`Sem`** | Semana calendario |
| **`SEvConteo`** | **Semana de evaluación de conteo.** Distinta de `Sem`: el corte de evaluación agronómica no cae en domingo. Difieren en **527 días** de 1.224 poblados |
| **`Campaña`** | Ciclo productivo anual: `C2022` a `C2026` |
| **`Version`** | Identifica un escenario de proyección. En `R08` son nombres (`Proy_Mayo`); en `R09` son códigos de semana (`S01`–`S32`) |
| **`Fundo_pptom5`** | "Fundo presupuesto módulo 5" — el vocabulario C de fundo |
| **`FundoPPto`** | "Fundo presupuesto" — el vocabulario B |

### Por qué `SEvConteo` merece atención especial

Es el concepto más sutil de la base y la causa de un defecto crítico (H-05).

La semana calendario (`Sem`) va de domingo a sábado. Pero la evaluación agronómica de campo
tiene su propio corte semanal, que **no coincide** — probablemente porque las cuadrillas
evalúan en un ciclo fijo que empezó en un día distinto. `SEvConteo` codifica esa semana
desplazada.

| Métrica | Valor |
|---|---|
| Días con `SEvConteo` poblado | 1.224 de 2.189 |
| Rango | 1 a 53 |
| **Días donde `Sem <> SEvConteo`** | **527** |

**El error que produce.** `SEvConteo` es un número de semana (1–53) que se repite en todos
los días de esa semana. Unir una tabla semanal contra `M_Time` por `SEvConteo` produce
tantas filas como días tenga la semana. Eso es exactamente lo que hace `01_Flores_C2025`, y
por eso devuelve 487.368 filas en vez de 9.040.

---

## 3 · Cálculos de negocio documentados

Fórmulas que aparecen en las consultas y su significado agronómico.

### `pE1..pE5` — distribución de madurez normalizada

```sql
pE1 = SUM(E1) / (SUM(E1)+SUM(E2)+SUM(E3)+SUM(E4)+SUM(E5))
```
*(en `0302_ConteoAjustado`, repetido para los 5 estados)*

**Por qué se normaliza.** Los evaluadores no muestrean la misma cantidad de plantas por
lote. Un lote con 40 plantas evaluadas y otro con 10 no son comparables en conteo absoluto:
el primero pesaría cuatro veces más en cualquier promedio, sin que eso refleje nada
agronómico.

Convertir a proporciones hace comparables lotes con esfuerzo de muestreo distinto. **La
distribución `pE1..pE5` es el indicador de avance de madurez**: si `pE5` sube, la cosecha
está cerca; si `pE1` domina, faltan semanas.

### `FrutosxPl` — frutos por planta

```sql
FrutosxPl = SUM(Total) / COUNT(Planta)
```
*(en `0302_ConteoAjustado`)*

Normaliza el conteo total por número de plantas evaluadas. Junto con `M_Lotes.NPlantas`
permite extrapolar del muestreo al lote completo.

### `KG / Peso * 1000` — frutos totales estimados

```sql
FrutosTotal = KG / Peso * 1000
```
*(patrón en la familia `R09xx` y `H0201`)*

`Peso` es el peso unitario de baya **en gramos**; `KG` son kilos. La división da el número
de frutos, y el `*1000` convierte kg a gramos. Es la conversión entre la medida comercial
(kilos) y la medida agronómica (frutos), necesaria porque la evaluación de campo cuenta
frutos y la venta se hace por peso.

### `CDate(Round(Avg(Fecha),0))` — fecha representativa del grupo

```sql
CDate(Round(Avg([0201_Flores].Fecha),0)) AS Fecha
```
*(en `0202_FloresTurno` y `0302_ConteoAjustado`)*

Access almacena las fechas como números. Promediarlas y redondear da la **fecha central del
grupo** — útil cuando se agrupa por semana y se quiere una fecha representativa en lugar del
mínimo o el máximo.

Es correcto pero frágil: depende de la representación numérica interna de la fecha. En
PostgreSQL el equivalente explícito sería trabajar sobre el epoch y volver a convertir.

### `Edad = (Now() - FSiembra) / 365`

*(en `M_EdadCultivo`)*

Edad de la plantación en años. **Es un cálculo dependiente de la fecha de ejecución**: el
resultado cambia cada día que pasa. Esto tiene una consecuencia práctica importante — una
captura de pantalla del tablero de hace seis meses no es reproducible hoy. En el modelo
destino conviene exponer `FSiembra` y calcular la edad en la capa de presentación.

### `Int(Right(Left(Version,3),2))` — extracción de la semana de la versión

*(en `R0901_Forecas_SemAc`)*

`Left(Version,3)` toma `S01` de `S01_v2`; `Right(...,2)` toma `01`; `Int` lo vuelve número.
Sirve para quedarse con la proyección vigente de cada semana.

**Es frágil.** Depende de que el código de versión tenga siempre exactamente esa forma. Si
alguien escribe `S1` en vez de `S01`, el parseo devuelve un valor incorrecto sin error. En
PostgreSQL debería ser una columna propia, no un parseo de texto.

### `Right(Fundo,2) & Modulo & Turno` — clave compuesta `Key1`

*(en `0301_ConteoEstados`)*

Construye un identificador concatenando los 2 últimos caracteres del fundo con módulo y
turno. Es un apaño para tener una clave única en ausencia de claves reales (H-02). En el
modelo destino se reemplaza por una clave sustituta.

### `left(KeyMap, InStr(1,KeyMap,"L")-1)` — extracción de `kk`

*(en `0106_RaFloYem`)*

Toma la parte de `KeyMap` anterior a la letra `L`. Identifica el bloque de mapa. Falla
silenciosamente si `KeyMap` es nulo — y **53 lotes lo tienen nulo**.

---

## 4 · Las 40 consultas, una por una

Cada consulta se explica con la misma estructura: **qué hace**, **por qué existe**, **cálculo
aplicado** (cuando lo hay), **qué se obtiene**, **alimenta a** y **estado**.

Las 40 se agrupan en 7 familias:

| Familia | Consultas | Propósito |
|---|---|---|
| `01xx`–`02xx` | 11 | Evaluaciones de ramas, flores y yemas |
| `03xx` | 7 | Estados de madurez del fruto |
| `04xx` | 2 | Estados a nivel de planta |
| `H01xx` | 6 | Cosecha real |
| `H02xx`, `H05xx` | 3 | Packing y clima |
| `R08xx`, `R09xx` | 7 | Forecast y comparación contra real |
| `M_xxx`, otros | 4 | Utilitarias de dimensión |

---

### Familia `01xx` – `02xx` · Evaluaciones de ramas, flores y yemas

---

#### `0101_Diametros`

**Qué hace.** Toma las 94.236 evaluaciones de `E01_Ramas` y les añade el `Turno` y el
`KeyMap` desde el maestro de lotes.

**Por qué existe.** `E01_Ramas` registra la ubicación física (fundo/módulo/lote/cortina/
hilera/planta) pero no el turno, que es un agrupamiento de gestión. Sin turno no se puede
analizar por unidad de manejo. Esta consulta es la que debería resolver esa carencia.

**Qué se obtiene.** 94.236 filas — todas las evaluaciones con sus atributos de lote.

**Alimenta a.** `0102_CantRamas`, `0106_RaFloYem`, `0108_diam` (y transitivamente
`0305_Brotes_Ramas`).

**Estado. Defectuosa por H-01.** El `RIGHT JOIN` une `E01_Ramas.Fundo` (vocabulario D:
`Kawsay Allpa`) contra `M_Lotes.FundoPPto` (vocabulario B: `Aqu Anqa II`). El join **nunca
acierta**: las 94.236 filas salen con `Turno`, `KeyMap`, `NPlantas` y `Area` en NULL.

La consulta cumple su función aparente —devuelve todas las filas— pero **falla en su
propósito real**, que era precisamente traer el turno. Es el caso más claro de defecto
silencioso de la base: no hay error, solo columnas vacías.

---

#### `0102_CantRamas`

**Qué hace.** Agrupa `0101_Diametros` por planta y calcula el total de ramas.

**Cálculo.** `TotalRamas = [Ramas <5] + [Ramas >5]`

**Por qué existe.** El conteo se captura separado en ramas finas (<5 mm) y gruesas (>5 mm)
porque son agronómicamente distintas: **las mayores a 5 mm son las que sostienen producción**;
las menores son crecimiento vegetativo. Esta consulta recompone el total sin perder el
desglose.

**Qué se obtiene.** 5.530 filas (agrupadas desde 94.236).

**Alimenta a.** `0106_RaFloYem`.

**Estado.** Hereda el defecto de H-01 (`Turno` NULL) y el sesgo de H-03 (duplicados).

---

#### `0104_PromFlores`

**Qué hace.** Promedia flores, cuajo y yemas por lote y semana.

**Cálculo.** `AVG(Cuajo)`, `AVG(nFlores)`, `AVG(YA)`, `AVG(YP)`, `MIN(Fecha)`

**Por qué existe.** La evaluación se hace planta por planta, pero la decisión agronómica se
toma por lote. Esta consulta es el puente entre el grano de muestreo y el grano de gestión.

**Qué se obtiene.** 9.040 filas — una por lote/semana/año.

**Alimenta a.** `0105_AcumFlores`, `0106_RaFloYem`, `0107_YemasAb`, `01_Flores_C2025`,
`0306_FrutosFlores`, `0307_EstadosFlores`. **Es una de las consultas más reutilizadas de la
base.**

**Estado.** Correcta. Une por `FundoPPto` contra `E02_ConteoFlores.Fundo`, que **también**
usa vocabulario B — este join sí acierta. Advertencia: `Cuajo` es 87,7% nulo, así que
`PromCuajo` se calcula sobre el 12,3% de los datos.

---

#### `0105_AcumFlores`

**Qué hace.** Suma los promedios semanales de flores por lote y año.

**Cálculo.** `SUM(PromFlores)` agrupado por fundo/módulo/lote/año.

**Por qué existe.** Acumular la floración de toda la campaña da el **potencial floral total**
del lote, que es el techo de producción posible.

**Qué se obtiene.** 867 filas.

**Alimenta a.** Nadie — es consulta hoja, consumo final.

**Estado.** Funciona, pero con una advertencia metodológica: **suma promedios**, lo cual no
es un total real de flores sino un acumulado de medias semanales. Es un índice comparable
entre lotes, no una cantidad absoluta. Un tablero que lo etiquete como "total de flores"
estaría induciendo a error.

---

#### `0106_RaFloYem`

**Qué hace.** Unifica en una sola tabla larga tres evaluaciones distintas: ramas, flores y
yemas.

**Cálculo.** `kk = left(KeyMap, InStr(1,KeyMap,"L")-1)` — extrae el bloque de mapa.

**Por qué existe.** Es un **despivote manual** (H-11): tres `SELECT` unidos con `UNION ALL`,
cada uno etiquetando su métrica con un literal (`"Ramas"`, `"Flores"`, `"YemaAb"`). El
resultado es formato largo, que permite a Power BI graficar las tres evaluaciones en un
mismo eje con un solo campo de leyenda.

**Qué se obtiene.** 18.778 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Funciona, pero con dos problemas: es el patrón redundante de H-11, y el cálculo
de `kk` **falla silenciosamente en los 53 lotes con `KeyMap` nulo**.

---

#### `0107_YemasAb`

**Qué hace.** Extrae solo el promedio de yemas abiertas por lote y semana.

**Por qué existe.** Aísla `PromYA` de `0104_PromFlores` con la etiqueta `"YemaAb"`. Es una
de las tres ramas de `0106_RaFloYem`, publicada por separado.

**Qué se obtiene.** 9.029 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Correcta, pero **redundante** (H-11): duplica una rama de `0106_RaFloYem`. Si se
corrige la lógica en una y no en la otra, divergen sin aviso.

Advertencia: `YA` es 72,6% nulo.

---

#### `0108_diam`

**Qué hace.** Extrae el diámetro de corona con año, semana y turno.

**Qué se obtiene.** **0 filas.**

**Estado. Efectivamente rota, aunque no lanza error.** Usa `INNER JOIN` contra `M_Lotes`
sobre el mismo par de vocabularios incompatibles de H-01. Donde `0101_Diametros` usa
`RIGHT JOIN` —y conserva las filas con NULLs—, aquí el `INNER JOIN` las **elimina todas**.

Es el mismo defecto con distinta manifestación, y vale la pena señalarlo: **`INNER JOIN`
hace visible el problema (0 filas), `RIGHT JOIN` lo esconde (94.236 filas con NULLs)**. La
consulta que parece rota es la honesta.

Cualquier tablero que consuma `0108_diam` está vacío hoy.

---

#### `01_Flores_C2025`

**Qué hace.** Cruza el promedio de flores con la fecha de poda y el número de plantas.

**Por qué existe.** Relacionar floración con `M_Poda.FInicio` permite medir el desarrollo en
**días desde poda**, que es la escala agronómicamente correcta.

**Qué se obtiene.** **487.368 filas** desde un origen de 9.040 — un factor de **×54**.

**Alimenta a.** Nadie — consulta hoja. Por el nombre (`C2025`), alimenta un tablero de campaña.

**Estado. Defectuosa por H-05.** La última línea:

```sql
INNER JOIN M_Time ON [0104_PromFlores].Sem = M_Time.SEvConteo
```

une un número de semana contra una tabla de **días**. Cada fila se multiplica por los días
de esa semana.

**Es el defecto más peligroso de la base** porque no se ve: los `AVG` siguen dando el valor
correcto (el promedio de un valor repetido es el mismo valor), solo los `SUM` y los conteos
están inflados ×54. Un tablero puede parecer perfectamente sano y estar reportando medio
millón de evaluaciones donde hubo nueve mil.

---

#### `0201_Flores`

**Qué hace.** Detalle de conteo de flores a nivel de planta, enriquecido con turno, semana,
y fecha de poda. **Filtrado a la campaña C2026.**

**Por qué existe.** Es la versión de detalle —grano de planta— frente a `0104_PromFlores`
que ya viene agregada por lote. Sirve para análisis de dispersión: cuánto varían las plantas
dentro del mismo lote.

**Qué se obtiene.** 43.457 filas.

**Alimenta a.** `0202_FloresTurno` (y transitivamente `0304_ConteoEst_Flo_Turno`).

**Estado.** Correcta. **Advertencia importante:** tiene `WHERE M_Poda.Campaña = "C2026"`
**embebido en el SQL**. El filtro de campaña está fijo en la consulta, no es un parámetro.
Cuando empiece C2027 esta consulta seguirá devolviendo C2026 sin avisar. Todo lo que
descienda de ella hereda el filtro.

---

#### `0202_FloresTurno`

**Qué hace.** Agrega `0201_Flores` a nivel de turno y semana.

**Cálculo.** `AVG(nFlores)` como `Cantidad`, `SUM(nFlores)` como `SumaTotal`,
`COUNT(nFlores)` como `n`, y `CDate(Round(Avg(Fecha),0))` como fecha representativa.
Etiqueta el resultado con el literal `"Flor"` en la columna `Estado`.

**Por qué existe.** Prepara los datos de flores para unirse con los datos de estados de
fruto en `0304_ConteoEst_Flo_Turno`. El literal `"Flor"` es lo que permite esa unión: la
flor se trata como **un estado más** de la cadena fenológica, anterior a E1.

Exponer `n` (el número de evaluaciones) es buena práctica: permite al analista saber sobre
cuántas muestras se calculó cada promedio.

**Qué se obtiene.** 2.648 filas.

**Alimenta a.** `0304_ConteoEst_Flo_Turno`.

**Estado.** Correcta. Hereda el filtro fijo de C2026 de `0201_Flores`.

---

### Familia `03xx` · Estados de madurez del fruto

Es la familia de mayor valor predictivo de la base: convierte conteos de campo en un
indicador de cuándo y cuánto se va a cosechar.

---

#### `0301_ConteoEstados`

**Qué hace.** Enriquece `E03_ConteoEstados` con turno, área, plantas, semana y dos claves
construidas.

**Cálculo.**
```sql
codPlt = "C" & Cortina & "H" & Hilera & "P" & Planta
Key1   = Right(Fundo,2) & Modulo & Turno
```
`codPlt` identifica la planta dentro del lote; `Key1` es un apaño para tener una clave
compuesta en ausencia de claves reales (H-02).

**Por qué existe.** Es la capa base de toda la familia `03xx`: añade a los conteos crudos el
contexto de lote y tiempo que necesitan las agregaciones posteriores.

**Qué se obtiene.** 18.714 filas (el total de `E03_ConteoEstados`).

**Alimenta a.** `0302_ConteoAjustado`, `0306_FrutosFlores`, `0307_EstadosFlores`
(y transitivamente `0303`, `0304`).

**Estado.** Funciona. Usa `RIGHT JOIN` contra `M_Lotes` por `FundoPPto`, y como
`E03_ConteoEstados` **usa vocabulario B**, el join sí acierta aquí. Expone `SEvConteo`, que
es lo que las consultas descendentes usan como semana.

---

#### `0302_ConteoAjustado`

**Qué hace.** Convierte los conteos absolutos de frutos en **proporciones de madurez** por
turno y semana.

**Cálculo.** Los cinco estados normalizados:
```sql
pE1 = SUM(E1) / (SUM(E1)+SUM(E2)+SUM(E3)+SUM(E4)+SUM(E5))
```
más `FrutosxPl = SUM(Total)/COUNT(Planta)` y la fecha representativa
`CDate(Round(Avg(Fecha),0))`.

**Por qué existe.** Esta es **la consulta conceptualmente más importante de la base**, y su
razón de ser merece explicarse bien.

El problema que resuelve: los evaluadores no muestrean el mismo número de plantas en cada
lote. Si el lote A tuvo 40 plantas evaluadas y el lote B solo 10, comparar sus conteos
absolutos no dice nada agronómico — solo dice quién muestreó más.

Al convertir a proporciones, la comparación pasa a ser sobre **la estructura de madurez**,
que sí es comparable: un lote con `pE5 = 0,40` tiene el 40% de su fruto listo,
independientemente de cuántas plantas se hayan revisado.

`FrutosxPl` complementa: da la intensidad (cuántos frutos por planta) que la proporción no
captura. Juntos responden "cuánto hay" y "en qué estado está".

**Qué se obtiene.** 2.802 filas.

**Alimenta a.** `0303_ConteoEstados_Turno`.

**Estado.** Correcta. Es el mejor diseño de la base. Un detalle: expone `n` (número de
plantas evaluadas), lo que permite al analista descartar grupos con muestreo insuficiente.

---

#### `0303_ConteoEstados_Turno`

**Qué hace.** Despivota los cinco estados de `0302_ConteoAjustado` a formato largo.

**Cálculo.** `Cantidad = pE<i> * FrutosxPl` para cada estado i.

**Por qué existe.** Reconstituye la cantidad de frutos por estado a partir de la proporción
y la intensidad. Cinco `SELECT` unidos con `UNION ALL`, cada uno etiquetado `"Est1"` a
`"Est5"`.

El formato largo permite a Power BI graficar la evolución de los cinco estados en un solo
gráfico usando `Estado` como leyenda — imposible en formato ancho sin cinco medidas.

**Qué se obtiene.** 14.010 filas = 2.802 × 5. La multiplicación por 5 aquí **es correcta y
esperada**: es un despivote, no un defecto de join. Contrasta con el ×54 de H-05, que sí lo es.

**Alimenta a.** `0304_ConteoEst_Flo_Turno`.

**Estado.** Correcta, pero es un caso de H-11: en PostgreSQL sería una sola expresión
`LATERAL (VALUES ...)`.

---

#### `0304_ConteoEst_Flo_Turno`

**Qué hace.** Une flores y estados de fruto en una única serie fenológica.

**Por qué existe.** **Es la consulta que materializa la cadena fenológica completa.** Toma
`0202_FloresTurno` (etiquetado `"Flor"`) y `0303_ConteoEstados_Turno` (etiquetado `"Est1"`
a `"Est5"`) y los apila.

El resultado es una serie de seis estados en orden cronológico natural:

```
Flor → Est1 → Est2 → Est3 → Est4 → Est5
```

Esto permite un único gráfico que muestra cómo la población de la planta migra de flor a
fruto maduro a lo largo de la campaña. **Es la vista analítica más valiosa que produce esta
base.**

**Qué se obtiene.** 16.658 filas = 2.648 (flores) + 14.010 (estados).

**Alimenta a.** Nadie — consulta hoja, consumo directo de Power BI.

**Estado.** Correcta. Hereda el filtro fijo de C2026 por la rama de flores — **importante**:
la rama de flores está limitada a C2026 pero la de estados no. En un tablero histórico, las
flores desaparecen antes que los estados.

---

#### `0305_Brotes_Ramas`

**Qué hace.** Unifica brotes (`E04_Brotes`) y ramas gruesas (`E01_Ramas.[Ramas >5]`) en una
sola tabla.

**Por qué existe.** Brotes y ramas son dos etapas consecutivas de la misma estructura: el
brote de este año es la rama del siguiente. Unificarlos permite ver la progresión.

El truco de implementación: la rama de `E01_Ramas` usa el literal `"Ramas"` en la columna
`Piso` —que en `E04_Brotes` es el nivel de la planta— para distinguir el origen.

**Qué se obtiene.** 8.910 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Funciona, con dos advertencias: hereda los duplicados de `E01_Ramas` (H-03), y
mezcla dos granos distintos —`E04_Brotes` no tiene fecha en su clave (H-02)— lo que hace la
serie temporal irregular.

---

#### `0306_FrutosFlores`

**Qué hace.** Apila el conteo de estados y el promedio de flores en formato largo, usando
`SEvConteo` como semana para ambos.

**Por qué existe.** Comparar el conteo de frutos contra el de flores en la misma semana de
evaluación permite estimar la **tasa de conversión flor → fruto**, que es el indicador
directo de cuajo efectivo.

**Qué se obtiene.** 27.754 filas = 18.714 (estados) + 9.040 (flores).

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Funciona. **Detalle metodológico relevante:** la rama de estados usa
`SEvConteo` y la de flores usa `Sem`, ambas etiquetadas como `Semana` en el resultado.

Como `Sem` y `SEvConteo` difieren en 527 días, **las dos ramas no están alineadas en el
tiempo**. Comparar flores contra frutos en la misma "semana" puede estar comparando semanas
distintas. No produce error ni infla filas, pero sesga la conversión calculada.

---

#### `0307_EstadosFlores`

**Qué hace.** Une lado a lado el promedio de flores y el total de frutos por lote y semana.

**Por qué existe.** Versión ancha (una fila con ambas métricas) de lo que `0306_FrutosFlores`
hace en formato largo. Facilita calcular la razón fruto/flor directamente.

**Qué se obtiene.** 16.239 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Funciona. El join incluye `[0104_PromFlores].Sem = [0301_ConteoEstados].SEvConteo`
— une **semana calendario contra semana de evaluación**. Aquí el efecto es distinto al de
H-05: como ambos lados ya están agregados por semana, no hay explosión cartesiana, pero
**el emparejamiento es incorrecto en los casos donde ambas semanas difieren**.

Al ser `LEFT JOIN`, las flores sin correspondencia salen con `Total` NULL. El resultado
(16.239 filas frente a 9.040 de origen) indica que hay múltiples registros de estados por
combinación de flores.

---

### Familia `04xx` · Estados a nivel de planta

---

#### `0401_Estados_planta`

**Qué hace.** Detalle plano de `E03_ConteoEstados` a nivel de planta individual, con año,
semana y turno.

**Por qué existe.** Es la vista de máximo detalle: sin agregación. Sirve para inspección
puntual y para análisis de variabilidad entre plantas del mismo lote.

Detalle de implementación notable: expone `M_Lotes.Fundo` como `Fundo` y
`E03_ConteoEstados.Fundo` como **`Empresa`**. Es un reconocimiento implícito de H-01 — quien
escribió la consulta sabía que los dos campos no significan lo mismo y les dio nombres
distintos en lugar de asumir que eran el mismo dato.

**Qué se obtiene.** 18.714 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Correcta.

---

#### `0402_ConteoBrotes`

**Qué hace.** *(pretende)* Enriquecer el conteo de brotes con año, semana, turno y KeyMap.

**Estado. ROTA — H-04 caso 1.**

| | |
|---|---|
| Referencia rota | `E04_ConteoBrotes` |
| Objeto real | `E04_Brotes` (3.385 filas) |
| Corrección | reemplazar las 14 apariciones del nombre |

Es una corrección puramente mecánica: todas las columnas que la consulta pide existen en
`E04_Brotes`.

Nota adicional: una vez corregida, el join a `M_Lotes` usa `M_Lotes.Fundo` (vocabulario A)
contra `E04_Brotes.Fundo` (vocabulario D) — **seguiría fallando por H-01**. Arreglar el
nombre de la tabla la hace ejecutable, no correcta.

---

### Familia `H01xx` · Cosecha real

Convierte los registros crudos de kilos en indicadores de rendimiento. Es la familia que
alimenta los tableros de producción de gerencia.

---

#### `H0100_Resumen_kgCosecha`

**Qué hace.** Enriquece `H00_VolumenCampo` con turno, semana, año y número de plantas.

**Por qué existe.** `H00` registra kilos por lote y fecha pero sin turno ni contexto
temporal agregable. Esta consulta añade lo necesario para segmentar la producción.

**Qué se obtiene.** 30.812 filas — el total de `H00`, incluida **la fila basura de H-06**.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Funciona (el join por `FundoPPto` acierta, `H00` usa vocabulario B), pero
**arrastra la fila de subtotal de 930.662,1 kg** con todos sus identificadores en NULL.
Cualquier total sobre esta consulta está sobreestimado en esa cantidad.

---

#### `H0101_ResumenHistoricos`

**Qué hace.** Consulta central de la familia. Calcula frutos totales y fecha ponderada, y
agrega por lote y paña.

**Cálculo — dos fórmulas importantes:**

```sql
FrutosT = KG / Peso * 1000      -- frutos totales estimados
FecPon  = Fecha * KG            -- fecha ponderada por kilos
```

**`FrutosT`** convierte la medida comercial (kilos) a la medida agronómica (número de
frutos), usando el peso unitario de baya en gramos. Permite comparar producción con los
conteos de `E03_ConteoEstados`, que están en frutos.

**`FecPon` merece explicación**, porque a primera vista parece un sinsentido — ¿multiplicar
una fecha por kilos?

Access almacena las fechas como números. `Fecha * KG` produce un producto que, dividido
entre `SUM(KG)`, da la **fecha promedio ponderada por volumen cosechado**:

```
fecha_media_cosecha = SUM(FecPon) / SUM(KG)
```

Esto responde una pregunta que el promedio simple no responde: *¿cuándo se cosechó el grueso
del volumen?* Si un lote se cosechó en cinco pasadas pero el 80% del kilaje salió en la
tercera, el promedio simple de fechas apunta a la tercera pasada — el ponderado también,
pero además refleja la distribución real.

Es el indicador de **concentración de cosecha**, clave para planificar cuadrillas y packing.

**Importante:** `FecPon` es un valor intermedio. Solo tiene sentido dividido entre `SUM(KG)`.
Un tablero que lo muestre en crudo mostraría un número sin significado.

**Qué se obtiene.** 30.624 filas.

**Alimenta a.** `H0104_FechaFinCosecha`, `H0105_RendTurno_paña`.

**Estado.** Correcta en su lógica. Arrastra las 2 filas basura de `H01` (H-06) y usa
`LEFT JOIN` contra `M_Lotes`, con lo que los 180 huérfanos de H-01 salen sin área ni
plantas.

---

#### `H0102_Producciondiaria`

**Qué hace.** Producción diaria por lote con semana, año y área.

**Por qué existe.** Vista de detalle temporal fino, sin agregación por paña. Sirve para
seguimiento diario durante la campaña.

**Qué se obtiene.** 30.446 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Correcta, y **es la versión más limpia de la familia**: usa `INNER JOIN` contra
`M_Lotes` y `M_Time`, lo que **elimina automáticamente las filas basura de H-06** (sus
identificadores nulos no enlazan) y los huérfanos de H-01.

De ahí la diferencia de filas: 30.446 frente a 30.624 de `H0101_ResumenHistoricos`. Las 178
filas de diferencia son precisamente basura y huérfanos.

**Recomendación para Power BI:** cuando haya que elegir entre `H0101` y `H0102` para un
total de kilos, `H0102` es la más confiable hoy.

---

#### `H0103_ResModulo`

**Qué hace.** Agrega kilos por módulo, campaña y año.

**Cálculo.** `año = Year(Fecha)` — nótese que calcula el año desde la fecha en lugar de
tomarlo de `M_Time`.

**Por qué existe.** Nivel de agregación intermedio (módulo) entre lote y fundo. Es el grano
en que se reportan los resultados a gerencia.

**Qué se obtiene.** 104 filas.

**Alimenta a.** `R0802_ResumenAño`.

**Estado.** Funciona. Detalle relevante: **`año` (de la fecha) y `Campaña` no son lo mismo**.
La campaña C2025 puede abarcar meses de 2025 y 2026. Agrupar por ambos simultáneamente
—como hace esta consulta— parte los totales de campaña en dos filas cuando la campaña cruza
el fin de año. Un tablero que sume por campaña debe agregar sobre ambas filas.

---

#### `H0104_FechaFinCosecha`

**Qué hace.** Identifica la **última fecha de cosecha** de cada lote por campaña.

**Cálculo.** `INNER JOIN` contra una subconsulta con `MAX(Fecha)` agrupado por
fundo/campaña/módulo/turno/lote — el patrón estándar para "traer la fila del máximo".

**Por qué existe.** La fecha de fin de cosecha determina cuándo el lote queda libre para la
poda siguiente. Es el dato que cierra el ciclo y permite planificar la campaña próxima:
`FInicio` de la siguiente campaña depende de cuándo terminó la anterior.

**Qué se obtiene.** 661 filas — una por lote/campaña.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Correcta. Es una de las consultas mejor construidas de la base.

---

#### `H0105_RendTurno_paña`

**Qué hace.** Rendimiento por turno y número de pasada de cosecha. **Filtrado a C2025.**

**Cálculo.** `SUM(KG)`, `SUM(FrutosT)`, `SUM(FecPon)` agrupados por turno y paña, cruzados
contra área y plantas del turno.

**Por qué existe.** Responde una pregunta operativa concreta: **¿cuánto rinde cada pasada de
cosecha?** En arándano la primera pasada suele dar fruta de mejor calibre y las últimas
menos volumen. Conocer esa curva permite decidir cuántas pasadas hacer antes de que deje de
ser rentable enviar cuadrilla.

Al traer `Area` y `NPlantas` permite calcular rendimiento por hectárea y por planta, que
son los indicadores comparables entre lotes de distinto tamaño.

**Qué se obtiene.** 3.442 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Correcta, con la misma advertencia que `0201_Flores`: tiene
`HAVING Campaña = "C2025"` **fijo en el SQL**. Para analizar C2026 hay que editar la
consulta. En el modelo destino esto debe ser un parámetro o un filtro de Power BI.

El nombre incluye "paña" con `ñ` — requiere el tratamiento de codificación descrito en
`01_AUDITORIA.md` §2.

---

### Familia `H02xx` · Packing

---

#### `H0201_PesoBaya_Elifab`

**Qué hace.** Cruza el resultado de packing (`H02_BDElifab`) con la producción de campo
(`H01_ProdHistorica`) para obtener el peso real de la baya.

**Por qué existe.** **Cierra el ciclo de información entre campo y planta de proceso.**

El peso unitario de baya se estima en campo, pero el dato exacto solo se conoce tras el
packing, donde se pesa y cuenta la fruta real. Esta consulta compara ambos y permite
calibrar las estimaciones de campo contra el resultado medido.

Usa `M_EquivalenciaElifab` para traducir el nombre de productor que usa la empacadora al
nombre de la empresa — el único caso en toda la base donde un problema de vocabulario se
resuelve explícitamente con una tabla de equivalencia. **Es el precedente interno que
justifica hacer lo mismo con el fundo** (H-01).

**Qué se obtiene.** 16.971 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Funciona, pero hereda H-10: los campos de `H02_BDElifab` que participan
(`Semana`, `Calibre`) son texto, así que el orden y los rangos no funcionan correctamente.

---

### Familia `H05xx` · Clima

---

#### `H0501_VariablesClima`

**Qué hace.** Expone las variables climáticas con año, semana y mes desde `M_Time`.

**Por qué existe.** Añade el contexto temporal agregable a la serie de la estación
meteorológica, para poder cruzar clima con fenología por semana.

**Qué se obtiene.** **155.588 filas** — exactamente el total de `H05_Clima`. Es un pase
directo.

**Alimenta a.** Nadie — consulta hoja.

**Estado. Hereda H-08 sin filtrar.** Las 2.079 mediciones duplicadas pasan tal cual. Todo
tablero de clima construido sobre esta consulta sobrestima la lluvia acumulada y sesga los
promedios de temperatura.

---

#### `H0502_Temperatura_variacion`

**Qué hace.** Analiza la variación de temperatura agregando por periodo.

**Por qué existe.** La **amplitud térmica** (diferencia entre máxima y mínima diaria) es un
factor determinante en arándano: influye en la acumulación de azúcares y en la firmeza del
fruto. Un rango amplio favorece calidad.

**Qué se obtiene.** 1.603 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Funciona; hereda H-08.

---

### Familia `R08xx` – `R09xx` · Forecast

La base tiene **dos sistemas de pronóstico paralelos** con horizontes distintos:

| | `R08_Forecast_Campaña` | `R09_Forecast_Semanal` |
|---|---|---|
| Horizonte | campaña completa | semana |
| Grano | módulo | lote |
| Versiones | 15, con nombre (`Proy_Mayo`) | 46, con código de semana (`S01`–`S32`) |
| Desglose | por destino (Exp/Des/Con) y calibre | por pasada |
| Filas | 101.715 | 48.368 |

**El punto crítico para Power BI:** ambas tablas **acumulan todo el histórico de
re-proyecciones**, no solo la vigente. Sumar sin filtrar por `Version` mezcla escenarios
distintos del mismo periodo y produce cifras que no significan nada.

---

#### `R0801_ResCampaña`

**Qué hace.** Resume el forecast de campaña por módulo, sumando solo los kilos exportables.

**Cálculo.** `SUM([KG Exp])` agrupado por versión/fundo/módulo/año/campaña, cruzado contra
`M_Mod` para traer área y plantas.

**Por qué existe.** Convierte el forecast semanal de detalle en un total de campaña por
módulo, comparable contra el resultado real.

**Nota importante sobre qué kilos usa.** Suma **solo `[KG Exp]`** — ignora `[Kg Des]` y
`[Kg Con]`. Es una decisión de negocio implícita: el forecast que importa es el de fruta
**exportable**, porque es la que genera margen. El descarte y el consumo se proyectan pero
no entran en este resumen.

Esto es relevante para H-04 caso 6: aquí hay un precedente de cómo se interpreta "los kilos
del forecast" en esta base — como `[KG Exp]`.

**Qué se obtiene.** 29 filas.

**Alimenta a.** `R0802_ResumenAño` (una vez corregida su referencia).

**Estado.** Correcta. Detalle: une `resMod.FundoPPto` (vocabulario B) contra
`M_Mod.Fundo_pptom5` (vocabulario C) — **son vocabularios distintos**. Que devuelva 29 filas
en vez de 0 indica que hay coincidencias parciales, pero es un join sospechoso que conviene
revisar con Planeamiento.

---

#### `R0801_Forecast_Campaña_SemMes`

**Qué hace.** *(pretende)* Despivotar los tres tipos de kilos (Exp/Des/Con) a formato largo,
con trimestre y campaña productiva.

**Estado. ROTA — H-04 caso 5.**

| | |
|---|---|
| Columnas rotas | `M_Time.CampProAra`, `M_Time.Trimestre` |
| Error | `Pocos parámetros. Se esperaba 2` |
| `M_Time` tiene | `Fecha, Sem, Mes, Año, SEvConteo, AQII, MesSem` — 7 columnas |

**Lo que revela sobre el modelo.** La consulta espera una dimensión de tiempo con dos
conceptos que no existen:

- **`Trimestre`** — trivial de derivar del mes.
- **`CampProAra`** — "Campaña Producción Arándano". **Este es el concepto que falta.**

La campaña productiva no coincide con el año calendario: C2025 abarca meses de 2025 y 2026.
Sin ese atributo en la dimensión de tiempo, no se puede agregar correctamente por campaña
sin recurrir a la columna `Campaña` de cada tabla de hechos — que es exactamente el tipo de
desnormalización que causa inconsistencias.

Es también el hallazgo que explica el defecto de `H0103_ResModulo`, donde `año` y `Campaña`
se agrupan juntos y parten los totales.

**Corrección.** Añadir `campana_productiva` y `trimestre` a la dimensión de tiempo del
modelo destino. Requiere que Planeamiento defina las fechas de corte de cada campaña.

Además, esta consulta es el peor caso de H-11: repite un bloque `FROM` de 25 líneas **tres
veces palabra por palabra**.

---

#### `R0802_ResumenAño`

**Qué hace.** *(pretende)* Apilar cosecha real y forecast en una sola tabla, etiquetando el
real con la versión `"Real"`.

**Por qué existe.** Es la consulta de **comparación plan vs. real**: pone lado a lado lo
proyectado y lo cosechado, con `Version` como discriminante. El literal `"Real"` convierte
el resultado efectivo en "una versión más" del pronóstico, lo que permite graficar ambos en
el mismo eje.

Es un buen diseño conceptual.

**Estado. ROTA — H-04 caso 3.**

| | |
|---|---|
| Referencia rota | `R0901_ResCampaña` |
| Objeto real | `R0801_ResCampaña` (29 filas) |
| Corrección | `R0901_` → `R0801_` (error de un dígito) |

Confirmado: `R0801_ResCampaña` expone exactamente las 8 columnas que el `UNION ALL` pide.
La corrección es mecánica.

---

#### `R0901_Forecas_SemAc`

**Qué hace.** Filtra `R09_Forecast_Semanal` para quedarse **solo con la proyección vigente
de cada semana**, en las campañas C2025 y C2026.

**Cálculo.** El filtro clave:
```sql
Int(Right(Left(Version,3),2)) = Sem
```

**Por qué existe — y por qué es la consulta más inteligente de la familia.**

`R09` acumula 46 versiones. La versión `S05` es la proyección emitida en la semana 5, y
contiene estimaciones para las semanas 5, 6, 7, 8... Si se suman todas las versiones, cada
semana aparece proyectada muchas veces.

Este filtro se queda con **la proyección que cada versión hizo para su propia semana** — es
decir, la estimación más reciente y por tanto más precisa de cada semana. Reconstruye así
una serie continua donde cada punto es el mejor pronóstico disponible en ese momento.

Es el equivalente a lo que en series temporales se llama *nowcast*.

**Qué se obtiene.** 6.994 filas de 48.368 — el 14,5%.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Funciona, con una **fragilidad importante**: el parseo `Left(Version,3)` asume
que el código tiene exactamente la forma `Snn`. Si alguien escribe `S5` en vez de `S05`, el
parseo devuelve un número incorrecto **sin lanzar error** y esa fila se pierde o se cuenta
mal en silencio.

Además ignora los sufijos: de `S27`, `S27_v2` y `S27_v3`, las tres pasan el filtro (las tres
empiezan por `S27`), así que la semana 27 aparece tres veces. **La consulta no desambigua
entre iteraciones de la misma semana.**

En el modelo destino, `Version` debe descomponerse en columnas propias
(`semana_emision`, `iteracion`) en lugar de parsearse.

---

#### `R0902_Forecast_Sem_vs_Camp`

**Qué hace.** *(pretende)* Comparar el forecast semanal contra el de campaña, prefijando las
versiones semanales con `"Proy."`.

**Estado. ROTA — H-04 caso 6.** Es la sexta consulta rota, detectada en la verificación
final.

| | |
|---|---|
| Columna rota | `R08_Forecast_Campaña.KG` |
| Error | `Pocos parámetros. Se esperaba 1` |
| Realidad | `R08` tiene `[KG Exp]`, `[Kg Des]`, `[Kg Con]` — no un `KG` genérico |

**Por qué esta corrección requiere decisión de negocio.** Tres interpretaciones posibles:

| Interpretación | `SUM` resultante |
|---|---|
| `[KG Exp]` (solo exportable) | 648.044.713,14 |
| `[KG Exp] + [Kg Con]` | 657.404.158,58 |
| `[KG Exp] + [Kg Des] + [Kg Con]` | 689.684.707,86 |

**El precedente sugiere `[KG Exp]`:** `R0801_ResCampaña`, la otra consulta que resume `R08`,
usa exactamente eso. Sería consistente.

**Pero la comparación sigue sin cerrar.** `SUM(R09.Kg)` = 51.083.049,92 frente a 648 M de
`R08`. Un factor de ~12,7. Como `R08` tiene 15 versiones y `R09` 46, y ninguna de las dos
está filtrada por versión en esta consulta, **se están comparando acumulados de escenarios
distintos**. La comparación solo es válida filtrando una versión de cada lado.

**Requiere confirmación de Planeamiento** sobre qué versión de `R08` compara contra qué
versión de `R09`. Registrado como decisión pendiente.

---

#### `R0903_Forecast_FrtsTotal`

**Qué hace.** Añade al forecast semanal la estimación de frutos totales del lote.

**Cálculo.** `frutosT = M_Lotes.NPlantas * R09_Forecast_Semanal.FrtCos`

**Por qué existe.** `FrtCos` es el número de frutos a cosechar **por planta** (medida de
muestreo). Multiplicado por las plantas del lote da el total absoluto. Es la extrapolación
del muestreo al lote completo — el paso que convierte una medición de campo en una
proyección de volumen.

**Qué se obtiene.** 22.272 filas de 48.368 — el `INNER JOIN` descarta el 54%.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Funciona, con dos advertencias:

1. **Une `R09.Fundo` contra `M_Lotes.Fundo_pptom5`** (vocabulario C). Que funcione confirma
   que `R09_Forecast_Semanal.Fundo` usa vocabulario C, distinto del que usan las tablas de
   evaluación. Es un quinto punto de contacto con H-01.
2. **El `INNER JOIN` descarta 26.096 filas** (54%) que no encuentran lote. Ese descarte es
   silencioso: el tablero muestra menos de la mitad del forecast sin indicarlo.

---

### Consultas utilitarias

---

#### `M_Mod`

**Qué hace.** Agrega `M_Lotes` a nivel de módulo, sumando área y plantas.

**Por qué existe.** Dimensión de módulo derivada. Evita repetir la agregación en cada
consulta que necesite área o plantas por módulo.

**Qué se obtiene.** 23 filas — **hay 23 módulos** en la operación.

**Alimenta a.** `R0801_ResCampaña`, `R0802_ResumenAño`.

**Estado.** Correcta. Expone los tres vocabularios de fundo (`Fundo`, `FundoPPto`,
`Fundo_pptom5`) en la misma fila — **es, de hecho, una tabla de equivalencia parcial de
H-01**, aunque no se use como tal.

---

#### `M_Lote_turno`

**Qué hace.** Expone `M_Lotes` con una clave concatenada de módulo y turno.

**Cálculo.** `ModTur = Modulo & Turno`

**Por qué existe.** La clave concatenada facilita joins y segmentación en Power BI, donde
una sola columna es más cómoda que dos.

**Qué se obtiene.** 860 filas — pase directo de `M_Lotes`.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Correcta.

---

#### `M_EdadCultivo`

**Qué hace.** Calcula la edad de la plantación por lote.

**Cálculo.** `Edad = (Now() - CDate(Avg(FSiembra))) / 365`

**Por qué existe.** La edad de la planta determina su potencial productivo: el arándano
alcanza plena producción hacia el tercer o cuarto año y decae después de cierta edad.
Comparar rendimiento sin controlar por edad lleva a conclusiones erróneas.

Excluye `Lote = "L000"` con un `HAVING` — `L000` es presumiblemente un lote ficticio o de
prueba.

**Qué se obtiene.** 860 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Funciona, con una advertencia relevante: **`Now()` hace el resultado dependiente
de la fecha de ejecución**. El mismo tablero da valores distintos cada día, y una captura de
hace seis meses no es reproducible.

Para análisis histórico esto es incorrecto: la edad debería calcularse contra la fecha del
hecho analizado, no contra hoy. En el modelo destino conviene exponer `FSiembra` y calcular
la edad en la capa de presentación.

---

#### `TPlantas`

**Qué hace.** Total de plantas por fundo y módulo.

**Qué se obtiene.** 23 filas.

**Alimenta a.** Nadie — consulta hoja.

**Estado.** Correcta, pero **redundante**: `M_Mod` ya expone `SUM(NPlantas)` con el mismo
grano, más el área. Caso menor de H-11.

---

#### `E`

**Qué hace.** *(pretende)* Contar plantas y sumar conteos de `E02` y `E03` por actividad y
evaluador.

**Estado. ROTA — H-04 caso 4.** Pide `Actividad`, que solo existe en `E01_Ramas`.

**Interpretación.** El nombre de un solo carácter, la ausencia de prefijo de familia y la
lógica —agrupar por evaluador— indican que era **un borrador para analizar productividad de
evaluadores** que quedó guardado.

Es interesante porque revela una intención: alguien quiso medir cuántas plantas evalúa cada
evaluador. Esa pregunta sigue sin respuesta hoy por H-09 (el maestro de evaluadores no
enlaza). Vale la pena rescatar la intención aunque se descarte la consulta.

**Recomendación.** Descartar la consulta; recuperar el requisito en el modelo destino, donde
sí se puede responder al enlazar por DNI.

---

#### `~TMPCLP151491`

Consulta temporal generada por el portapapeles de Access. El prefijo `~` marca objetos
temporales del motor. **Descartar** (H-12).

---

## 5 · Los 6 patrones de despivote manual

Seis consultas implementan despivote con `UNION ALL` y literales (H-11):

| Consulta | Ramas | Qué despivota |
|---|---|---|
| `0106_RaFloYem` | 3 | Ramas · Flores · YemaAb |
| `0303_ConteoEstados_Turno` | 5 | Est1 · Est2 · Est3 · Est4 · Est5 |
| `0304_ConteoEst_Flo_Turno` | 2 | Flores + Estados |
| `0305_Brotes_Ramas` | 2 | Brotes + Ramas |
| `0306_FrutosFlores` | 2 | Estadios + Flores |
| `R0801_Forecast_Campaña_SemMes` | 3 | Kg Exp · Kg Des · Kg Con |

**Por qué existen.** Access no tiene `UNPIVOT`. El formato largo es necesario para que Power
BI grafique varias series en un eje con un solo campo de leyenda, así que se construye a
mano.

**Por qué son innecesarios en el destino.** PostgreSQL tiene `LATERAL (VALUES ...)`, y Power
Query tiene "Anular dinamización de columnas" nativo. En ambos casos el bloque `FROM` se
evalúa una sola vez.

**El coste real.** En `R0801_Forecast_Campaña_SemMes` el bloque `FROM` —con su subconsulta
agregada de `M_Lotes` y su join a `M_Time`— se evalúa **tres veces** sobre 101.715 filas. Y
corregir un error exige editar los tres bloques: si se edita uno y se olvida otro, la
consulta **sigue ejecutándose y devuelve resultados inconsistentes entre métricas**, sin
señal de error.

Es llamativo que **3 de estos 6 casos coinciden con consultas rotas**. La correlación tiene
explicación: son las consultas más largas y difíciles de editar, y por eso quedaron
desactualizadas cuando cambiaron los objetos que referencian.

---

## 6 · Mapa de dependencias

Del análisis de linaje (`evidencia\05_linaje_dependencias.txt`):

### Las consultas más reutilizadas

| Consulta | La usan |
|---|---|
| `0104_PromFlores` | 6 consultas |
| `0301_ConteoEstados` | 5 consultas |
| `H0101_ResumenHistoricos` | 2 consultas |
| `0101_Diametros` | 3 consultas |

Corregir `0104_PromFlores` o `0301_ConteoEstados` afecta a media familia. Son los puntos de
mayor apalancamiento del modelo.

### Impacto inverso por tabla

| Tabla | Consultas afectadas si se modifica |
|---|---|
| `M_Lotes` | **33 de 40** |
| `M_Time` | **26 de 40** |
| `E02_ConteoFlores` | 11 |
| `E03_ConteoEstados` | 8 |
| `H01_ProdHistorica` | 7 |
| `M_Poda` | 7 |
| `E01_Ramas` | 5 |

`M_Lotes` y `M_Time` son las dos dimensiones sobre las que descansa el modelo entero. **Todo
cambio en ellas debe validarse contra las 33 y 26 consultas respectivamente.**

### Tablas sin ningún consumidor

`E05_DiametrosBayas` · `M_Evaluadores` · `M_nMuestra` · `Errores de pegado`

Las tres primeras contienen **4.905 filas de datos reales que nunca llegan a un tablero**.
Ver `03_GUIA_REPORTES.md` §6.

### Consultas hoja (puntos de consumo de Power BI)

De las 40, **28 son hoja** — nadie depende de ellas. Son las candidatas naturales a ser los
puntos de conexión de Power BI. Las 12 restantes son intermedias: existen para alimentar a
otras.

---

## 7 · Lo que la base podría responder y hoy no responde

Cerrando: tres preguntas de negocio para las que **los datos ya existen** en la base, y que
no se responden por defectos corregibles.

**1 · ¿El calibre medido en campo predice el calibre de packing?**
`E05_DiametrosBayas` tiene 4.193 mediciones de diámetro de baya; `H02_BDElifab` clasifica
117.536 registros por calibre. Nadie las cruza. Poder anticipar el calibre semanas antes del
packing permitiría comprometer volúmenes con clientes antes de cosechar.

**2 · ¿Qué evaluadores producen mediciones consistentes?**
`M_Evaluadores` tiene 31 registros y las tablas de evaluación guardan el DNI en cada fila.
Nunca se cruzan (H-09). La variabilidad entre evaluadores es una fuente de error conocida en
evaluación fenológica, y hoy no se mide.

**3 · ¿Se cumplió el muestreo requerido en cada lote?**
`M_nMuestra` define cuántas muestras corresponden por lote y evaluación (681 filas). Nadie
la consulta. No se sabe qué evaluaciones se hicieron con muestreo insuficiente — y esas son
precisamente las que producen estimaciones poco confiables.

Las tres se resuelven con joins que hoy no existen. Ninguna requiere capturar dato nuevo.
