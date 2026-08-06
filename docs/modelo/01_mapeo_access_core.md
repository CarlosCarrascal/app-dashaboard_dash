# Mapeo Access → `core` · auditoría columna por columna

Dónde vive hoy, en PostgreSQL, cada columna de `BD_AQUANQA_26.accdb`. El objetivo es poder
afirmar —con evidencia y no de memoria— que **nada del origen quedó sin localizar**, y que cada
nulo que hay en `core` está ahí por una razón conocida.

- **Alcance**: 18 tablas de Access, **235 columnas** (sin contar `Errores de pegado`, que tiene
  0 filas y se extrae solo para dejar constancia).
- **Método**: se cruzó `../historico-access/evidencia/02_esquema_tablas.txt` (esquema y nulos del
  origen, generado por ACE OLEDB) contra el esquema y los datos reales de la base `aquanqa`.
  Cada afirmación se comprobó con una consulta; ninguna se dedujo leyendo el SQL.
- **Fecha**: 2026-08-05.

## Veredicto

| | |
|---|---|
| Columnas con destino en `core` | **211 de 235** |
| Sin destino, **justificado** | 18 |
| Sin destino, **no justificado** — hallazgos nuevos | 6 |
| Hallazgos nuevos abiertos por esta auditoría | **7** (N-16 … N-22), uno de ellos **crítico** |

La migración **no puede declararse cerrada todavía**. El motivo no son los nulos —esos están
clasificados y bajo control (§4)— sino **N-16**: una columna de packing guarda el total del
grupo en cada fila, y sumarla multiplica los kilos por ~24.

---

## 1 · Los siete hallazgos nuevos

### N-16 · `packing.peso_kg` guarda el total del grupo, no el peso de la fila · **CRÍTICO**

`H02_BDElifab` tiene dos columnas llamadas casi igual: `Peso total (kg)` y `Peso total (kg)2`.
Se trataron como un par de duplicados y se eligió la segunda **por tener menos nulos** (0 frente
a 1). No son duplicados: son el **numerador y el denominador** de un porcentaje.

Comprobado sobre las 117.536 filas:

| Comprobación | Resultado |
|---|---|
| `sum(Peso total (kg))` | 18.582.402 kg |
| `sum(Peso total (kg)2)` | **789.597.707 kg** |
| Filas donde ambos coinciden | **0 de 117.536** |
| `% ≈ 100 × peso1 / peso2` | error medio **0,25 pp**; 108.394 de 114.434 filas cuadran dentro de 1 pp |
| `peso2` constante dentro de (fecha proceso, módulo, turno, lote) | **2.535 de 2.591 grupos** (97,8 %) |
| Suma de los `peso1` del grupo ≈ `peso2` del grupo (±2 %) | solo **1.179 de 2.535 grupos** (46 %) |

Es decir: `peso1` es **la parte** (el peso de esa clase/calibre) y `peso2` se repite igual en
cada fila del grupo, como denominador del porcentaje. Pero `peso2` **no es la suma de las
partes** más que en el 46 % de los grupos: es un dato declarado aparte, y la clasificación por
calibre no siempre agota ese total (hay filas de ajuste dentro de un grupo, como
`Net weight correction`, con `peso1 = 0`).

**Qué es `peso2`, con evidencia y sin inventar:**

| Hipótesis probada | Resultado |
|---|---|
| Es un acumulado de campaña (crece con el tiempo) | **Descartada.** Siguiendo un mismo lote en el tiempo, `peso2` sube y baja (1.474 → 23.293 → 367 → 5.184 kg en fechas consecutivas). Es el peso de una entrega puntual, no un acumulado |
| Se deriva del conteo de frutos (`Recuento × peso promedio`) | **No sostenible.** Correlaciona 0,91 con el recuento total del grupo, pero es lo esperable de que ambos escalen con el tamaño del lote — no prueba una fórmula |
| Es un peso real de recepción/báscula, de una fracción de la cosecha | **Compatible, no confirmado.** Sumando `peso2` una vez por grupo (sin repetir): 16.871.430 kg, un 52 % de los 32.386.650 kg cosechados. Ni igual ni absurdo — pero el cruce usa la nota de packing como si fuera el lote de campo, que **no lo es** (N-2), así que es una cota de plausibilidad, no una reconciliación |

