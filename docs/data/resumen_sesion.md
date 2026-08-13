# Resumen de la Sesión: Optimización del Modelo Predictivo con GDD

A lo largo de esta sesión de trabajo, nos hemos enfocado en mejorar la precisión del modelo predictivo de rendimiento agrícola (Kg/Ha) incorporando conceptos de fisiología vegetal, específicamente los Grados Día de Desarrollo (GDD), y resolviendo diversos problemas técnicos que surgieron durante la implementación en el dashboard de Streamlit.

## 1. Objetivos Iniciales y Exploración
- **Objetivo Principal:** Mejorar el coeficiente de determinación ($R^2$) del modelo predictivo (XGBoost), que inicialmente rondaba un valor de **0.461**.
- **Enfoque Fisiológico:** El usuario propuso integrar los GDD (Grados Día de Desarrollo) en lugar de utilizar las temperaturas máximas y mínimas por separado, buscando que el modelo entienda la acumulación térmica y el estrés en la planta de una manera más biológica y coherente.
- **Configuración Base:** Se confirmó empíricamente que la mejor respuesta del modelo a los datos históricos se daba con un desfase de **Riego = 1 semana** y una ventana de promedio de **Clima = 7 días**, reflejando la respuesta inmediata de la planta al riego frente al efecto acumulativo del clima.

## 2. Implementaciones Realizadas

### A. Integración de Grados Día de Desarrollo (GDD)
- Se desarrolló la lógica para calcular el GDD con una temperatura base de **4.4°C** utilizando las temperaturas máxima y mínima.
- Se incorporó la variable `gdd_lag` como una nueva característica (feature) oficial del modelo predictivo.
- **Archivos Modificados:**
  - `db/tools/dashboard/config.py`: Se agregó `gdd_lag` a la lista de `FEATURES`.
  - `db/tools/dashboard/nucleo/datos.py`: Se actualizó la función de cálculo de promedios móviles para incluir la columna `gdd_semana`.

### B. Control Dinámico de Desfase de GDD en la Interfaz
- Se implementó un nuevo control interactivo en la barra lateral del dashboard para permitir al usuario ajustar la ventana de observación del GDD (desfase) entre 1 y 8 semanas.
- **Archivos Modificados:**
  - `db/tools/dashboard/app.py`: Se añadió el componente `st.sidebar.number_input` para el `Desfase de GDD (semanas)`.

## 3. Errores Encontrados y Soluciones Aplicadas

### Error de Caché y `KeyError: 'gdd_lag'`
**Problema:**
Al añadir la nueva variable interactiva del GDD, el dashboard colapsó mostrando un error `KeyError: "['gdd_lag'] not in index"`.

**Análisis:**
El error ocurría porque Streamlit estaba utilizando una versión antigua del panel de datos guardada en la caché (`@st.cache_resource` o `@st.cache_data`) que no contenía la columna `gdd_lag`. El modelo XGBoost intentaba buscar esta columna para realizar predicciones y fallaba.

**Soluciones Aplicadas:**
1. **Invalidación Correcta de la Caché:** Se actualizó la firma de la función `entrenar` en `servicios/cache.py` para que dependa explícitamente de la configuración de `FEATURES`. De este modo, si las variables predictoras cambian, Streamlit fuerza el reentrenamiento del modelo en lugar de usar la versión cacheada.
2. **Programación Defensiva (Cálculo al Vuelo):** Se añadió una lógica de contingencia en `nucleo/modelo.py`. Si el DataFrame llega al modelo sin la columna `gdd_lag` (por algún desfase en el estado), esta se calcula al momento usando las temperaturas existentes, garantizando que el modelo nunca falle por esta causa y recupere el estado.

### Desviaciones en Predicciones Semanales
**Problema:**
El usuario notó que en ciertas proyecciones semanales, el modelo mostraba desviaciones muy grandes respecto a la realidad.

**Análisis e Investigación:**
Se explicó que estas anomalías se deben principalmente a la naturaleza de los datos y el proceso biológico actual que no se le está entregando al modelo:
1. **Falta de variable "Fecha de Poda":** Al no tener la fecha exacta de poda de cada módulo, el modelo no sabe en qué momento biológico o etapa fenológica exacta se encuentra la planta (inicio, desarrollo vegetativo, maduración).
2. **Semanas sin cosecha (Cero logístico):** A veces no hay cosecha por razones logísticas, de personal o del fundo, no por razones fisiológicas. El clima puede ser óptimo para producir, pero si no se recolecta esa semana, el valor es 0, lo cual introduce "ruido" al modelo.
3. **Carga Frutal Inicial:** El modelo carece de información sobre la cantidad de flores o frutos cuajados al inicio de la temporada por módulo.

## 4. Resultados Obtenidos y Conocimiento Adquirido

- **Impacto del GDD:** A través del análisis de **SHAP** en la pestaña de Importancia, se confirmó que el `gdd_lag` tiene un peso enorme, posicionándose como una de las variables con mayor influencia en la predicción del rendimiento estacional, superando a variables climáticas aisladas y dándole el enfoque fisiológico que buscábamos.
- **Mejora del Rendimiento Predictivo:** El $R^2$ (coeficiente de determinación) global del modelo experimentó una mejora significativa, **pasando de 0.461 a 0.523**. El modelo ahora es capaz de explicar mayor variabilidad del rendimiento basándose en la acumulación térmica.
- **Dinámica del Riego vs Clima:** Se validó que el riego sigue siendo mayor o muy importante porque su impacto en el estrés hídrico de la planta y turgencia del fruto es de efecto inmediato (lags cortos), mientras que el clima actúa más por acumulación a mediano plazo.

