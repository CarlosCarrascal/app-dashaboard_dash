# Relación clima / riego ↔ kg/ha — campaña 2025

**Fecha:** 2026-08-07 · **Fuente:** `docs/data/IA.final.xlsx` (5 hojas) · **Tablero:**
`apps/dashboard/dashboard/app.py` (`npm run dashboard`).

---

## 0 · Actualización del 2026-08-07 (tarde)

Llegó una versión nueva de `IA.final.xlsx` y se reajustó el modelo. **Las conclusiones de
fondo no cambian**; sí cambian varias cifras. Lo que hay que saber antes de leer el resto:

**La cosecha y el clima son idénticos** a la versión anterior, byte a byte. Lo único que
cambió es la hoja **Riego**: pasó de 11.128 filas con columna `Turno` a 988 ya agregadas
por módulo y semana.

**Esa agregación vino inconsistente.** Comparando contra el archivo anterior:

| Columna | Cómo se agregó | Coincidencias |
|---|---|---|
| `m3/ha` | **suma** de los turnos | 984 de 988 |
| `Lt/planta` | **media** de los turnos | 982 de 988 |

Las dos columnas del mismo archivo se agregaron con criterios distintos. La consecuencia
es que `m3/ha` declara **171 mm/semana contra una ETo de 29**: 5,98 veces la demanda
hídrica, lámina que no cabe en el perfil del suelo. El tablero lo detecta solo
(`diagnosticar_riego()`) y lo avisa en rojo en la sección **Resumen**.

**Qué implica para el análisis.** La suma equivale a la media multiplicada por el número
de turnos, que es constante dentro de cada módulo. Así que el **orden** de los módulos por
riego se conserva y el análisis de relación sigue en pie; lo que no se puede leer es la
magnitud absoluta como lámina de riego real. Las pendientes de §2.6 en kg/ha por 100 m³/ha
quedan expresadas en una unidad que ya no es la lámina física.

**Reajuste del modelo.** Se barrieron 108 combinaciones de hiperparámetros, eligiendo con
«deja-una-semana-fuera» y reportando con «deja-un-bloque-fuera». La configuración anterior
resultó estar en el puesto 57 de 108:

| | R² selección | R² honesto | MAE honesto |
|---|---|---|---|
| Anterior (prof. 3, η 0,03) | +0,344 | −0,116 | 757 kg/ha |
| **Actual** (prof. 6, η 0,01, hoja ≥ 10, λ 5) | **+0,402** | **+0,053** | **686 kg/ha** |
| Piso: predecir la media | — | −0,147 | 756 kg/ha |

**El ajuste anterior no medía nada:** su MAE honesto (757) era el mismo que el de predecir
el promedio (756). El nuevo cruza el piso por primera vez. La mejora se verificó con 8
semillas y sobrevive con 5,1 desviaciones típicas de margen.

**Por qué XGBoost y no algo más simple** — comprobado, no supuesto, con las mismas
particiones:

| Modelo | R² deja-una-semana | R² deja-un-bloque | MAE bloque |
|---|---|---|---|
| Predecir la media | −0,001 | −0,147 | 756 |
| Regresión lineal | +0,257 | **−0,590** | 962 |
| Ridge | +0,261 | −0,456 | 913 |
| Árbol único | +0,270 | −0,431 | 839 |
| Random Forest | +0,380 | −0,149 | 775 |
| **XGBoost (ajustado)** | **+0,397** | **+0,053** | **688** |

La regresión lineal es **mucho peor que no usar ninguna variable**. No es que no encuentre
el patrón: lo encuentra y lo extrapola fuera del rango que vio, y como el bloque retenido
cae en otra estación, se dispara. Los árboles no extrapolan. XGBoost es el único que queda
por encima del piso, y ésa —no la precisión— es la justificación de usarlo.

**Lo que sigue igual.** El calendario desnudo (R² +0,345) le sigue ganando a las cinco
variables de clima juntas (+0,266); el riego sigue siendo el de mayor aporte marginal
(+0,131) pese a tener la correlación más débil; y la temperatura mínima y el DPV siguen
con aporte negativo.

