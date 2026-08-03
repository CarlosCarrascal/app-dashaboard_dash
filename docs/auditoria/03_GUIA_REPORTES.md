# Guía para el área de Reportes · BD_AQUANQA_26

**Fecha:** 2026-08-02
**Para:** área de Reportes / Power BI
**Propósito:** qué se puede consumir hoy, qué advertencias tiene cada objeto, y qué cambia
con la migración a PostgreSQL.

---

## 0 · Lo que necesitas saber antes de seguir leyendo

**1 · Los nombres de las 40 consultas se preservan.** En PostgreSQL serán vistas con el
mismo nombre y las mismas columnas. Power BI seguirá encontrando lo que busca.

**2 · Seis consultas están rotas hoy.** Si tu tablero consume alguna, está mostrando caché
o nada. La lista está en §3.

**3 · Algunos números van a cambiar tras migrar — y eso es correcto.** Hay cifras que hoy
son incorrectas (totales inflados, kilos fantasma). Corregirlas hará que un tablero muestre
menos kilos o menos filas. **Ese cambio es la corrección, no un error de la migración.**
La lista completa está en §5, con la magnitud esperada de cada cambio.

**4 · Hay 7 verificaciones que conviene ejecutar antes de migrar** (§4). Sirven para saber
qué tableros dependen de qué, y para tener una foto del "antes" contra la que comparar.

---

## 1 · Inventario de las 40 consultas · contrato de interfaz

Esto es lo que Power BI puede consumir hoy. `Filas` es el conteo real verificado.

### Familia `01xx` – `02xx` · Evaluaciones

| Consulta | Filas | Grano | Columnas expuestas |
|---|---|---|---|
| `0101_Diametros` | 94.236 | planta/fecha | 16 |
| `0102_CantRamas` | 5.530 | planta/fecha | 12 |
| `0104_PromFlores` | 9.040 | lote/semana | 13 |
| `0105_AcumFlores` | 867 | lote/año | 5 |
| `0106_RaFloYem` | 18.778 | lote/semana/evaluación | 10 |
| `0107_YemasAb` | 9.029 | lote/semana | 9 |
| `0108_diam` | **0** | — | 9 |
| `01_Flores_C2025` | **487.368** | inflado ×54 | 11 |
| `0201_Flores` | 43.457 | planta/fecha | 18 |
| `0202_FloresTurno` | 2.648 | turno/semana | 11 |

### Familia `03xx` – `04xx` · Estados de fruto

| Consulta | Filas | Grano | Columnas |
|---|---|---|---|
| `0301_ConteoEstados` | 18.714 | planta/fecha | 26 |
| `0302_ConteoAjustado` | 2.802 | turno/semana | 15 |
| `0303_ConteoEstados_Turno` | 14.010 | turno/semana/estado | 11 |
| `0304_ConteoEst_Flo_Turno` | 16.658 | turno/semana/estado | 11 |
| `0305_Brotes_Ramas` | 8.910 | planta | 10 |
| `0306_FrutosFlores` | 27.754 | lote/semana/tipo | 8 |
| `0307_EstadosFlores` | 16.239 | lote/semana | 7 |
| `0401_Estados_planta` | 18.714 | planta/fecha | 17 |
| `0402_ConteoBrotes` | **ROTA** | — | — |

### Familia `H0xxx` · Cosecha, packing y clima

| Consulta | Filas | Grano | Columnas |
|---|---|---|---|
| `H0100_Resumen_kgCosecha` | 30.812 | lote/fecha | 11 |
| `H0101_ResumenHistoricos` | 30.624 | lote/paña | 19 |
| `H0102_Producciondiaria` | 30.446 | lote/fecha | 13 |
| `H0103_ResModulo` | 104 | módulo/campaña/año | 7 |
| `H0104_FechaFinCosecha` | 661 | lote/campaña | 18 |
| `H0105_RendTurno_paña` | 3.442 | turno/paña | 11 |
| `H0201_PesoBaya_Elifab` | 16.971 | lote/clase | 9 |
| `H0501_VariablesClima` | 155.588 | timestamp | 18 |
| `H0502_Temperatura_variacion` | 1.603 | periodo | 7 |

### Familia `R08xx` – `R09xx` · Forecast