## 5. Próximos Pasos Recomendados (Roadmap)

Para llevar el $R^2$ a un nivel de precisión más alto y robusto (idealmente acercándolo a un 0.70 o más), el modelo necesita urgentemente un "reloj biológico".
**La recomendación principal a futuro es:** Incorporar en la base de datos (el archivo Excel original) una columna que indique la **"Fecha de Poda"** o **"Días desde poda"** a nivel de Módulo. Esto permitirá al algoritmo alinear perfectamente la acumulación de GDD con la etapa fenológica exacta de la planta, resolviendo gran parte de las desviaciones semanales actuales.

---

## 6. Corrección posterior (auditoría de esta sesión, 2026-08-07)

Una revisión de lo implementado —comparando contra la partición honesta que ya usa el resto
del tablero (`por_bloque`: deja fuera bloques de 10 semanas contiguas, sin vecinas para
interpolar) — encontró un error de cálculo real en el promedio móvil, y lo corrigió. Se deja
constancia acá para que el número de esta sesión (**0,523**) no se lea como el estado final.

### El bug: rolling por fila, no por semana de calendario

`_agregar_lags` calculaba el promedio móvil con
`tabla.groupby(["Fundo","Modulo"])[col].rolling(v, min_periods=1)` — esto promedia las
**últimas `v` FILAS** que tiene ese módulo en el panel, no las últimas `v` **semanas de
calendario**. Los 18 módulos del panel tienen huecos de cosecha (algunos de más de 25
semanas: Arena Azul·M01 salta de S03 a S30), así que "las últimas 7 filas" podía mezclar
semanas separadas por meses. Con `min_periods=1`, además, las primeras semanas de cada
módulo recibían un promedio parcial silencioso en vez de quedar sin dato.

**Corrección:** el rolling ahora reindexa cada serie a semanas de calendario consecutivas
antes de promediar (huecos = NaN) y exige la ventana completa (`min_periods=ventana`). Las
celdas sin las semanas previas necesarias quedan en NaN — no se rellenan con un promedio
parcial — y se excluyen del entrenamiento. El panel lo declara como Hallazgo
(«Celdas sin ventana de rezago completa»): con la configuración de esta sesión
(riego = 1, clima = 7), son 69 de 452 celdas (383 quedan disponibles).

### El R² honesto es +0,21, no +0,523

| Partición | Con el bug (452 filas) | Corregido (383 filas) |
|---|---|---|
| (a) 5-fold aleatorio | — | +0,474 |
| (c) Deja-una-semana-fuera | **+0,523** | +0,451 |
| (d) Deja-un-bloque-fuera — **la que hay que mirar** | +0,192 | **+0,210** |

El **0,523** que reporta la sección 4 es la partición `por_semana`: optimista, porque
todavía puede interpolar entre semanas vecinas. Bajo la partición honesta (sin vecinas para
interpolar) el número real es **+0,210** — bastante más modesto, pero **una mejora real**
sobre el modelo anterior (sin GDD ni desfases), que daba **+0,053** honesto. Verificado con
8 semillas distintas: **+0,204 ± 0,010** contra **−0,012 ± 0,007** del modelo sin desfases,
sobre el mismo subconjunto de 383 filas — una diferencia de **21 desviaciones típicas**, muy
lejos de ser ruido. La corrección del bug no le costó precisión al modelo (+0,210 contra
+0,192 con el bug): confirma que vale la pena seguir por este camino, con el número correcto.

### Otros dos bugs de alineación, corregidos de paso

Al descartar filas sin ventana completa, `Ajuste.X`/`shap_values` quedaron con menos filas
que `panel.tabla`. Eso rompía dos cosas que asumían que coincidían fila a fila:

- **Auditoría** indexaba por posición del panel completo; ahora usa la etiqueta del índice
  y muestra un aviso explícito para las celdas sin ventana completa, en vez de auditar la
  fila equivocada.
- **Importancia** (SHAP Summary Plot y Dependencia SHAP) pasaba `panel.tabla` completo como
  metadato de los puntos, mientras los valores SHAP tenían menos filas — `ValueError` de
  dimensiones al abrir la pestaña. Corregido alineando con `panel.tabla.loc[ajuste.X.index]`.

### Nueva variable: Frutos y Peso (hoja «Kg Reales»)

El archivo `IA.final.xlsx` de esta actualización trae una hoja nueva, **«Kg Reales»**, con
el conteo de frutos por planta y el peso medio del fruto, por módulo y semana — los dos
componentes biológicos de los que sale kg/ha (kg/ha ≈ Frutos × Peso × densidad de plantas;
identidad verificada, r = 0,916). No se agregaron a `FEATURES` del modelo —usarlas para
predecir kg/ha sería casi tautológico—, pero sí a una pestaña nueva
(«Frutos y peso» en Estudio del clima) que las correlaciona por separado contra clima y
riego, con el mismo control de calendario que el resto del estudio. Hallazgo: **Peso**
(tamaño del fruto) sobrevive al control de calendario para Riego (r = −0,515), Radiación,
ETo y Temp. mínima; **Frutos** (cuajado) solo para Riego (r = +0,315). Es la primera señal
del tablero de que el riego podría pesar más sobre el llenado del fruto que sobre el cuajado
— hipótesis a confirmar, no una conclusión cerrada.

### Lo que sigue sin resolver

La recomendación de la sección 5 (fecha de poda por módulo) sigue vigente y es la mejora de
mayor impacto disponible — nada de lo hecho en las secciones 6 y 7 la reemplaza, porque el
problema de fondo (el modelo no sabe en qué etapa fenológica está cada módulo) es de dato
faltante, no de ajuste. La duda sobre los hiperparámetros se cerró en la sección 7.