Con los datos disponibles no se puede fijar con certeza qué instrumento o proceso genera
`peso2` — eso es información operativa de la planta de packing, no algo que un dato por sí solo
pueda revelar. Queda como pregunta para Operaciones, junto con el resto de columnas de Elifab
sin documentar (N-21). Es un total independiente y repetido dentro del grupo, no una suma que se
pueda reconstruir desde las otras filas — y esa propiedad, sola, ya basta para explicar por qué
sumarlo multiplica los kilos.

Hoy `core.packing.peso_kg` contiene `peso2`: **789.597.707 kg**, frente a **32.386.650 kg** de
cosecha real de campo. Cualquier medida que sume `peso_kg` está inflada unas **24 veces** —esto
no depende de si las partes suman el total o no: `peso2` se repite idéntico en cada fila del
grupo, y sumarlo por fila lo cuenta una vez por cada clase en vez de una vez por lote.

Es exactamente el mismo defecto estructural que el hallazgo B-4 (la medida `KG/HA` que suma un
área repetida una vez por paña), pero en el otro extremo del pipeline y sin que nadie lo hubiera
señalado.

**Propuesta.** Cargar las dos: `peso_kg` = `Peso total (kg)` (la parte, sumable) y
`peso_kg_lote` = `Peso total (kg)2` (el total del grupo, **no sumable**), con un `COMMENT` que
lo diga y una comprobación en el contrato que ate `sum(peso_kg)` a un orden de magnitud
coherente con la cosecha. La fila con `Peso total (kg)` nulo se resuelve con el porcentaje.

### N-17 · `E03_ConteoEstados.F16` es la hora de captura, no un residuo · **Medio**

Se descartó como columna basura. Comprobado: **13.230 valores no vacíos, el 100 % con formato
de hora**, en rango `04:25:03`–`22:42:03`. Es la hora de captura — el mismo dato que `E02` y
`E04` **sí** conservan en `flores.hora` y `brotes.hora`.

Se pierde información real, y además de forma incoherente entre tablas hermanas.

**Propuesta.** Cargar en `core.estados.hora` (`time`), igual que sus dos tablas gemelas.

### N-18 · El turno se descarta en cinco tablas · **Medio**

`core.turno` existe como dimensión (T00–T12) y `R08_Forecast_Campaña` sí persiste su turno.
Pero en otras cinco tablas la columna `Turno` del origen se normaliza en `stg` y **se tira al
insertar en `core`**:

| Tabla de Access | Valores en el origen |
|---|---|
| `H01_ProdHistorica` | 30.624 valores, 13 turnos distintos |
| `E05_DiametrosBayas` | 12 turnos |
| `M_Poda` | poblado |
| `M_nMuestra` | se descarta ya en la vista de `stg` |
| `R09_Forecast_Semanal` | poblado |

En parte es esperable —el turno suele derivarse del lote, que sí se guarda— pero no está escrito
en ninguna parte, y en `H01` conviven un turno propio y el del lote sin que se haya comprobado
que coinciden.

**Propuesta.** Verificar en cada caso si el turno del hecho coincide con el del lote resuelto.
Donde coincida, documentar que es derivable y cerrar. Donde no, persistirlo: una discrepancia
es información, no ruido.

### N-19 · 390 filas de packing traen el programa en la columna equivocada · **Bajo**

`Contenedores volcados` contiene, en 390 filas, un texto que es un nombre de programa:
`Programa IA AQU 2025 (con daño por insecto) SIN ACDT` (320 filas) y `… (ORIGINAL)` (70).

No es un desplazamiento general de columnas: en esas filas `Clases`, `Lote`, `Calibre` y
`Mercado` son correctos. Es un valor puesto en el sitio equivocado — y en **las 390**, la
columna `Programa de clasificación` está vacía, así que el dato es recuperable sin ambigüedad.

Hoy se pierde en silencio: el casteo a entero devuelve NULL y no queda registro en cuarentena.
Por eso `core.packing.contenedores_volcados` tiene **más** nulos que el origen (13.475 vs
13.085): la diferencia son exactamente esos 390.