Panel resultante: **452 celdas** módulo × semana, **18 módulos** en 4 fundos, **50 semanas**
de 2025. Variable objetivo `kg/ha`; predictoras `DPV`, `Riego`, `Rad`, `ETo`, `Temp máx`,
`Temp mín`. Todo lo que sigue sale exclusivamente de ese archivo.

---

## 1 · Cómo se armó el panel (tres decisiones que cambian los números)

El Excel no se puede cruzar tal cual. Tres cosas hubo que resolver, y conviene que estén a la
vista porque cualquiera de ellas movida da otro resultado:

| Decisión | Qué se hizo | Por qué |
|---|---|---|
| **Riego por turno → módulo** | **Promedio** entre turnos, no suma | Cada turno ya viene en m³/**ha** de su propio sector. Sumar los 10-12 turnos da 172 mm/semana contra una ETo de 29 mm/semana: **6× la demanda**, físicamente imposible. El promedio da 15,5 mm/semana (ratio riego/ETo = 0,57), que sí es plausible en goteo. |
| **M10A y M10B** | Se fusionan en M10 | La cosecha los separa; el riego no. Sin fusionar, esas filas se quedan sin riego. |
| **30 filas duplicadas** | Se consolidan sumando kilos y área | Todas en S01 — varios eventos de cosecha con la misma etiqueta. El kg/ha tiene que ser **ponderado por área**; promediar los kg/ha parciales daría un número distinto y equivocado. |

Verificado: `Kg/Ha = Kilogramos / Area` en el 100% de las filas del origen.

---

## 1 bis · El R² que se reporta es del conjunto, no de cada variable

Todos los R² de este informe son **del modelo con las 6 variables juntas**. El R² no se
reparte entre variables: no es aditivo. Las dos preguntas por separado, medidas con
deja-una-semana-fuera:

| Variable | r (Pearson) | r² descriptivo | **R² sola** | R² del modelo sin ella | **Aporte marginal** |
|---|---|---|---|---|---|
| **Riego** | +0,124 | 1,5 % | −0,088 | **+0,196** | **+0,175** |
| ETo | +0,014 | 0,0 % | −0,607 | +0,326 | +0,046 |
| Radiación | +0,118 | 1,4 % | −0,820 | +0,331 | +0,040 |
| Temp máxima | −0,373 | 13,9 % | −0,337 | +0,345 | +0,026 |
| Temp mínima | −0,466 | 21,8 % | −0,064 | +0,389 | **−0,017** |
| DPV | −0,356 | 12,7 % | −0,155 | +0,382 | **−0,010** |
| **Las 6 juntas** | | | **+0,371** | | |

Suma de los R² individuales: **−2,070**. El del conjunto: **+0,371**. No hay relación
aritmética entre ambos.

Tres lecturas que cambian el diagnóstico:

1. **Ninguna variable se sostiene sola.** Las seis dan R² negativo por separado: cada una
   predice peor que el promedio histórico. El +0,371 nace de la combinación.
2. **El orden por correlación y el orden por aporte son casi opuestos.** El riego, que tiene
   la correlación más débil de todas (+0,124), es **la variable más valiosa del modelo**:
   quitarla derrumba el R² de 0,371 a 0,196. La temperatura mínima y el DPV, que encabezan
   las correlaciones, tienen aporte **negativo** — el modelo funciona algo mejor sin ellas.
3. **Por qué el riego vale tanto teniendo tan poca correlación.** No entra como lámina de
   agua: entra como **señal de manejo**. El riego se programa según el estado del cultivo, así
   que codifica en qué punto de su ciclo está cada módulo — que es justamente la variable que
   falta. El riego está funcionando como sustituto imperfecto de la fenología.

Esto invierte la conclusión intuitiva: **la variable que hay que mirar no es la de mayor
correlación, es la de mayor aporte marginal.**

---

## 2 · Rol 2 · Análisis agronómico-matemático

### 2.1 El orden que sale de los datos

Correlación con kg/ha y peso SHAP del modelo XGBoost:

| Variable | Pearson | Spearman | Varianza explicada sola | \|SHAP\| medio | Pendiente lineal |
|---|---|---|---|---|---|
| **Temp mínima** | **−0,466** | −0,502 | 21,8 % | **250 kg/ha** | −269 kg/ha por °C |
| Temp máxima | −0,373 | −0,366 | 13,9 % | 148 kg/ha | −167 kg/ha por °C |
| **DPV** | **−0,356** | −0,311 | 12,7 % | 83 kg/ha | −2.498 kg/ha por kPa |
| Radiación | +0,118 | +0,104 | 1,4 % | 156 kg/ha | +2,2 kg/ha por W/m² |
| **Riego** | **+0,124** | +0,057 | 1,5 % | 137 kg/ha | +158 kg/ha por 100 m³/ha |
| ETo | +0,014 | −0,029 | 0,0 % | 69 kg/ha | +1,9 kg/ha por mm |

Leído sin más, el titular sería: *«la temperatura mínima es el factor dominante; cada grado de
más cuesta 269 kg/ha, y cada kPa de DPV cuesta 2.498 kg/ha»*.

**Ese titular es falso.** Las tres pruebas siguientes lo desarman.

### 2.2 Prueba 1 — el clima es un calendario disfrazado

Las variables climáticas están casi determinadas por la posición en el año:

| Variable | Correlación con el número de semana |
|---|---|
| Temp mínima | **−0,774** |
| Temp máxima | −0,603 |
| DPV | −0,563 |
| Radiación | +0,213 |
| ETo | +0,007 |

Y la cosecha tiene su propia curva de calendario, fijada por la **poda**, no por el clima:

| Tramo | Temp mín media | DPV medio | kg/ha medio |
|---|---|---|---|
| S01–S15 (cola de la campaña anterior) | 20,4 °C | 0,67 | 486 |
| S16–S29 (valle) | 17,8 °C | 0,31 | 689 |
| S30–S52 (campaña 2025, pico) | 16,6 °C | 0,40 | **1.544** |

Las 5 semanas de temperatura mínima **más baja** son S33-S41 (1.625 kg/ha medio) y las 5 **más
alta** son S06-S10 (370 kg/ha). No es que el frío produzca fruta: es que **el pico de cosecha
cae en invierno austral** porque así se programó la poda. La correlación de −0,47 mide el
solapamiento de dos calendarios, no una causa.

La prueba definitiva: se entrenó el mismo modelo contra el **puro número de semana**, sin
ninguna variable física.

| Modelo (deja-una-semana-fuera) | R² |
|---|---|
| **Solo el número de semana** | **+0,308** |
| Las 5 variables de clima juntas | +0,196 |

**El almanaque le gana al clima.** Si las cinco mediciones meteorológicas no superan a
`nsem`, no están aportando información física — están aproximando peor lo que la fecha ya dice.

### 2.2 bis La relación al grano correcto, y módulo por módulo

El clima se mide una vez por semana para todo el fundo, y **eso es correcto**: la temperatura
y el DPV no varían de forma apreciable entre un módulo y el vecino. Así que hay que hacerle
dos preguntas que el análisis celda-por-celda no responde.

**(a) Al grano de la semana.** Agregando el fundo entero a una fila por semana (50 filas,
kg/ha ponderado por área), la asociación es **bastante más fuerte** que celda por celda:

| Variable | r (nivel semana) | r² | r (nivel celda) |
|---|---|---|---|
| **Temp mínima** | **−0,706** | **49,8 %** | −0,466 |
| Temp máxima | −0,572 | 32,7 % | −0,373 |
| DPV | −0,504 | 25,4 % | −0,356 |
| Riego | +0,116 | 1,4 % | +0,124 |
| Radiación | +0,094 | 0,9 % | +0,118 |
| ETo | −0,068 | 0,5 % | +0,014 |

Ésta es la forma correcta de reportar la asociación climática: al grano al que el dato existe.
La temperatura mínima acompaña al **49,8 %** de la variación semanal del rendimiento del fundo.

**(b) Dentro de cada módulo.** Prueba de consistencia: si la relación es física, debería
reaparecer en cada módulo por separado. **Y en gran medida reaparece:**

| Variable | Mediana entre módulos | Rango | Módulos con signo negativo |
|---|---|---|---|
| Temp mínima | **−0,508** | −0,752 a +0,770 | **16 de 18** |
| DPV | −0,289 | −0,754 a +0,943 | **16 de 18** |
| Riego | +0,017 | −0,527 a +0,715 | 9 de 18 |
| Radiación | +0,158 | −0,188 a +0,773 | 5 de 18 |

Es un patrón consistente y reproducible, más sólido de lo que sugeriría solo la correlación
global. **Pero la consistencia no distingue las dos hipótesis**, porque los 18 módulos comparten
el mismo calendario: todos suben en S30-S52. El patrón es igual de esperable si la causa es la
temperatura o si es la poda.

**(c) Las dos excepciones son la prueba decisiva.** Los únicos dos módulos con correlación
**positiva** son también los dos que **arrancan la cosecha más tarde**:

| Módulo | Primera semana | Semana del pico | r (Temp mín ↔ kg/ha) |
|---|---|---|---|
| Ayllu Allpa / M13 | **S35** | S48 | **+0,770** |
| Ayllu Allpa / M14 | **S39** | S48 | **+0,761** |
| Los otros 16 | S01–S31 | S32–S50 | −0,254 a −0,752 |

M13 y M14 cosechan de S35-S39 a S52, subiendo de ~150 a ~1.700 kg/ha. En ese tramo la
temperatura **también sube**. Resultado: correlación positiva y fuerte.

Es el mismo fundo, el mismo termómetro, la misma semana — y el signo se invierte según dónde
caiga la ventana de cosecha. Si la temperatura fuera la causa, un módulo que cosecha mientras
hace más calor debería rendir **menos**, no más. Lo que la correlación mide es **el solapamiento
entre la ventana de cosecha y la curva anual de temperatura.**

### 2.3 Prueba 2 — el techo estructural

El clima es **un solo valor por semana** para los 18 módulos — y así corresponde, según lo
anterior. La consecuencia es entonces aritmética, no un defecto de medición. La varianza del
kg/ha se reparte así:

- **49,5 %** entre semanas → es lo máximo que el clima puede llegar a explicar.
- **50,5 %** entre módulos dentro de la misma semana → **ninguna variable climática puede
  tocarlo nunca**, por espacialmente fina que sea la medición.

Para esa mitad hace falta algo que **distinga un módulo de otro**. La única candidata en el
archivo es el riego, y no la explica:

| Riego → desvío del promedio semanal | Valor |
|---|---|
| Correlación (dentro de semana) | +0,107 |
| Varianza explicada | **1,1 %** |
| R² con validación cruzada | **−0,149** |
| Pendiente | +105 kg/ha por 100 m³/ha |

Es decir: **de por qué el módulo M09 rinde distinto que el M03 en la misma semana, este
archivo no explica prácticamente nada.** Y esa es la mitad del problema.

### 2.4 Prueba 3 — validación honesta

| Esquema | R² | MAE (kg/ha) | Lectura |
|---|---|---|---|
| Baseline: predecir el promedio | 0,000 | 708 | el piso |
| Baseline: promedio de cada semana | +0,495 | 460 | sin usar ninguna variable |
| (a) 5-fold aleatorio | +0,500 | 461 | **inflado** |
| (b) Deja-un-módulo-fuera | +0,491 | 475 | inflado por la misma razón |
| (c) Deja-una-semana-fuera | +0,371 | 541 | aún interpola entre semanas vecinas |
| **(d) Deja-un-bloque-de-10-semanas-fuera** | **−0,070** | **743** | **honesta** |
| Corte temporal (entrena S<36, valida S≥36) | **−1,121** | 1.055 | pronóstico real |

Dos lecturas obligadas:

1. **El R² de 0,500 del 5-fold aleatorio es una fuga, no un logro.** Coincide casi exactamente
   con el baseline «promedio de cada semana» (0,495). Como el clima es constante dentro de la
   semana, al partir al azar el modelo ve otros módulos de la *misma* semana durante el
   entrenamiento y solo tiene que recordar el promedio de esa semana. No aprendió nada.
2. **Al quitar las semanas vecinas, la señal desaparece** (R² = −0,070: peor que predecir la
   media global). Lo que parecía conocimiento era interpolación de una curva suave.
3. **Como pronóstico, es destructivo:** R² = −1,12 en corte temporal, MAE de 1.055 kg/ha sobre
   una media de 1.294. Equivocarse en el 81 % es peor que no tener modelo.

### 2.5 Un problema adicional: no se puede repartir el crédito

Correlaciones **entre las predictoras**:

- DPV ↔ Temp máxima: **0,97**
- Radiación ↔ ETo: **0,97**
- Temp mín ↔ Temp máx: 0,84

Son casi la misma señal medida de tres maneras. El reparto SHAP entre ellas es en buena parte
arbitrario: cambiando la semilla o quitando una, el ranking se reordena. Afirmar «el DPV pesa
más que la radiación» con estos datos no tiene sustento.

### 2.6 Respuesta directa a las preguntas planteadas

> **¿Qué variable afecta más al kg/ha?**

En asociación cruda, la temperatura mínima (r = −0,47; 250 kg/ha de \|SHAP\|). **En efecto
causal demostrable con este archivo, ninguna.** El ranking observado es, en su mayor parte, el
calendario de poda visto a través del termómetro.

> **¿Cómo impacta el DPV matemáticamente en los kilos?**

La recta ajustada da **−2.498 kg/ha por cada kPa**. Ese número no debe usarse: el DPV está
correlacionado 0,97 con la temperatura máxima y −0,56 con la semana del año, y su rango útil
(0,22–0,80 kPa) coincide con el ciclo estacional completo. La pendiente mide la pendiente de la
campaña, no la respuesta fisiológica al déficit de presión de vapor. Con DPV medido **por
módulo** y controlando por semana, la pregunta sería contestable; con un dato semanal único
para todo el fundo, no.

> **¿Cómo impacta el riego?**

Es la única variable que **sí** varía por módulo, y la única cuyo efecto puede aislarse del
calendario. Controlando por semana: **+105 kg/ha por cada 100 m³/ha adicionales**, con r =
+0,107 y **1,1 % de varianza explicada**. Estadísticamente indistinguible de cero en la
práctica. El ratio riego/ETo mediano es 0,51 (media 0,57), y su correlación con el rendimiento
es +0,086.

Interpretación agronómica: dentro del rango en que Aqu Anqa opera hoy, **el riego no es el
factor limitante del rendimiento semanal**. Eso no significa que el riego no importe —
significa que la lámina aplicada ya está en una zona donde variarla no mueve la aguja, o que su
efecto es acumulativo y no se ve en la ventana semanal.

---

## 3 · Rol 3 · Resumen ejecutivo

### 3.1 Qué se puede afirmar ante gerencia

**Lo que este análisis prueba:**

- Se consolidó, por primera vez, un panel único de 452 celdas módulo × semana que cruza
  cosecha, clima y riego real de la campaña 2025. Ese panel es reutilizable y auditable.
- El proceso detectó y corrigió tres defectos del archivo que habrían falseado cualquier
  cálculo: el riego sumado en vez de promediado (6× la demanda hídrica real), 30 filas
  duplicadas en S01, y la desalineación M10A/M10B.
- **Existe una asociación fuerte y consistente entre temperatura y rendimiento semanal:**
  r = −0,706 al grano de la semana (49,8 % de la varianza), y de signo negativo en 16 de los
  18 módulos analizados por separado. Es un patrón real y reproducible.
- **Esa asociación no es causal, y hay evidencia directa de por qué:** los dos módulos que
  cosechan más tarde (M13, M14) invierten el signo a +0,77. Mismo clima, signo opuesto, según
  dónde caiga la ventana de cosecha.
- **El riego es la variable más valiosa del modelo** (aporte marginal +0,175, contra −0,017 de
  la temperatura mínima), pese a tener la correlación cruda más débil. Actúa como señal de
  manejo: codifica en qué punto del ciclo está cada módulo.
- **La mitad de la variación del rendimiento ocurre entre módulos dentro de la misma semana, y
  hoy no se mide nada que la explique.** Éste es el hallazgo con más valor económico del
  informe.

**Lo que este análisis NO permite afirmar:**

- Que el DPV, la temperatura o la ETo causen las variaciones de rendimiento. La asociación
  observada es indistinguible del calendario de poda.
- Que se pueda pronosticar el kg/ha a una o seis semanas. Probado explícitamente: R² = −1,12.

### 3.2 Por qué igual conviene el tablero

La recomendación **no** es transicionar a un tablero predictivo — no hay nada que predecir
todavía. Es adoptarlo por tres razones distintas y más sólidas:

1. **Convierte el Excel en un activo auditable.** Hoy las tres correcciones del §1 se aplican a
   mano y sin registro. El tablero las aplica igual siempre y las declara en pantalla.
2. **Hace visible el hueco de instrumentación.** El gráfico «techo estructural del clima» pone
   el 50,5 % no explicado delante de quien decide el presupuesto. Ése es el argumento para
   pedir sensores por módulo.
3. **Establece el estándar de evidencia.** La pestaña de validación deja documentado que un
   R² de 0,50 mal medido y uno de −0,07 bien medido salen de los mismos datos. Cualquier
   proveedor que llegue prometiendo precisión tendrá que pasar por esa misma tabla.

### 3.3 Qué falta para llegar al modelo predictivo

En orden de retorno por sol invertido:

| # | Qué | Por qué es lo que destraba |
|---|---|---|
| 1 | **Fecha de poda por módulo** | Es la variable que hoy actúa disfrazada de temperatura, y lo que explica que M13/M14 inviertan el signo. Incluirla separa el calendario del clima y vuelve interpretable todo lo demás. Es dato que **ya existe** — no hay que medir nada nuevo. |
| 2 | **Fenología (E02–E05) alineada con 2025** | Flores, estadios y diámetro de baya son los predictores directos de carga frutal, y son atributos **de módulo**: atacan el 50,5 % inalcanzable. Hoy solo cubren C2026. |
| 3 | **Atributos de módulo: variedad, edad de planta, densidad, suelo** | Son las candidatas restantes para la mitad de varianza que ocurre entre módulos. Baratas: son maestras, no series de tiempo. |
| 4 | **Una segunda campaña con riego medido** | Con 50 semanas de un solo año no hay forma de distinguir efecto climático de efecto de temporada. |

**Lo que NO hace falta:** instrumentar clima por módulo. La temperatura y el DPV no varían de
forma apreciable dentro del fundo, así que medirlos con más finura espacial no aportaría
información nueva — y no toca el 50,5 % de varianza entre módulos, que por definición necesita
una variable que distinga un módulo de otro.

### 3.4 Recomendación

Adoptar el tablero como **herramienta de auditoría y diagnóstico**, presentándolo con esa
etiqueta. No comprometer un pronóstico basado en clima y riego: los datos actuales no lo
sostienen, y prometerlo ahora quemaría la credibilidad del proyecto cuando falle en campo.

El punto #1 de la tabla anterior — instrumentar el clima a nivel de módulo — es la inversión
que convierte este trabajo en un modelo predictivo. Es también la única que no se puede suplir
con más análisis sobre los datos que ya existen.

---

## 4 · Relación con el análisis previo

Este informe **converge con `02_relacion_variables_kg_ha.md`** por un camino independiente. Aquel
trabajo, hecho sobre `reporting.v_analitica_modulo_semana`, ya había descartado el pronóstico a
1 semana (R² entre −0,331 y −0,089) y había detectado que `lluvia_acum_poda_mm` encabezaba el
ranking SHAP siendo **una huella de la cohorte de poda disfrazada de lluvia**.

Aquí ocurre exactamente lo mismo con la temperatura mínima y el DPV: variables que el modelo
usa como marcador de calendario, no como magnitud física. Que el patrón reaparezca con otra
fuente, otro panel y otro conjunto de variables refuerza el diagnóstico de fondo — **el
determinante dominante del kg/ha semanal en este fundo es la programación de la poda**, y hasta
que esa variable entre explícitamente al modelo, seguirá contaminando el peso de todas las demás.

Diferencia de alcance: aquel análisis reportó R² = 0,283 en su esquema honesto
(deja-un-módulo-fuera) con 14 variables incluyendo edad, GDD acumulados y dispersión de poda.
Éste, con solo 6 variables y sin ninguna que capture la cohorte, cae a −0,070 en su esquema
honesto. La comparación es en sí misma un argumento: **las variables que faltan valen más que
las que hay.**