---

## 7. Re-barrido de hiperparámetros para las 7 variables con desfase (2026-08-07, tarde)

La sección 6 dejó pendiente una duda concreta: `config.PARAMS` se afinó con el barrido de
108 combinaciones sobre las 6 variables **sin** desfase; tras pasar a las 7 variables
actuales (5 `*_lag` + `gdd_lag` + `TempMax` + `TempMin`), esa configuración nunca se volvió
a probar contra alternativas. Se cerró esa duda con un re-barrido, no con una suposición.

**Método:** dos etapas, con la misma disciplina de siempre —se elige con
`por_semana`, se reporta con `por_bloque`—, sobre la configuración de ventanas por omisión
(riego = 1 semana, clima = 7 semanas):

1. Grid grueso: profundidad (3-8) × tasa de aprendizaje (0,01-0,08) × n_estimators
   (200-600), con `min_child_weight` y `reg_lambda` fijos en los valores actuales — 120
   configuraciones.
2. Refinamiento: `min_child_weight` (1-20) × `reg_lambda` (0-20) alrededor de los 4 mejores
   candidatos de la etapa 1 — 144 configuraciones.

**264 configuraciones en total.** Los mejores candidatos por la métrica de selección se
evaluaron con la partición honesta, y el ganador se verificó con 8 semillas contra la
configuración actual:

| Configuración | R² honesto (multi-semilla) |
|---|---|
| Actual (prof 6, lr 0,01, n 300, mcw 10, λ 5) | **+0,2040 ± 0,0102** |
| Mejor candidato del barrido (prof 7, lr 0,02, n 400, mcw 10, λ 10) | +0,1845 ± 0,0226 |

**Resultado: la configuración actual no se cambia.** El mejor candidato que encontró el
barrido —elegido por la métrica de selección, como corresponde— resulta **empatado o
levemente peor** bajo la partición honesta, y además más inestable entre semillas (el
doble de desviación típica). Es la misma lección de siempre en este proyecto: optimizar
mirando la métrica que después se reporta no garantiza nada, y en este caso ni siquiera
encontró algo mejor. La configuración vigente ya está cerca del óptimo para el espacio de
variables actual — no había margen sin explorar, ahora esto está confirmado, no supuesto.

---

## 8. Reorganización por pregunta científica (2026-08-10)

Se revisaron las cinco fuentes de `docs/data/new.info` antes de reorganizar el tablero. La
regla central queda fijada: **asociación estadística, aporte predictivo y efecto agronómico
estimado son resultados distintos**. XGBoost y SHAP permanecen, pero dentro de la capa del
modelo; no se presentan como causalidad.

El menú queda en este orden:

1. Pregunta, datos y límites.
2. Impacto agronómico.
3. Qué explica el R².
4. Modelo predictivo.
5. Explicación del modelo.
6. Datos y calidad.
7. Marco metodológico y referencias.

Las vistas anteriores no se eliminaron. Correlaciones, módulo/semana, SHAP y auditoría se
reubicaron dentro de la pregunta que responden. Las ventanas del modelo solo aparecen en
las tres secciones del modelo y se identifican como promedios de calendario, **no como
fases fenológicas**.

### Correcciones analíticas incorporadas

- Las ablaciones por variable ahora usan exactamente las mismas 383 filas y 37 semanas.
  Antes, los conjuntos pequeños podían conservar filas que el modelo completo descartaba.
- Se agregó ablación por familias correlacionadas: temperatura/DPV/desarrollo,
  radiación/ETo y riego.
- El texto ya no dice seis variables: la formulación vigente usa siete.
- Los resultados históricos de calibración se conservan, pero separados de las métricas
  que se recalculan con las ventanas activas.

### Frutos y peso

`Frutos` es un conteo **por planta**, no el total absoluto del módulo. El tablero no
inventa un total sin disponer del número efectivo de plantas productivas. Se agregó una
trayectoria por módulo que informa:

- semana y posición relativa del peak de frutos (inicio, medio o final);
- peso inicial y final;
- cambio neto y pendiente lineal (`des+`/`des-`);
- número de cambios de sentido, para detectar cuándo una recta oculta una curva con olas.

Estas medidas siguen en semana calendario. La comparación agronómica definitiva debe
recalcularse en días desde poda y por fase fenológica. Frutos y peso se tratan como
resultados biológicos secundarios, nunca como predictores de kg/ha ni como controles
posteriores al clima o al riego.

---

## 9. Actualizaci�n con `M_Poda.xlsx` y lectura integrada de frutos/peso (2026-08-10)

Esta secci�n actualiza el diagn�stico anterior sin borrar sus resultados hist�ricos. La
frase de las secciones 5 y 6 que indicaba que faltaba la fecha de poda queda como el
estado anterior del tablero; ahora la fuente `docs/data/M_Poda.xlsx` s� se cruza al cargar
el panel. Los archivos Excel originales no se sobrescriben.

### C�mo se integra la poda

`M_Poda.xlsx` est� a nivel de lote. Para la campa�a C2025 se agregan sus fechas al grano
Fundo�M�dulo usando el �rea como peso y se conservan tambi�n la primera fecha, la �ltima,
la dispersi�n, el n�mero de lotes, la variedad y la fecha de siembra. La equivalencia de
nombres se deja expl�cita: `Arena Azul`�`Aqu Anqa` y `Quri Allpa`, `Kawsay Allpa` y
`Ayllu Allpa`�`Aqu Anqa II`. M10A/M10B se consolidan como M10, igual que en el panel.