**Propuesta.** Al cargar, si `contenedores_volcados` no es numérico y `programa` está vacío,
mover el valor a `programa` y registrar la fila en `qua.rechazos` con un motivo nuevo
`VALOR_EN_COLUMNA_EQUIVOCADA`.

### N-20 · 52 fechas de poda con el cero de la época de Excel · **Bajo** · *ya resuelto, faltaba documentarlo*

Access declara 2 nulos en `M_Poda.FInicio`. En realidad hay **54 fechas ausentes**: 2 nulas y
**52 con el valor `1899-12-30 00:00:00`**, que es lo que Access guarda cuando una fecha está
vacía.

La función de casteo ya las convierte a NULL, que es lo correcto: una poda no empezó en 1899.
**La migración es aquí más honesta que el origen** — pero la diferencia entre "2 nulos en
Access" y "54 en `core`" parecía una pérdida y no lo es.

**Propuesta.** Ninguna corrección de datos. Queda documentado aquí y en §4.

### N-21 · Seis columnas de H02 sin destino que no son duplicados · **Medio**

Se descartaron por parecer redundantes. Comprobado que **no lo son**:

| Columna | Por qué no es redundante |
|---|---|
| `ACDT 2` | Solo coincide con `ACDT` en 15.950 de 117.536 filas. `>ACDT 60` vs `>ACDT 50` son umbrales distintos |
| `ENSAYO` | Coincide con `Mercado` en 98.250 de 117.536. En 15.699 filas dice `USA` donde `Mercado` dice `CHINA` |
| `S26` / `S271` | Rangos ACDT distintos entre sí (`50-90` vs `40-90`); iguales solo en 61.437 filas |
| `Packet` | 3 valores propios (Exportable / Descarte / -) |
| `Clasificación` | 15 valores (OM, China, Blando, Color…) **no derivables** de `Clases` |
| `Peso total (kg)2` (`peso_kg_lote`, N-16) | No se deriva del conteo de frutos ni es un acumulado (descartado con evidencia); compatible con ser un peso de recepción, sin confirmar |

Sí están correctamente descartadas: `Calibres` (3 valores derivables de `Calibre`), `Mes`
(derivable de `Fecha Proceso`) y `Modulo` sin tilde (se eligió `Módulo`, que resuelve mejor los
submódulos A/B).

**Propuesta.** Son campos del sistema de packing (Elifab) cuyo significado no está documentado
en ninguna parte. Antes de cargarlos hay que preguntar a quien opera el packing qué son. Si
resultan operativamente útiles, entran como columnas de texto en `core.packing`; si no, se
documenta el descarte con su motivo. **Hoy no están ni cargados ni justificados.**

### N-22 · La cifra de N-9 quedó obsoleta para `H00` · **Bajo**

`05_ADDENDA_TECNICA.md` documenta que `H00_VolumenCampo` tiene "151 filas de exceso en 34
grupos" con la clave natural repetida, y el código de carga sigue afirmándolo.

Comprobado hoy: **0 grupos repetidos** en `stg.h00_cosecha` y **0 rechazos**
`CLAVE_NATURAL_REPETIDA` con origen H00. Los 116 que hay en cuarentena vienen **todos** de
`E02_ConteoFlores`.

La normalización de identidad (N-3) cambió la clave y el problema desapareció. La cifra
sobrevive en los comentarios pero ya no describe la realidad.

**Propuesta.** Corregir el comentario del código y la nota de la addenda. Sin cambio de datos.

---

## 2 · Mapeo por tabla

Convención: `Fundo` + `Modulo` + `Lote` **nunca** tienen columna propia en `core` — los tres se
colapsan en un único `lote_id` (ADR-0003), y el fundo se recupera navegando
`lote → modulo → fundo`. `Evaluador` se resuelve a `evaluador_id` por DNI (H-09).

### Evaluaciones de campo