| Consulta | Filas | Grano | Columnas |
|---|---|---|---|
| `R0101_KgCosecha` | **ROTA** | — | — |
| `R0801_ResCampaña` | 29 | módulo/versión | 8 |
| `R0801_Forecast_Campaña_SemMes` | **ROTA** | — | — |
| `R0802_ResumenAño` | **ROTA** | — | — |
| `R0901_Forecas_SemAc` | 6.994 | lote/semana | 15 |
| `R0902_Forecast_Sem_vs_Camp` | **ROTA** | — | — |
| `R0903_Forecast_FrtsTotal` | 22.272 | lote/semana | 16 |

### Utilitarias

| Consulta | Filas | Grano | Columnas |
|---|---|---|---|
| `M_EdadCultivo` | 860 | lote | 8 |
| `M_Lote_turno` | 860 | lote | 11 |
| `M_Mod` | 23 | módulo | 6 |
| `TPlantas` | 23 | fundo/módulo | 3 |
| `E` | **ROTA** | — | — |

**Total: 34 consultas ejecutables, 6 rotas.**

---

## 2 · Mapa de impacto inverso · qué se rompe si se toca cada tabla

Si el equipo de TI modifica una tabla, estas son las consultas afectadas — y por tanto los
tableros a revisar.

| Tabla | Consultas afectadas |
|---|---|
| **`M_Lotes`** | **33 de 40** |
| **`M_Time`** | **26 de 40** |
| `E02_ConteoFlores` | 11 |
| `E03_ConteoEstados` | 8 |
| `H01_ProdHistorica` | 7 |
| `M_Poda` | 7 |
| `E01_Ramas` | 5 |
| `R08_Forecast_Campaña` | 3 |
| `R09_Forecast_Semanal` | 3 |
| `H05_Clima` | 2 |
| `E04_Brotes` | 1 |
| `H00_VolumenCampo` | 1 |
| `H02_BDElifab` | 1 |
| `M_EquivalenciaElifab` | 1 |
| `E05_DiametrosBayas` | **0** |
| `M_Evaluadores` | **0** |
| `M_nMuestra` | **0** |
| `Errores de pegado` | **0** |

**Regla práctica:** cualquier cambio en `M_Lotes` o `M_Time` requiere validar el 80% de los
tableros. Son las dos dimensiones que sostienen el modelo.

El detalle consulta por consulta está en `evidencia\05_linaje_dependencias.txt` §2.

---

## 3 · Advertencias por consulta

Ordenadas por gravedad. Si tu tablero usa alguna de estas, léela.

### Nivel 1 · Consultas que NO devuelven datos hoy

| Consulta | Qué pasa | Qué ver en el tablero |
|---|---|---|
| `0402_ConteoBrotes` | rota: busca `E04_ConteoBrotes`, la tabla es `E04_Brotes` | error de actualización o datos congelados |
| `R0101_KgCosecha` | rota: busca `R01_VolumenCampo`, la tabla es `H00_VolumenCampo` | ídem |
| `R0802_ResumenAño` | rota: busca `R0901_ResCampaña`, existe `R0801_ResCampaña` | ídem |
| `R0801_Forecast_Campaña_SemMes` | rota: `M_Time` no tiene `CampProAra` ni `Trimestre` | ídem |
| `R0902_Forecast_Sem_vs_Camp` | rota: `R08` no tiene columna `KG` | ídem |
| `E` | rota: `Actividad` no existe en E02/E03 | es un borrador, descartable |
| **`0108_diam`** | **ejecuta pero devuelve 0 filas** | **visual vacío** |

**`0108_diam` merece atención especial.** No lanza error, así que Power BI la actualiza sin
quejarse — pero devuelve cero filas. Un visual construido sobre ella aparece vacío y es
fácil atribuirlo a un filtro mal puesto.

### Nivel 2 · Consultas con totales incorrectos

| Consulta | Problema | Efecto sobre las medidas |
|---|---|---|
| **`01_Flores_C2025`** | **inflado ×54** (487.368 vs 9.040 reales) | `SUM` y `COUNT` inflados ×54. **`AVG` sigue correcto** |
| `H0100_Resumen_kgCosecha` | incluye fila basura de 930.662,1 kg | total sobreestimado; el kilaje no aparece en ningún corte |
| `H0101_ResumenHistoricos` | incluye 2 filas basura (995.333,2 kg) | ídem |
| `H0501_VariablesClima` | 2.079 mediciones duplicadas | `SUM(Lluvia)` sobreestimado, `AVG(Temp)` sesgado |
| `0101_Diametros` y descendientes | duplicados de `E01_Ramas` | `SUM` inflado ~24%, `AVG` sesgado +0,83% |