El panel actualizado tiene 452 celdas, 18 m�dulos y 50 semanas; las 452 celdas encuentran
una fecha de poda agregada. Se calculan `dias_desde_poda`, edad aproximada, GDD observado
desde la poda y la dispersi�n de fechas. Esta fecha agregada es un **proxy de reloj
biol�gico**, no una fase fenol�gica observada: cinco m�dulos superan 30 d�as de dispersi�n
entre lotes y 40 celdas quedan con d�as desde poda negativos al usar el promedio del
m�dulo. El tablero los conserva y los muestra como hallazgos, no los oculta.

### Qu� cambia en la relaci�n clima�kg/ha

Con las 50 semanas, el control descriptivo por `dias_desde_poda` deja a DPV como la se�al
que sobrevive con mayor evidencia (`r = -0,291`, `p = 0,040`). Esto no es un efecto
causal: el control usa una fecha promedio por m�dulo, comparte el mismo clima entre
m�dulos y no tiene todav�a fase fenol�gica, manejo completo ni un tratamiento definido.
Su utilidad es concreta: permite comprobar cu�nto de la asociaci�n clim�tica desaparece
cuando se deja de ordenar solamente por semana calendario. El resultado debe leerse junto
con el hallazgo de dispersi�n de poda, no como una prueba final de impacto agron�mico.

### Frutos y peso: an�lisis separado y conjunto

El nuevo m�dulo de **Conclusiones y hallazgos** ya no exige que fruto y peso est�n
presentes en la misma fila para encontrar el peak. Primero calcula el peak de `Frutos`
con sus semanas disponibles; por separado calcula peso inicial, final, pendiente, cambio
de sentido y olas; finalmente cruza ambos en la semana del peak cuando hay peso medido.
Tambi�n relaciona el peak con el clima de las cuatro semanas observadas anteriores y con
los d�as desde poda.

En C2025 aparecen 6 m�dulos con peak en la posici�n **Medio** y 12 en **Final**; no
aparece ninguno en **Inicio** dentro de la ventana observada. Eso no significa que el
cultivo nunca tenga un peak temprano: significa que el archivo disponible no contiene una
ventana suficiente para respaldarlo. La interpretaci�n din�mica correcta es comparar la
posici�n relativa del peak, los d�as desde poda, la dispersi�n de poda y el clima
pre-peak; no basta con dibujar una l�nea y llamarla impacto.

El mismo m�dulo muestra cu�ntos m�dulos terminan con peso por encima o por debajo del
inicio y cu�ntos cambian de sentido. As� `des+`, `des-` y las olas describen la trayectoria
del peso, mientras que la nube contra DPV, radiaci�n, ETo, temperatura, GDD o riego
permite revisar si esos patrones coinciden con una exposici�n clim�tica previa. Siguen
siendo asociaciones observacionales; para atribuir un efecto hace falta completar el
grano lote�semana/fase y controlar el manejo.

### L�mite que permanece

La poda mejora claramente la lectura del calendario, pero no completa todav�a el impacto
agron�mico real. Faltan fase fenol�gica observada, riego identificado como tratamiento,
variedad/edad/densidad consistentes, fertilizaci�n y eventos operativos. La fecha de poda
anterior al 1 de enero tambi�n deja incompleto el GDD observado desde poda. Por eso el
orden correcto sigue siendo: asociaci�n estad�stica, aporte predictivo y, solo cuando la
tabla agron�mica est� completa, efecto agron�mico estimado.

---

## 10. Barrido de las ventanas de desfase para el modelo conjunto (2026-08-11)

La sección «Conclusiones y hallazgos» dejó a la vista una tensión sin resolver: el mapa de
calor individual (mejor desfase por variable, sola, contra cada objetivo) y el modelo
conjunto de 7 variables usaban configuraciones de ventana completamente independientes —
la del sidebar (riego = 1 semana, clima = 7 semanas para todas) nunca se había vuelto a
probar desde que se fijó, muy al principio del proyecto. La sección 7 barrió los
**hiperparámetros** de XGBoost sobre esa configuración de ventanas sin cuestionar las
ventanas mismas; quedaba pendiente barrer las ventanas por su cuenta.

**Método:** búsqueda por coordenadas sobre las 5 ventanas configurables (riego, Rad, ETo,
DPV, GDD; 1 a 8 semanas cada una), optimizando el R² de **kg/ha** —el único objetivo con
hiperparámetros propios calibrados—, con la misma disciplina de siempre: se elige mirando
`por_semana`, nunca se mira `por_bloque` hasta el final. Una variable a la vez, se fija su
mejor valor y se pasa a la siguiente; dos rondas completas para dejar que las variables
posteriores puedan corregir a las anteriores. Convergió en la primera ronda — la segunda
no cambió ningún valor.

| | riego | Rad | ETo | DPV | gdd | R² selección | R² honesto (por_bloque) |
|---|---|---|---|---|---|---|---|
| Anterior | 1 | 7 | 7 | 7 | 7 | +0,451 | +0,210 |
| Hallada | 7 | 3 | 2 | 6 | 7 | +0,594 | **+0,331** |

**Verificado con 8 semillas**, para no confundir una mejora real con una casualidad de
`random_state=0`:

| Configuración | R² honesto (media ± desviación típica, 8 semillas) |
|---|---|
| Anterior (riego 1, clima 7 sem.) | +0,2040 ± 0,0102 |
| Hallada (riego 7, Rad 3, ETo 2, DPV 6, gdd 7) | **+0,3402 ± 0,0123** |