| Access | Destino en `core` | Transformación |
|---|---|---|
| **E01_Ramas** (94.236 → 5.384 + 71.095) | | **cambia el grano** (N-1) |
| Id | `rama_medicion.id_origen` | entra en la deduplicación por fila completa |
| Actividad | *(sin destino, justificado)* | constante: un solo valor, `ConteoRamas` |
| Evaluador, Fecha, Fundo/Modulo/Lote, Cortina, Hilera, Planta | `evaluacion_ramas.*` | cabecera: 1 fila por planta evaluada |
| `Ramas <5`, `Ramas >5` | `evaluacion_ramas.ramas_menor5/_mayor5` | `max()` por planta: en el origen se repetían en cada rama |
| `# Ramas` | `rama_medicion.nro_rama` | **es el índice de rama, no un total** (N-1) |
| Diametro | `rama_medicion.diametro`, `.sospechoso` | marca > 50 mm |
| **E02_ConteoFlores** (43.490 → 43.469) | | |
| Item, Fecha, Evaluador, ubicación, nFlores, Cuajo, YA, YP, Hora | `flores.*` | `Cuajo`→`cuajo`, `YA`→`yemas_abiertas`, `YP`→`yemas_por_abrir` |
| **E03_ConteoEstados** (18.714 → 18.708) | | |
| Item, Fecha, Evaluador, ubicación, E1…E5 | `estados.*` | `item` forma parte de la clave natural (N-8) |
| Total | `estados.total_origen` | se conserva crudo; `estados.total` es **columna generada** `e1+…+e5` |
| **F16** | **sin destino — N-17** | es la hora de captura, 13.230 valores |
| **E04_Brotes** (3.385 → 3.385) | | |
| Piso, Fecha, Evaluador, ubicación, Brotes, Des1–Des3, Hora | `brotes.*` | la fecha entra en la clave (H-02) |
| Des4, Des5 | *(sin destino, justificado)* | 3.385 de 3.385 vacías: comprobado |
| **E05_DiametrosBayas** (4.193 → 3.889) | | |
| Modulo, Lote, Cortina, Hilera, Diametro, Fecha | `baya_medicion.*` | 1 fila = 1 baya (N-7); `nro_muestra` es sintético |
| **Turno** | **sin destino — N-18** | 12 turnos en el origen |
| **M_Evaluadores** (31 → 37) | | |
| DNI, Nombres, Apellidos, Cod, InicioLabores, Nacimiento, Zona, Celular, Estado | `evaluador.*` | `Estado`→`activo`; se añaden 6 DNI con `en_maestro = false` (H-09) |
| **M_nMuestra** (681 → 680) | | |
| Evaluacion, ubicación, Cortina, Hilera, Planta, Muestras | `muestra_requerida.*` | |
| **Turno** | **sin destino — N-18** | |

### Cosecha, packing y clima

| Access | Destino en `core` | Transformación |
|---|---|---|
| **H00_VolumenCampo** (30.812) + **H01_ProdHistorica** (30.626) → `core.cosecha` (30.540) | | **ver §3** |
| H00: Campaña, Fecha, ubicación, Variedad, KG | `cosecha.campania_id/fecha/lote_id/variedad_id/kg` | H00 es la referencia de kilos |
| H01: nPlantas, Semana, Paña, Peso | `cosecha.n_plantas/semana/pana/peso_baya` | **solo H01 los trae** |
| H01: KG | `cosecha.kg_h01` | se guarda aparte, no sobrescribe |
| H01: **Turno** | **sin destino — N-18** | 30.624 valores |
| **H02_BDElifab** (117.536 → 117.536) | | |
| Clases, Recuento, %, Programa, Contenedores esp./volc., Horas, Fechas, Calibrador, ACDT, Acidez, Defecto, Semana, Año | `packing.*` | 1:1 |
| Lote | `packing.nota_packing` | **no es un lote de campo**: es una nota de packing (N-2) |
| `Peso total (kg)` | **sin destino — N-16 (crítico)** | es el peso real de la fila |
| `Peso total (kg)2` | `packing.peso_kg` | **es el total del grupo — N-16** |
| Productor | `packing.empresa_id` | vía `productor_equivalencia`; 117.536 de 117.536 resueltas |
| Productor1 | *(sin destino, justificado)* | 16 grafías; se eligió `Productor`, con 2 valores canónicos |
| Variedad, Módulo, Turno, Calibre, Mercado | `packing.variedad_id/modulo_id/turno_packing/calibre_id/mercado` | `turno_packing` es un dominio distinto del turno de riego (N-2) |
| Modulo *(sin tilde)*, Calibres, Mes | *(sin destino, justificado)* | duplicados o derivables |
| ACDT 2, ENSAYO, S26, S271, Packet, Clasificación | **sin destino — N-21** | no son duplicados |
| **H05_Clima** (155.588 → 153.413) | | |
| Las 25 columnas | `clima.*` | **mapeo 1:1 verificado**; `TembAlta`→`temp_alta` (typo corregido) |
| | | 2.175 filas de exceso por timestamp duplicado, en cuarentena (H-08) |