**Sobre `01_Flores_C2025`:** es el caso más engañoso de todos. Los promedios son correctos
—el promedio de un valor repetido 54 veces es el mismo valor— y solo los totales y conteos
están mal. Un tablero puede verse perfectamente sano.

### Nivel 3 · Consultas con columnas vacías

| Consulta | Columnas siempre NULL | Causa |
|---|---|---|
| `0101_Diametros` | `Turno`, `KeyMap`, `NPlantas`, `Area` | H-01: join de vocabularios incompatibles |
| `0102_CantRamas` | `Turno`, `KeyMap` | heredado de `0101_Diametros` |
| `0106_RaFloYem` | `kk` en 53 lotes | `KeyMap` nulo |

**Si tienes un segmentador de Turno sobre datos de ramas, muestra una sola categoría vacía.**
El dato de ramas y diámetro no es analizable por turno hoy.

### Nivel 4 · Filtros fijos embebidos en el SQL

Estas consultas tienen un filtro escrito dentro del SQL, no como parámetro. **No se puede
cambiar desde Power BI.**

| Consulta | Filtro fijo | Consecuencia |
|---|---|---|
| `0201_Flores` | `WHERE M_Poda.Campaña = "C2026"` | solo C2026, para siempre |
| `0202_FloresTurno` | heredado de `0201_Flores` | ídem |
| `0304_ConteoEst_Flo_Turno` | heredado en la rama de flores | **flores solo C2026, estados sin filtro** |
| `H0105_RendTurno_paña` | `HAVING Campaña = "C2025"` | solo C2025 |
| `R0901_Forecas_SemAc` | `WHERE Campaña IN ("C2025","C2026")` | solo esas dos campañas |
| `M_EdadCultivo` | `HAVING Lote <> "L000"` | excluye lote de prueba (correcto) |

**`0304_ConteoEst_Flo_Turno` tiene un desequilibrio importante:** su rama de flores está
limitada a C2026 pero la de estados no. En un tablero histórico, las flores desaparecen
antes que los estados y la serie fenológica queda incompleta sin señal de que falta algo.

### Nivel 5 · Advertencias de interpretación

| Consulta | Advertencia |
|---|---|
| **`R08_Forecast_Campaña`** (y derivadas) | **acumula 15 versiones de proyección. Sumar sin filtrar `Version` mezcla escenarios: los 648 M de kg no son producción, son 15 escenarios sumados** |
| **`R09_Forecast_Semanal`** (y derivadas) | **acumula 46 versiones. Mismo problema** |
| `R0901_Forecas_SemAc` | filtra por semana pero **no desambigua `S27`, `S27_v2`, `S27_v3`** — la semana 27 aparece 3 veces |
| `R0903_Forecast_FrtsTotal` | el `INNER JOIN` **descarta 26.096 filas (54%)** en silencio |
| `0105_AcumFlores` | suma **promedios**, no un total de flores. Es un índice comparativo, no una cantidad |
| `H0101_ResumenHistoricos` | `FecPon` solo tiene sentido dividido entre `SUM(KG)`. En crudo no significa nada |
| `M_EdadCultivo` | usa `Now()`: **el resultado cambia cada día**. No es reproducible |
| `H0103_ResModulo` | agrupa por `año` y `Campaña` a la vez: **parte los totales de campaña cuando cruza el fin de año** |
| `0306_FrutosFlores` | mezcla `Sem` y `SEvConteo` en la misma columna `Semana` — las ramas no están alineadas |
| `0307_EstadosFlores` | une `Sem` contra `SEvConteo`: emparejamiento incorrecto donde difieren |

**Sobre las versiones de forecast — la advertencia más importante de esta sección.**

Toda medida sobre `R08` o `R09` **debe filtrar una versión**. Sin ese filtro:

| Medida sin filtrar | Valor | Qué es realmente |
|---|---|---|
| `SUM(R08.[KG Exp])` | 648.044.713 kg | suma de 15 escenarios del mismo periodo |
| `SUM(R09.Kg)` | 51.083.049 kg | suma de 46 escenarios |

Para contexto: la cosecha real de las 5 campañas suma ~32,45 M kg. Un forecast de 648 M no
es un pronóstico optimista, es un artefacto de sumar versiones.