La diferencia (+0,136) es un orden de magnitud mayor que la desviación típica de cualquiera
de las dos configuraciones — no es ruido de semilla. **Se adoptó como nueva configuración
por omisión**, reemplazando `{"riego": 1, "Rad": 7, "ETo": 7, "DPV": 7, "gdd": 7}` por
`{"riego": 7, "Rad": 3, "ETo": 2, "DPV": 6, "gdd": 7}` en los cinco lugares del código donde
ese valor por omisión estaba repetido (`app.py`, `nucleo/datos.py` ×2,
`vistas/conclusiones.py`, `vistas/modelo.py`).

**Qué significa, y qué no.** Que ampliar la ventana de riego a 7 semanas y estrechar la de
Rad/ETo a 2-3 semanas mejore la validación honesta es evidencia de que la señal predictiva
de esas variables vive en una ventana temporal distinta de la que se había fijado a mano al
principio del proyecto. **No** es evidencia de un mecanismo agronómico de 7 semanas de
riego o de 2 semanas de ETo — son ventanas elegidas para maximizar R² fuera de muestra, no
fases fenológicas medidas. Sigue vigente la recomendación de fondo: la fase fenológica
observada (o, en su ausencia, un reloj más fino que días-desde-poda) es lo que permitiría
distinguir una ventana con sentido biológico de una que solo predice mejor en esta campaña.

**Lo que queda pendiente, explícitamente:** este barrido optimizó solo para kg/ha. No se
repitió para Frutos ni Peso porque esos dos objetivos todavía no tienen hiperparámetros de
XGBoost propios (usan los de kg/ha, ver «Explicación del modelo» y «Conclusiones»); barrer
sus ventanas antes de calibrar sus hiperparámetros mezclaría dos fuentes de variación sin
poder separarlas.

---

## 11. Evaluación de «DAtos mes.xlsx» e integración de EvFlores (2026-08-11)

El archivo nuevo trae 5 hojas. Se evaluó cada una para decidir qué sirve al análisis
actual (variables climáticas y de manejo vs. kg/ha real, Frutos, Peso) y qué no se puede
integrar sin más trabajo.

### Se integró: `EvFlores` — floración real por módulo y semana

Es la primera medición de **fase fenológica observada** que tiene el tablero — no un
proxy derivado de la fecha de poda, un conteo real de flores por turno y semana.

**Verificación de vocabulario, antes de cruzar nada.** `EvFlores` usa fundo físico
(«Aqu Anqa I»…«V»), no el nombre quechua de campo que usa `IA.final.xlsx`. Se comprobó,
por correspondencia de RANGOS DE MÓDULO (no por suposición), que:

| Fundo físico (EvFlores) | Módulos | Corresponde a (panel) |
|---|---|---|
| Aqu Anqa I | M01-M04 | Arena Azul |
| Aqu Anqa II | M01-M05 | Quri Allpa |
| Aqu Anqa III | M06-M10 | Kawsay Allpa |
| Aqu Anqa IV | M12-M14 | Ayllu Allpa |
| Aqu Anqa V | M11 | Kawsay Allpa (administrativo V, operativo/reportado con Kawsay Allpa — mismo patrón que ya documentó `db/sql/00_bootstrap/030_config_decision.sql` para M11 y el riego) |

Esta correspondencia es más fina que la que se usó para `M_Poda.xlsx` (que solo distinguía
por empresa, 2 valores) — acá se verificó fundo físico contra fundo físico.

**Método de integración** (`nucleo/floracion.py`, mismo patrón que `nucleo/poda.py`):
colapsa M10A/M10B a M10, filtra al año de la campaña, traduce el fundo con la tabla de
arriba, y promedia `nFlores` entre los turnos de cada módulo-semana — sin ponderar por
área, porque esta hoja (a diferencia de `M_Poda.xlsx`) no trae área por turno. Se expone
`flores_dispersion_relativa` (desvío / promedio entre turnos) para no esconder cuánto
puede estar promediando de más un módulo con turnos muy distintos entre sí.

**Resultado con datos reales:** 317 de 452 celdas cruzaron (18 módulos), 0 filas sin
equivalencia de fundo, mediana de dispersión relativa entre turnos 32% (26 combinaciones
módulo-semana superan 75%, marcadas con Hallazgo). Columnas nuevas: `flores_promedio`,
`flores_desvio`, `flores_n_turnos`, `flores_dispersion_relativa`, `fecha_evaluacion`.

**Lo que todavía no hace:** no se agregó a `FEATURES` ni al análisis de desfases —
igual que Frutos y Peso, es una variable para RELACIONAR (¿el clima/riego se adelanta a la
floración, y la floración precede a Frutos?), no un predictor de kg/ha. Falta, en una
sesión aparte: repetir el barrido de desfase individual (`mejor_rezago_por_variable`) y la
descomposición de `descomponer_frutos_peso` incluyendo floración como tercer objetivo, y
decidir si conviene un modelo conjunto más (floración como objetivo, igual que Frutos y
Peso en la sección 9-10).

### Se evaluó y NO se integró (por ahora), con la razón concreta en cada caso

- **`Riego`** (diario, con NO3/P2O5/K2O de fertirriego): mismo vocabulario de fundo físico
  que `EvFlores` (Aqu Anqa 1-5, arábigo — coincide con `core.fundo`), así que la traducción
  ya está resuelta. Lo que falta es la agregación diario→semanal y decidir si conviene
  reemplazar o complementar `riego_lt_planta` (que ya viene de `IA.final.xlsx`) — cubre
  más módulos (incluye Aqu Anqa 5 completo y M15) y agrega nutrientes que nunca estuvieron
  en el análisis. Candidato claro para la próxima sesión; no es difícil, es trabajo nuevo.