### Maestros y forecast

| Access | Destino en `core` | Transformación |
|---|---|---|
| **M_Lotes** (860) | | **sustituida por el maestro vigente** `M_Lotes.xlsx` (879 lotes, ADR-0003) |
| Fundo | `fundo_alias` | única columna con uso real: aporta 3 grafías comerciales |
| Las otras 14 | *(sin destino, justificado)* | el maestro vigente las reemplaza |
| **M_Poda** (2.159 → 2.147) | | 12 filas a cuarentena |
| Campaña, ubicación, Area, FSiembra, FInicio | `poda.*` | `FInicio`: ver N-20 |
| Variedad | `variedad` / `variedad_alias` | al catálogo, no por fila |
| **Turno** | **sin destino — N-18** | |
| **M_Time** (2.189) | | |
| Fecha, Sem, Mes, Año | `calendario.*` | **recalculadas** desde la fecha, no copiadas |
| SEvConteo | `calendario.sem_ev_conteo` + `semana_evaluacion` | grano semanal separado (H-05) |
| MesSem | `calendario.mes_sem` | |
| AQII | *(sin destino, justificado)* | 2.189 de 2.189 vacías: comprobado |
| **M_EquivalenciaElifab** (15) | `productor_equivalencia` | 15 de 15; es lo que da `empresa_id` a todo el packing |
| **R08_Forecast_Campaña** (101.715 → 101.714) | | |
| Version | `version_forecast.codigo/iteracion/es_presupuesto` | |
| **Fundo** | `forecast_campania.empresa_id` | **semántica invertida: trae la empresa** (N-5) |
| **FundoPPto** | *(indirecto)* | **trae el fundo físico** (N-5); se usa para desambiguar el módulo |
| Modulo, Turno, Año, Semana, KG Exp/Des/Con, FrtTotal_Exp, Campaña, C12…C26 | `forecast_campania.*` | 624 filas al módulo centinela (ADR-0005) |
| **R09_Forecast_Semanal** (48.368 → 48.368) | | |
| Version, Campaña, Pasada, Mod/Lote/Fundo, Area, FCosAnt, FCos, Sem, FrtCos, Peso, FrutosTotal, Rend, Kg, Dr | `forecast_semanal.*` | `FrtCos`→`frutos_por_planta` (renombre semántico); 23 al lote centinela |
| **Turno**, **FundPPTo** | **sin destino — N-18** | |

---

## 3 · Por qué la cosecha se unificó en una sola tabla

Es el cambio de modelado con más impacto de toda la migración, y hasta ahora solo estaba
documentado el *resultado*. Este es el *porqué*.

### El problema en Access

`H00_VolumenCampo` (30.812 filas) y `H01_ProdHistorica` (30.626) son **la misma cosecha contada
dos veces**, con columnas distintas:

- `H00` trae la **variedad**, y es la que se usaba como referencia de kilos.
- `H01` trae **paña, peso de baya, número de plantas y semana** — atributos que `H00` no tiene.
- Ninguna de las dos trae todo.

Nadie había verificado si coincidían. La auditoría original (H-07) registró una diferencia de
187 filas y 4.486,59 kg y la dejó como pregunta abierta para Agronomía (decisión **D-3**:
"¿cuál es la fuente de verdad?").

Cualquier informe que necesitara variedad **y** peso de baya tenía que unir las dos tablas a
mano, y cada analista lo hacía a su manera. Ese es el coste real: no la duplicación de
almacenamiento, sino que **la relación entre ambas vivía en la cabeza de quien escribía cada
consulta**.

### Qué se descubrió al verificar (N-14)