---

## 4 · Checklist · 7 verificaciones antes de migrar

Ejecutar en Power BI y guardar los resultados. Sirven para dos cosas: saber qué tableros
dependen de qué, y tener la foto del "antes" contra la que comparar después.

### V-1 · Inventariar qué consultas consume cada informe

**Cómo.** En cada archivo `.pbix`: *Inicio → Transformar datos → Configuración del origen
de datos*. Anotar cada consulta de Access referenciada.

**Entregable.** Una tabla `informe → consultas que usa`.

**Por qué.** Sin esto no se sabe qué informes se ven afectados por cada corrección. Es la
base de todo lo demás.

### V-2 · Identificar informes que dependen de las 6 consultas rotas

**Cómo.** Cruzar el inventario de V-1 contra la lista de §3 nivel 1.

**Qué esperar.** Esos informes están mostrando datos congelados de la última actualización
exitosa. **Verificar la fecha de última actualización correcta de cada uno** — puede ser de
hace meses.

**Por qué.** Son el riesgo más alto: un tablero que muestra datos viejos sin indicarlo es
peor que uno que falla visiblemente.

### V-3 · Detectar informes que usan `0108_diam`

**Cómo.** Buscar `0108_diam` en el inventario. Abrir los informes que la usen.

**Qué esperar.** Visuales vacíos. Devuelve 0 filas sin lanzar error.

### V-4 · Congelar los totales actuales de kilos

**Cómo.** Para cada informe de producción, anotar el `SUM(KG)` total y por campaña.

**Valores de referencia** (`evidencia\04_metricas_validacion.txt`):

| Métrica | Valor actual | Tras migrar |
|---|---|---|
| `H00 SUM(KG)` crudo | 33.381.134,66 | **32.450.472,60** |
| `H01 SUM(KG)` crudo | 33.441.319,22 | **32.445.986,02** |

**Por qué.** Tras la migración estos totales **bajan** en ~930 mil y ~995 mil kg
respectivamente. Es la corrección de H-06 (filas de subtotal). Sin este registro previo, la
bajada parecerá pérdida de datos.

### V-5 · Documentar los conteos de filas actuales

**Cómo.** Para cada consulta que uses, anotar el número de filas que Power BI importa.

**Los que van a cambiar más:**

| Consulta | Ahora | Tras migrar | Motivo |
|---|---|---|---|
| `01_Flores_C2025` | 487.368 | **9.040** | corrección de H-05 |
| `0101_Diametros` | 94.236 | **71.095** | deduplicación H-03 |
| `H0501_VariablesClima` | 155.588 | **153.413** | deduplicación H-08 |

**Por qué.** La caída de `01_Flores_C2025` es de 98%. Sin explicación previa, se lee como
pérdida masiva de datos.

### V-6 · Revisar segmentadores de Turno sobre datos de ramas

**Cómo.** Buscar visuales que segmenten por `Turno` usando `0101_Diametros`, `0102_CantRamas`
o `0106_RaFloYem`.

**Qué esperar.** Una única categoría vacía (H-01).

**Tras migrar.** El turno se poblará correctamente. **Los visuales que hoy muestran una
categoría pasarán a mostrar varias** — un cambio visible que conviene anticipar.

### V-7 · Verificar filtros de versión en tableros de forecast

**Cómo.** En cada informe que use `R08` o `R09`, comprobar si hay un filtro sobre `Version`.

**Si NO lo hay: el tablero está sumando todas las versiones.** Los kilos mostrados no son un
pronóstico, son la suma de 15 (o 46) escenarios del mismo periodo.

**Es la verificación de mayor impacto potencial de las siete.** Un tablero de forecast sin
filtro de versión puede estar mostrando cifras 10 o 20 veces mayores que el pronóstico real,
y nada en el visual lo indica.

---

## 5 · Compromiso de compatibilidad

### Lo que NO cambia

**Nombres de las 40 consultas.** Cada una existirá como vista en PostgreSQL con el mismo
nombre. Las que hoy tienen `ñ` o acentos (`R0801_ResCampaña`, `R0802_ResumenAño`,
`H0105_RendTurno_paña`, `R0801_Forecast_Campaña_SemMes`, `R0902_Forecast_Sem_vs_Camp`) se
conservan **con su grafía actual** en la vista de compatibilidad.