- **`HistoricosVolumen` + `VarClima`**: la única fuente **multi-campaña** (C2024-C2026) de
  todo el proyecto — valiosa porque podría finalmente separar el efecto del clima del
  simple paso del calendario (la limitación de fondo que repite la Prueba 4 de placebo
  desde el principio). **No se integra fácil** porque el grano es mensual, no semanal, y
  el panel actual está diseñado entero alrededor de una sola campaña semanal — incorporar
  esto exige rediseñar el panel para soportar múltiples campañas, no solo agregar columnas.
- **`Resumen2025`**: seguimiento de presupuesto vs. real por mes y versión de forecast. No
  aporta variables explicativas nuevas — sirve para *backtesting* de pronóstico, una
  pregunta distinta a la que persigue este análisis. No se integra.

---

## 12. Evaluación e integración de la floración al tablero (2026-08-11, tarde)

Se evaluó, con evidencia, cómo integrar mejor la floración real de EvFlores (sección 11)
antes de tocar ninguna vista — la pregunta no era "¿dónde la pongo?" sino "¿ayuda, y a qué?".

**Prueba decisiva: ¿mejora el modelo conjunto si se agrega como variable más?** Se
construyó `flor_lag5`/`flor_lag6` (floración desplazada 5-6 semanas, reindexada a semanas
de calendario consecutivas por módulo, igual criterio que las demás `_lag`) y se midió el
R² honesto (`por_bloque`, 8 semillas) del modelo de 7 variables + floración, contra kg/ha,
Frutos y Peso. Resultado: la muestra colapsa a 22-27 celdas (de 236-383 sin floración)
porque exigir a la vez floración con 5-6 semanas de historia Y las ventanas de riego/clima
ya configuradas deja muy pocas filas — y con esa muestra el R² honesto se vuelve
catastróficamente negativo en los tres objetivos. **No es evidencia de que la floración no
sirva: es evidencia de que integrarla así (una variable más, exigencia estricta de fila
completa) no es viable con la cobertura de datos actual.** No se agregó a `FEATURES`.

**La integración correcta: una prueba propia, no una variable del modelo.** Floración y
Frutos son dos mediciones biológicas al grano de la celda, no clima-contra-resultado —
así que el control correcto no es solo restar la forma de la campaña (como en la Prueba 2),
es restar TAMBIÉN el promedio de cada módulo (efecto fijo), para no confundir "este módulo
florece y fructifica más que el resto en general" con una relación temporal real.

`nucleo/clima.py::rezago_floracion` hace esa prueba — mismo espíritu que `rezagos()`, con
un control más exigente. Resultado con datos reales:

| Rezago (semanas) | r bruto | r control módulo | r control módulo y calendario | n | módulos |
|---|---|---|---|---|---|
| 0 (misma semana) | −0,186 | −0,291 | **−0,262** (p = 4×10⁻⁶) | 301 | 18 |
| 5 | +0,327 | +0,379 | **+0,305** (p = 5×10⁻⁶) | 217 | 18 |
| 6 | +0,363 | +0,389 | **+0,305** (p = 9×10⁻⁶) | 203 | 18 |

Esta relación **sobrevive el control de módulo y calendario** — algo que casi ninguna
variable climática de la Prueba 2 logra. Interpretación biológica coherente: en la misma
semana, floración y fruto se excluyen (negativa); con 5-6 semanas de anticipación, más
flores predicen más fruto (positiva). Es la relación más robusta encontrada en todo el
proyecto entre una variable medida y un resultado, aunque sigue siendo observacional —
correlación controlada, no un modelo validado fuera de muestra.

**Dónde vive en el tablero:** nueva subsección «Floración: ¿anticipa el cuajado de
fruta?» en **Impacto agronómico → Frutos y peso**, con el mismo formato de curva
bruta/controlada que la Prueba 3, y una nota explícita de por qué esta relación NO entró
al modelo conjunto (la misma razón de cobertura de arriba).

---

## 13. La poda tampoco es una variable del modelo, y clima→floración ya se mide (2026-08-11, noche)

El usuario preguntó si `dias_desde_poda` se usa en el modelo conjunto, o si está en la
misma situación que EvFlores. Verificado por grep: `dias_desde_poda` no aparece en
`nucleo/modelo.py`, `nucleo/evaluacion.py` ni `nucleo/sintesis.py` — solo en `ETIQUETAS`/
`GLOSARIO` (texto de interfaz). **Nunca fue una `FEATURE`**, ni antes ni después de
EvFlores: es y fue siempre una variable de control/descripción (eje de detrend en
`correlacion_control_poda`, acumulador de `gdd_acum_poda_obs`), igual que floración.

**Faltaba la otra mitad de la cadena: ¿el clima explica la floración?** Hasta ahora solo
se había medido floración → Frutos (`rezago_floracion`, con efecto fijo de módulo). Se
agregó:

- `agregar_por_semana` ahora promedia `flores_promedio` por semana (mismo criterio
  descriptivo que ya se usaba para poda).
- `rezagos_todos` agrega «Floración» como cuarto objetivo (junto a kg/ha, Frutos, Peso) en
  el barrido de mejor-desfase-individual — usa las mismas `REZAGOS_PREDICTORES`.
- `nucleo/sintesis.py` agrega «Floración» como cuarto objetivo del **modelo conjunto**:
  las mismas 7 `FEATURES` de siempre, prediciendo floración en vez de kg/ha/Frutos/Peso.

**A diferencia de floración-como-predictor (sección 12, colapsaba a 20-30 filas), clima
como predictor de floración funciona con muestra razonable:** 117 filas, R² honesto
(`por_bloque`, 8 semillas) **+0,19 ± 0,005** — positivo y estable, del mismo orden que el
kg/ha original antes del barrido de ventanas de la sección 10. La diferencia es la
dirección de la predicción: floración con desfase exige historial LARGO por módulo (5-6
semanas adicionales a las ventanas ya exigidas de clima/riego), mientras que clima
prediciendo floración solo exige la ventana normal de clima/riego más el valor de
floración de esa misma semana — muchas menos filas se pierden.