La diferencia de 187 filas **no existía**. Era un artefacto de comparar recuentos crudos sin
normalizar los códigos de lote (`L11B` vs `L011B`, N-3) y sin apartar las filas de subtotal de
Excel. Normalizando la identidad primero, las dos tablas contienen la misma cosecha con
**0,01 kg** de diferencia.

**Eso cerró D-3 sin necesidad de preguntar a nadie**: no hay que elegir una fuente de verdad
porque no hay conflicto. La pregunta estaba mal planteada.

### Cómo se unificó

`FULL OUTER JOIN` por `(lote_id, fecha, campania_id)` — la paña queda deliberadamente **fuera**
de la clave, porque solo H01 la conoce y usarla partiría filas que son la misma cosecha.

| Regla | Decisión |
|---|---|
| Kilos | `kg = coalesce(H00, H01)` — **H00 gana**, por convención (D-3), no porque H01 esté mal |
| Kilos de H01 | se guardan aparte en `kg_h01`, sin sobrescribir nada |
| Variedad | de H00; si falta, fila centinela (ADR-0005) |
| Paña, peso de baya, nº de plantas, semana | **solo de H01** — H00 no los tiene |
| Procedencia | `en_h00` / `en_h01` marcan en qué fuente estaba cada fila |

### Impacto en los datos, medido

| | |
|---|---|
| Filas en `core.cosecha` | **30.540** |
| Presentes en **ambas** fuentes | 30.532 |
| Solo en H00 | 4 |
| Solo en H01 | 4 — son las que no tienen variedad, porque **H01 nunca tuvo esa columna** (ADR-0005) |
| Filas donde `kg` ≠ `kg_h01` (a 2 decimales) | **105** de 30.532 (0,34 %) |
| `sum(kg)` | 32.386.650 kg |
| Apartadas en cuarentena | 3 subtotales de Excel (H-06) + 363 de lotes fuera del maestro (N-14) |

**Qué se gana**: una sola tabla con todos los atributos, sin que nadie tenga que recordar cómo
se unen. La reconciliación se sigue calculando y guardando en `qua.reconciliacion_cosecha` —
ahora como evidencia de que cuadran, no como registro de una diferencia sin explicar.

**Qué se pierde, y hay que saberlo**: el turno propio de H01 (N-18) y la posibilidad de
distinguir a simple vista de qué tabla venía cada cifra — para eso están `en_h00` y `en_h01`.
Y las **105 filas con kilos discrepantes** siguen ahí: son reales, están conservadas en las dos
columnas, y nadie ha decidido cuál vale. Es poco, pero no es cero.

---

## 4 · Los nulos de `core`, clasificados

Se midieron **los nulos reales de las 323 columnas** de `core` y se compararon uno a uno con los
que declara Access.

### A · Nulos que ya venían de Access, idénticos — *no hay nada que corregir*

La coincidencia exacta es la prueba de que la migración fue fiel:

| Columna en `core` | Nulos | En Access |
|---|---|---|
| `brotes.des1` / `des2` / `des3` | 3.145 / 3.380 / 3.380 | idéntico |
| `brotes.hora` | 2.356 | idéntico |
| `flores.hora` | 14.862 | idéntico |
| `flores.n_flores` | 250 | idéntico |
| `calendario.sem_ev_conteo` / `mes_sem` | 965 / 707 | idéntico |
| `clima.barometro` / `tshw_index` | 95 / 3 | idéntico |
| `packing.turno_packing` | 7.708 | idéntico |
| `packing.recuento` / `porcentaje` / `programa` | 30 / 3.102 / 391 | idéntico |
| `packing.hora_inicio` / `hora_fin` | 56.173 / 56.172 | idéntico |
| `packing.contenedores_esperados` | 10.439 | idéntico |
| `forecast_semanal.pasada` / `peso_baya` / `frutos_total` | 22.765 cada una | idéntico |
| `forecast_campania.c12`…`c26` | 13.120 | 13.121 − 1 fila de subtotal |
| `forecast_campania.frutos_exp` | 17.483 | 17.484 − 1 subtotal |

Son **ausencias legítimas de medición**: nadie contó el cuajo en esa planta, el packing no
registró la hora, el forecast no desglosó calibres. Forzarles un valor inventaría datos.