**Nombres de columnas expuestas.** Las columnas que hoy devuelve cada consulta seguirán
llamándose igual, incluidas las que tienen espacios (`Ramas <5`, `# Ramas`, `KG Exp`).

**Grano de cada consulta.** Lo que hoy es una fila por lote/semana seguirá siéndolo.

### Lo que SÍ cambia — y por qué

Cada cambio corrige un defecto documentado. **Ninguno es opcional**: mantener el
comportamiento actual sería mantener el error.

| # | Consulta | Cambio | Magnitud | Hallazgo |
|---|---|---|---|---|
| 1 | `01_Flores_C2025` | filas | 487.368 → **9.040** (−98,1%) | H-05 |
| 2 | `0101_Diametros` | filas | 94.236 → **71.095** (−24,6%) | H-03 |
| 3 | `0101_Diametros` | `Turno` deja de ser NULL | 94.236 NULL → **0** | H-01 |
| 4 | `0102_CantRamas` | `Turno`, `KeyMap` se pueblan | — | H-01 |
| 5 | `0108_diam` | pasa de 0 filas a devolver datos | 0 → **>0** | H-01 |
| 6 | `H0100_Resumen_kgCosecha` | `SUM(KG)` baja | −930.662,06 kg | H-06 |
| 7 | `H0101_ResumenHistoricos` | `SUM(KG)` baja | −995.333,20 kg | H-06 |
| 8 | `H0501_VariablesClima` | filas | 155.588 → **153.413** | H-08 |
| 9 | `H0501_VariablesClima` | `SUM(Lluvia)` baja | pendiente de cuantificar | H-08 |
| 10 | `0402_ConteoBrotes` | pasa de rota a funcional | — | H-04 |
| 11 | `R0101_KgCosecha` | pasa de rota a funcional | — | H-04 |
| 12 | `R0802_ResumenAño` | pasa de rota a funcional | — | H-04 |
| 13 | `E01_Ramas AVG(Diametro)` | 10,978 → **10,887** | −0,83% | H-03 |

### Cómo explicar estos cambios

Si alguien pregunta por qué el tablero muestra menos kilos:

> *"El total anterior incluía 1.925.995 kg en tres filas de subtotal de Excel que se
> importaron junto con los datos. No tenían fundo, módulo, lote ni fecha, así que nunca
> aparecían al segmentar — solo en el total general. Por eso el total no cuadraba con la
> suma de las partes. Ahora sí cuadra."*

Y si preguntan por la caída de `01_Flores_C2025`:

> *"Las 487.368 filas eran 9.040 evaluaciones reales, cada una repetida 54 veces por un
> error de join. Los promedios eran correctos, pero cualquier total o conteo estaba
> multiplicado por 54."*

### Lo que queda pendiente de decisión

Tres cambios **no se aplicarán** sin confirmación del negocio:

| # | Qué | Quién decide |
|---|---|---|
| 1 | `R0902_Forecast_Sem_vs_Camp`: qué columna de kilos usar de `R08` | Planeamiento |
| 2 | `R0801_Forecast_Campaña_SemMes`: definir `CampProAra` (fechas de corte de campaña) | Planeamiento |
| 3 | `H00` vs `H01`: cuál es la fuente de verdad de cosecha | Agronomía |

---

## 6 · Las 3 tablas sin consumo · oportunidad de análisis

Hay **4.905 filas de datos capturados en campo que nunca llegan a un tablero**. No es deuda
técnica: es información que se recoge y se pierde.

### `E05_DiametrosBayas` — 4.193 filas

**Qué contiene.** Diámetro de baya medido en campo, por módulo/turno/lote/cortina/hilera y
fecha. `AVG(Diametro)` = 19,885 mm. **Sin un solo nulo en ninguna columna** — es la tabla
más limpia de la base.

**Por qué importa.** El diámetro de baya es el **indicador directo de calibre comercial**.
`H02_BDElifab` clasifica la fruta en calibres de 12mm a 26mm+, y ese calibre determina el
mercado (China/USA pagan más, ácido va a industria, descarte es pérdida).

**La pregunta que permitiría responder:** *¿el diámetro medido en campo predice el calibre
que saldrá de packing?* Si la correlación es buena, se podría **comprometer volumen por
calibre con los clientes semanas antes de cosechar**.

Ventaja adicional: es la única tabla de evaluación que **trae `Turno` de origen**, así que
no depende del join que falla en H-01.