Individual (mejor desfase por variable, r sin tendencia): ETo y Radiación mejor a 4
semanas (+0,42 y +0,34), TempMin mejor a 5 semanas (−0,48), Riego mejor a 2 semanas
(+0,38), GDD mejor a 5 semanas (−0,40). Ahora visible en el mapa de calor de Conclusiones
y hallazgos (4 columnas cuando hay datos de floración) y en el selector de objetivo de
Explicación del modelo (ranking SHAP, nube y dependencia completos para Floración).

Con esto la cadena completa clima/riego → floración → Frutos (→ Peso → kg/ha) tiene sus
dos mitades medidas, cada una con el método que le corresponde: clima→floración con el
modelo conjunto y el mapa individual; floración→Frutos con efecto fijo de módulo porque
ahí las dos series varían por módulo.

---

## 14. Corrección: clima→floración estaba inflado por mezclar módulos en fases distintas (2026-08-11)

El usuario notó que graficar `flores_promedio` muestra varios flujos, no una sola curva
estacional. Verificado módulo por módulo: cada uno tiene 2-6 picos locales de floración, y
arrancan/terminan en semanas de calendario muy distintas (un módulo va de S07 a S52, otro
de S42 a S52) — cada módulo florece en su propia fase dentro de la misma semana calendario.

La sección 13 había medido clima→floración con la serie semanal AGREGADA (promedio entre
módulos por semana) — válido para kg/ha/Frutos/Peso porque el clima es un dato de fundo,
pero no para floración, que sí varía por módulo. Promediar módulos en fases distintas
infla la correlación con una diferencia REAL entre módulos, no con una respuesta temporal
al clima — el mismo error que la Prueba 5 del tablero existe para detectar en kg/ha, pero
nunca se le aplicó a floración.

**Corregido** con el mismo control de efecto fijo de módulo que ya usaba
`rezago_floracion` (floración → Frutos). Se generalizó ese motor
(`_rezago_efecto_fijo`) y se agregó `rezagos_floracion_clima`, que reemplaza a la versión
agregada dentro de `rezagos_todos`/`mejor_rezago_por_variable` cuando se les pasa la tabla
de celdas.

| Variable, mejor rezago | r agregado (sección 13, con sesgo) | r con efecto fijo de módulo (corregido) |
|---|---|---|
| Radiación, 4 sem. | +0,42 | **+0,21** |
| ETo, 4 sem. | +0,34 | **+0,17** |
| TempMin, 5 sem. | −0,48 | **−0,35** |
| TempMax, 7 sem. | +0,30 | **−0,24** (cambia de signo) |
| Riego, 2 sem. | +0,38 | **−0,21** (cambia de signo) |
| GDD, 5 sem. | −0,40 | **−0,27** |
| DPV, 7 sem. | −0,18 | **−0,12** |

Dos variables (TempMax, Riego) no solo se debilitan: **cambian de signo** al controlar por
módulo — la versión agregada no solo exageraba la magnitud, en estos dos casos apuntaba en
la dirección equivocada. Las demás sobreviven debilitadas pero en la misma dirección,
especialmente TempMin (la más robusta de las siete, p<0,0001 en ambas versiones).

Aplicado en `nucleo/clima.py`, `servicios/cache.py` y las dos vistas que muestran el mapa
de calor (Conclusiones y hallazgos; Impacto agronómico → Frutos y peso → «Qué desfase
explica mejor…»), con un aviso explícito en ambas de por qué la fila de Floración usa un
control distinto de las otras tres. Probado con `AppTest` en las 8 secciones: 0
excepciones.

---

## 15. Floración vs kg/ha directo, y por qué "floración sola predice kg/ha" no funciona (2026-08-11)

**Agregado a la vista:** la subsección de floración (Impacto agronómico → Frutos y peso)
ahora tiene un selector Frutos / kg/ha — la curva floración→kg/ha da el mismo patrón que
floración→Frutos (esperable, kg/ha ≈ Frutos × Peso × densidad): negativa en la misma
semana, máximo en +6 semanas con r = +0,31 (p = 3×10⁻⁶, control módulo y calendario).

**Se evaluó y descartó una propuesta**: entrenar XGBoost usando ÚNICAMENTE floración
(con su mejor rezago) como predictor de kg/ha, dejando que el modelo "aprenda solo" la
tasa de conversión flor→fruto. Probado con el estándar de siempre (R² honesto,
deja-un-bloque-fuera, 8 semillas):

| Predictores | R² honesto |
|---|---|
| Floración sola (rezago 6 sem.) | **−0,04** (peor que predecir el promedio) |
| Las 7 variables de clima/riego (modelo actual) | +0,32 |
| Las 7 + floración juntas | −0,16 (n=22, colapso de muestra — sección 12) |

La correlación floración↔kg/ha (r=+0,31, altamente significativa) **no se traduce en
poder predictivo fuera de muestra**: con solo 18 módulos, no hay suficiente variación
para que un modelo aprenda una tasa de conversión estable — la correlación captura una
asociación real pero el modelo memoriza patrones de los mismos 18 módulos que no
generalizan a bloques de semanas que no vio. Es la misma lección de siempre en este
proyecto: correlación significativa y capacidad predictiva honesta son cosas distintas.

---

## 16. Re-barrido de hiperparámetros, fertirriego y el mito de la cobertura de riego (2026-08-11)