### B · Nulos menores que en Access — *filas apartadas en cuarentena*

`flores.cuajo` (38.138 vs 38.154), `yemas_abiertas` (31.555 vs 31.567), `clima.direc_viento`
(7.723 vs 7.830). La diferencia son las filas que no entraron en `core` y están en
`qua.rechazos`. **Correcto por construcción.**

### C · Nulos mayores que en Access — *los dos únicos casos, ambos ya explicados*

| Columna | `core` | Access | Explicación |
|---|---|---|---|
| `poda.fecha_inicio` | 54 | 2 | **N-20**: 52 fechas `1899-12-30`, el cero de Excel. La migración acierta |
| `packing.contenedores_volcados` | 13.475 | 13.085 | **N-19**: 390 filas con un nombre de programa en la columna. Recuperable |

**No hay ningún otro caso** en el que la migración haya añadido nulos.

### D · Nulos de dominio distinto — *no comparables con Access*

`lote.*` (fecha_siembra 16, maceta 170, tipo_fibra 256): vienen del **maestro vigente**
`M_Lotes.xlsx` (879 lotes), no del `M_Lotes` de Access (860). `evaluador.*`: 37 filas frente a
31, porque se añadieron 6 DNI que capturan datos sin ficha (H-09).

### E · Nulos estructurales del modelo nuevo — *por diseño*

| Columna | Nulos | Por qué |
|---|---|---|
| `calibre.mm` | 3 de 12 | `DESCARTE` y similares están fuera de la escala de milímetros |
| `fundo_alias.fundo_id` | 8 de 25 | La tabla existe para registrar alias que **no** determinan un fundo; `ambiguo` gobierna el caso (ADR-0005) |
| `version_forecast.semana_emision` | 15 de 61 | `Presupuesto 2026` y `Proy_<mes>` no llevan semana en el código |
| `campania.fecha_inicio` / `fecha_fin` | 1 de 6 | Una campaña sin poda registrada de la que derivar el rango (N-11) |
| `config_decision.confirmado_por` / `_en` | 5 de 5 | **Las decisiones D-1 y D-2 siguen sin confirmar** — el nulo *es* el estado |
| `cosecha.pana` / `peso_baya` / `n_plantas` / `semana` / `kg_h01` | 4 y 12 | Las 4 filas que solo existen en H00, que no trae esos atributos (§3) |

### F · Claves foráneas — *cerrado*

**Ninguna FK de una tabla de hechos es NULL** (ADR-0005). Verificado hoy:
`cero.fk_nula_en_hechos = 0`.

---

## 5 · Qué falta para declarar la migración cerrada

| # | Acción | Tipo | Dueño |
|---|---|---|---|
| 1 | **N-16** · Cargar `Peso total (kg)` como `peso_kg` y renombrar el actual a `peso_kg_lote` | corrección | Ingeniería |
| 2 | **N-17** · Cargar `E03.F16` en `estados.hora` | corrección | Ingeniería |
| 3 | **N-19** · Mover el programa a su columna y registrar en cuarentena | corrección | Ingeniería |
| 4 | **N-22** · Corregir los comentarios obsoletos de N-9 | documentación | Ingeniería |
| 5 | **N-18** · Comprobar si el turno del hecho coincide con el del lote; persistirlo donde no | verificación | Ingeniería, con criterio de Agronomía |
| 6 | **N-21** · Preguntar qué son `ENSAYO`, `S26`, `S271`, `Packet`, `Clasificación`, `ACDT 2` | **decisión de negocio** | Operaciones de packing |
| 7 | Las 105 filas de cosecha con kilos discrepantes entre H00 y H01 | **decisión de negocio** | Agronomía |

Los puntos 1 a 4 no dependen de nadie externo y son los que bloquean el cierre técnico. Los
puntos 5 a 7 se suman a las cuatro decisiones ya listadas en
[`../runbooks/02-cierre-de-migracion.md`](../runbooks/02-cierre-de-migracion.md) §3.

Hasta que el punto 1 esté resuelto, **`core.packing.peso_kg` no debe usarse en ninguna medida de
Power BI**.