### `M_Evaluadores` — 31 filas

**Qué contiene.** DNI, nombres, código, zona y estado de los 31 evaluadores.

**Por qué importa.** Las tablas de evaluación guardan el DNI del evaluador en cada fila.
Cruzarlas permitiría medir la **variabilidad entre evaluadores**, que es una fuente de error
conocida en evaluación fenológica: dos personas contando la misma planta pueden diferir
significativamente.

**Las preguntas que permitiría responder:** ¿cuántas plantas evalúa cada uno? ¿los conteos
de alguno se desvían sistemáticamente del promedio de su zona? ¿la calidad mejora con la
antigüedad (`InicioLabores`)?

**Nota técnica.** El enlace debe hacerse por `DNI`, no por `Cod`. Hoy hay 2 DNI en
`E01_Ramas` sin registro en el maestro.

### `M_nMuestra` — 681 filas

**Qué contiene.** Cuántas muestras corresponden por lote y tipo de evaluación.

**Por qué importa.** Es la **referencia para validar cobertura de muestreo**. Cruzándola con
el conteo real de evaluaciones se sabría qué lotes se evaluaron con muestreo insuficiente —
y por tanto qué estimaciones son poco confiables.

**La pregunta que permitiría responder:** *¿este promedio de lote se calculó sobre suficientes
plantas como para ser representativo?* Hoy `0302_ConteoAjustado` expone `n` (plantas
evaluadas) pero no hay contra qué compararlo.

### Recomendación

Migrar las tres tablas y **exponerlas como fuentes disponibles** en el modelo de PostgreSQL,
aunque hoy ningún tablero las use. El coste de migrarlas es marginal; el coste de descubrir
dentro de un año que se perdieron es alto.

---

## 7 · Preguntas frecuentes

**¿Tengo que rehacer mis informes?**
No. Los nombres de consultas y columnas se preservan. Habrá que reapuntar el origen de datos
de Access a PostgreSQL, pero las consultas del modelo no cambian.

**¿Por qué van a bajar los kilos?**
Porque hoy incluyen 1.925.995 kg de filas de subtotal de Excel sin fundo, módulo ni fecha
(H-06). Nunca aparecían al segmentar, solo en el total. Ver §5.

**¿Puedo seguir usando Access mientras tanto?**
Sí. La migración no toca la base original. Access sigue funcionando hasta que se decida
cortar.

**¿Qué pasa con las consultas rotas?**
Cuatro se corrigen sin intervención del negocio y quedarán funcionales. Dos (las de
forecast) requieren decisión de Planeamiento antes de poder corregirse.

**¿Las relaciones que Power BI infiere seguirán funcionando?**
Mejorarán. Hoy Power BI infiere relaciones por nombre de columna porque Access no declara
ninguna (H-02). En PostgreSQL las claves foráneas serán explícitas y Power BI las detectará
correctamente.

**¿Cómo sé si mi tablero está afectado por el problema de versiones del forecast?**
Ejecutar V-7 (§4). Si el informe usa `R08` o `R09` y no filtra por `Version`, está sumando
todos los escenarios.

---

## 8 · Resumen de acciones

| Cuándo | Qué | Quién |
|---|---|---|
| **Antes de migrar** | Ejecutar las 7 verificaciones (§4) y guardar resultados | Reportes |
| **Antes de migrar** | Identificar informes que usan las 6 consultas rotas | Reportes |
| **Antes de migrar** | Confirmar interpretación de kilos del forecast | Planeamiento |
| **Antes de migrar** | Confirmar fuente de verdad: `H00` o `H01` | Agronomía |
| **Antes de migrar** | Definir fechas de corte de campaña (`CampProAra`) | Planeamiento |
| **Durante** | Reapuntar orígenes de datos de Access a PostgreSQL | Reportes + TI |
| **Después** | Validar contra las cifras congeladas en V-4 y V-5 | Reportes |
| **Después** | Revisar visuales de Turno, que pasarán a mostrar categorías reales | Reportes |
| **Después** | Evaluar las 3 tablas sin consumo como nuevas fuentes (§6) | Reportes + Agronomía |

---

**Documentos relacionados:** `01_AUDITORIA.md` (hallazgos técnicos) ·
`02_LOGICA_NEGOCIO.md` (qué hace cada consulta y por qué) ·
`04_PLAN_MIGRACION.md` (plan técnico) · `evidencia\` (volcados verificables)