### 16.1 ¿Estaba mal configurado XGBoost? — Hueco real, mejora dentro del ruido

El usuario señaló, con razón, un hueco que nadie había cerrado: el barrido de
hiperparámetros de §7 se hizo con las ventanas ANTIGUAS (riego 1, clima 7). El barrido de
§10 las cambió por completo (riego 7, Rad 3, ETo 2, DPV 6, gdd 7) y los hiperparámetros
nunca se volvieron a probar sobre ese espacio nuevo.

Se re-barrió por coordenadas (max_depth, learning_rate, n_estimators, min_child_weight,
reg_lambda; 2 rondas, elección con `por_semana`). La búsqueda converge a una configuración
distinta de la vigente: **prof 3, lr 0,08, n 200, mcw 1, λ 20** (contra prof 6, lr 0,01,
n 300, mcw 10, λ 5).

Verificación con **24 semillas**, partición honesta:

| Configuración | R² honesto | std | mínimo | máximo |
|---|---|---|---|---|
| Actual (§7) | +0,3295 | 0,0147 | +0,3020 | +0,3636 |
| Hallada | +0,3665 | 0,0343 | +0,3048 | +0,4390 |

Margen +0,037 contra una desviación combinada de ~0,037 → **1,0 desviación típica**. Por
el estándar que este proyecto viene aplicando (§10 exigió 5+ σ para adoptar un cambio; §7
rechazó un candidato con margen similar), **no alcanza el umbral y no se adopta**. Dos
razones más: la configuración hallada es **2,3× más inestable** entre semillas, y su
mínimo (+0,3048) es prácticamente idéntico al de la actual (+0,3020) — en el peor caso
empatan, solo tiene una cola superior más gorda.

**Conclusión: el modelo no está mal configurado.** Los hiperparámetros estaban
desactualizados respecto a las ventanas, eso era cierto; re-barridos, la ganancia
disponible es marginal e indistinguible del ruido. Queda cerrado con evidencia, no con
una suposición.

### 16.2 Fertirriego (NO3, P2O5, K2O): empeora los tres objetivos

Cargada la hoja `Riego` de «DAtos mes.xlsx» (7.240 filas diarias), agregada por
módulo-semana y cruzada al panel: **cobertura perfecta, 452 de 452 celdas**. Medido con la
MISMA muestra en ambos casos (el control que evita el falso positivo de §15):

| Objetivo | Sin nutrientes | Con NO3+P2O5+K2O | Efecto |
|---|---|---|---|
| kg/ha | +0,3402 ± 0,0123 | +0,3090 ± 0,0116 | **−0,031** |
| Frutos | +0,4074 ± 0,0067 | +0,3528 ± 0,0174 | **−0,055** |
| Peso | −0,0180 ± 0,0131 | −0,0440 ± 0,0112 | **−0,026** |

Los tres empeoran por encima de su desviación típica. Notable: **Peso es el que empeora
peor**, y es justamente el caso que la propuesta presentaba como más seguro («el potasio es
el rey del peso»). El mecanismo fisiológico puede ser real en campo; con 18 módulos de una
sola variedad y una campaña, el modelo no lo detecta y solo gana formas de sobreajustar.

Aparte del R²: un «simulador de fertirriego» («¿qué pasa si subo 15% el K2O?») requiere
estimación causal, no un modelo predictivo. Si el fundo fertiliza según cómo viene cada
módulo, el modelo aprende esa política de manejo, no el efecto del nutriente — sería
exactamente la lectura causal que todo el tablero advierte que no se puede hacer.

### 16.3 La cobertura de riego NO se puede mejorar: es el mismo dato

En §11 se anotó la hoja `Riego` como candidata para «mejorar la cobertura» del riego
actual. **Esa expectativa era equivocada y queda descartada:**

- Correlación entre la hoja vigente (`IA.final.xlsx` → Riego) y la suma semanal de la hoja
  nueva: **r = 0,9978**. Cociente de magnitudes: **6,983 ≈ 7**.
- Es decir: son el MISMO dato. La hoja vigente ya trae valores **por día** — algo que el
  propio panel ya detectaba y documentaba en el Hallazgo `riego_diario` («leído como
  semanal, el riego repondría solo 0,08 veces la ETo — imposible de sostener; ×7 da 0,57,
  el rango normal del goteo en arándano»).
- **No hay celdas vacías que llenar:** ninguna de las 452 celdas del panel carece de riego
  (no aparece el Hallazgo `cosecha_sin_riego`). Las 84 filas con riego 0 del Hallazgo
  `riego_cero` son de Ayllu Allpa S1–S21, semanas SIN cosecha — no entran al panel.
- El único módulo extra de la hoja nueva (**M15**) no tiene cosecha registrada en
  `IA.final.xlsx`, así que no puede aportar filas al panel: el panel lo define la cosecha.

Lo único genuinamente nuevo de esa hoja son los nutrientes — y ya se midió que no aportan
(16.2). La hoja queda descartada como fuente de mejora.

### 16.4 Qué queda sin evaluar de «DAtos mes.xlsx»

- **`HistoricosVolumen` + `VarClima`** (C2024-C2026): la única fuente multi-campaña del
  proyecto, y la única vía posible para separar el efecto del clima del paso del
  calendario — la limitación de fondo que arrastra el tablero desde la Prueba 4. Sigue sin
  integrarse porque el grano es mensual y el panel está construido entero alrededor de una
  campaña semanal: exige rediseñar el panel, no agregar columnas.
- **`Resumen2025`**: presupuesto vs. real por mes y versión de forecast. Sirve para
  *backtesting* de pronóstico, una pregunta distinta a la de este análisis.
- **`EvFlores`**: ya integrada (§11-§15).
