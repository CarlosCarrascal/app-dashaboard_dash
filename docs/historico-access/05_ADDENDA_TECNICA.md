# Addenda técnica · verificación previa a la migración

**Fecha:** 2026-08-03
**Origen:** `BD_AQUANQA_26.accdb` · `M_Lotes.xlsx` (maestro vigente) · TMDL de los dos informes Power BI
**Acceso:** solo lectura, vía `Microsoft.ACE.OLEDB.16.0` (`Mode=Read`)
**Para:** TI / equipo de datos — **leer antes de aplicar el DDL de `04_PLAN_MIGRACION.md` §3**

> **Por qué existe este documento.** Antes de escribir el DDL, cada afirmación de los cuatro
> documentos que fija una clave, un grano o una cifra de aceptación se verificó contra los
> datos reales. El diagnóstico de la auditoría se confirma en lo esencial: los 12 hallazgos
> existen y las cifras de control son reproducibles. Pero aparecen **quince hechos nuevos**, y
> nueve de ellos obligan a cambiar el DDL propuesto: aplicarlo tal como está **destruiría
> datos**.
>
> Igual que en `01_AUDITORIA.md`, toda cifra publicada aquí proviene de una consulta ejecutada.

**Alcance real del origen:** 18 tablas y **654.598 filas** — no las 683.180 que publican los
cuatro documentos, cuyos recuentos por tabla son correctos pero cuya suma no lo es (N-10).

---

## 1 · Resumen

| Bloque | Qué cambia |
|---|---|
| **A · Datos** (N-1…N-22) | El grano de dos tablas está mal entendido, una clave natural es inviable, otra faltaba, los códigos de lote no están normalizados entre fuentes, el total de filas está mal sumado, las campañas se solapan, hay una cuarta fila de subtotal en el forecast, H-07 no era lo que parecía, dos hechos de forecast no trataban sus FK sin resolver como el resto, y **la columna de peso de packing guarda el total del grupo en cada fila, lo que multiplica los kilos por 24** (N-16) |
| **B · BI** (B-1…B-6) | El consumo real de Power BI no es el que midió el linaje: hay dimensiones inventadas con DAX, un mapeo de fundo incorrecto, una medida mal calculada y lógica de negocio que solo vive en Power Query |
| **C · Decisiones** | **D-3 y D-4 quedan cerradas por los datos**; D-2 estaba mal planteada; solo D-1 sigue necesitando a Planeamiento |

**El hallazgo más importante es N-1.** El `UNIQUE` que `04_PLAN_MIGRACION.md` §3.4 declara para
`fact.ramas` rechazaría **88.852 de las 94.236 filas de `E01_Ramas` — el 94%**.

---

## 2 · Bloque A · Hallazgos sobre los datos

### N-1 · El grano de `E01_Ramas` es la rama, no la planta · **Crítico**

**Lo que dicen los documentos.** `01_AUDITORIA.md` §5 describe el grano como "una planta
evaluada en una fecha", presenta `# Ramas` como "total; `SUM` = 730.318", y fija como filas
únicas 71.095 "por `(Fecha, Fundo, Modulo, Lote, Cortina, Hilera, Planta)`". El DDL declara
`UNIQUE (lote_id, fecha, cortina, hilera, planta)`.

**Lo que muestran los datos.** Esa clave tiene **5.384 combinaciones**, no 71.095:

| Clave probada | Combinaciones |
|---|---|
| `Fecha, Fundo, Modulo, Lote` | 825 |
| `+ Cortina` | 1.964 |
| `+ Hilera` | 5.373 |
| `+ Planta` | **5.384** |
| `+ Actividad` | 5.384 *(`Actividad` tiene un solo valor: `ConteoRamas`)* |
| `+ Id` | 63.709 |
| **las 14 columnas completas** | **71.095** |

Un grupo cualquiera, extraído tal cual (lote M01/L001, 2026-08-01, cortina 1, hilera 4,
planta 15):

```
 Id  | Actividad   | Evaluador | Fecha      | Fundo      | Mod | Lote | C | H | P  | <5 | >5 | # Ramas | Diametro
1099 | ConteoRamas | 73681272  | 2026-08-01 | Quri Allpa | M01 | L001 | 1 | 4 | 15 |  7 | 21 |    1    |   8,52
1100 | ConteoRamas | 73681272  | 2026-08-01 | Quri Allpa | M01 | L001 | 1 | 4 | 15 |  7 | 21 |    2    |   6,69
1101 | ConteoRamas | 73681272  | 2026-08-01 | Quri Allpa | M01 | L001 | 1 | 4 | 15 |  7 | 21 |    3    |   7,25
 ...    (21 filas consecutivas, # Ramas de 1 a 22, un diámetro distinto en cada una)
1120 | ConteoRamas | 73681272  | 2026-08-01 | Quri Allpa | M01 | L001 | 1 | 4 | 15 |  7 | 21 |   22    |  10,64
```

La lectura es inequívoca:

- **`# Ramas` es el número de la rama medida**, no un total. Su rango es **1 a 33**.
- **`Diametro` es el diámetro de esa rama concreta**, no de la planta.
- **`Ramas <5` y `Ramas >5` son atributos de la planta** (los conteos declarados por el
  evaluador) y se repiten idénticos en todas las filas del grupo.
- `Id` es un contador secuencial del registro de campo (1.099…1.120 en este grupo), reiniciado
  por lote y fecha: 15.043 valores para 94.236 filas.

**Consecuencias.**

1. **La clave del DDL es inviable.** `UNIQUE (lote_id, fecha, cortina, hilera, planta)` admitiría
   5.384 filas y rechazaría 88.852. Hay que separar en dos entidades: cabecera por planta
   (5.384) y detalle por rama medida.
2. **La clave (punto físico + `# Ramas`) tampoco es única**: da 66.538 combinaciones. Quedan
   4.557 filas donde la misma rama del mismo punto y fecha aparece con **diámetro distinto** —
   eso no es una recarga, es un conflicto de captura y necesita revisión agronómica.
3. **La cifra de aceptación 71.095 sí es correcta**, pero corresponde a *filas completas
   distintas*. La deduplicación de H-03 debe definirse como **fila exactamente idéntica**, que
   es además coherente con las 23.141 de exceso que publica la auditoría (94.236 − 71.095).
4. **`SUM([# Ramas]) = 730.318` no significa nada**: es la suma de los índices de rama. Debe
   retirarse como métrica de control. El total de ramas realmente declarado es
   **110.095** (`SUM` de `Max(Ramas <5) + Max(Ramas >5)` por planta).
5. `Ramas <5 + Ramas >5` **no coincide** con el número de filas medidas en 5.363 de los 5.384
   grupos: se declaran más ramas de las que se miden. Es esperable —se mide una submuestra—
   pero confirma que ambas cifras son conceptos distintos y que no se puede derivar una de otra.

**Efecto en Power BI.** Cualquier medida que hoy sume `# Ramas` está reportando una suma de
índices bajo la etiqueta "total de ramas".

**Corrección adoptada.** Ver [ADR-0002](../adr/0002-grano-evaluacion-ramas.md).

---

### N-2 · `H02_BDElifab` no baja a lote · **Alto**

`04_PLAN_MIGRACION.md` §4.7 carga `fact.packing` con `lote_id`. No es posible:

| Columna | Lo que contiene realmente | Valores más frecuentes |
|---|---|---|
| `Lote` | identificador de **nota de packing / pallet**, no un lote de campo | `NP`=3.464 · *(vacío)*=1.254 · `NP  910`=366 · `NP  212`=285 |
| `Modulo` | el módulo **sin prefijo ni relleno** | `2`=18.275 · `4`=18.139 · `3`=17.334 · `1`=15.887 |
| `Módulo` | el mismo módulo con otra grafía | `Módulo 02`=18.275 · `Módulo 04`=18.139 |
| `Turno` | **turno de proceso de la empacadora**, no el turno de riego | `DÍA`=90.702 · `NOCHE`=19.126 · *(vacío)*=7.708 |

Resolver `(Modulo, Lote)` contra el maestro deja **117.536 filas huérfanas — el 100%**, en
2.363 combinaciones inexistentes.

**Consecuencias.** `fact_packing` referencia **módulo**, no lote. `turno_packing` (DÍA/NOCHE) es
un dominio distinto de `turno` (T00–T12): **son dos conceptos con el mismo nombre de columna**,
y mezclarlos en una sola dimensión rompería ambos. `dim_modulo` se resuelve con
`'M' || lpad(modulo, 2, '0')`.

Además, `Mercado` tiene valores que la auditoría no recoge: además de `USA`=44.134,
`DESCARTE`=12.305, `CHINA`=11.827 y `ÁCIDO`=7.167, hay **`'0'`=41.428 y `'-'`=675**. Un tercio
de la tabla no tiene mercado asignable, y `01_AUDITORIA.md` describe la distribución entre los
cuatro valores como "el indicador de rentabilidad de la campaña".

---

### N-3 · Códigos de lote sin normalizar entre fuentes · **Alto**

El maestro escribe `L011B`; los hechos escriben `L11B`. Sin normalizar, esas filas quedan
huérfanas aunque el lote exista. Normalizando a `L` + 3 dígitos + sufijo:

| Tabla | Huérfanos sin normalizar | Huérfanos normalizando |
|---|---|---|
| `M_Lotes` (Access) | 4 | **0** |
| `E02_ConteoFlores` | 167 | **21** |
| `E03_ConteoEstados` | 172 | **6** |
| `H00_VolumenCampo` | 318 | **276** |
| `H01_ProdHistorica` | 132 | **90** |
| `M_Poda` | 16 | **12** |
| `R09_Forecast_Semanal` | 392 | **23** |
| `E05_DiametrosBayas` | 304 | **304** |
| `E01_Ramas`, `E04_Brotes` | 0 | **0** |

La normalización es lo que lleva el maestro histórico de Access a **cobertura total** y deja los
huérfanos en **~732 filas de ~280.000 (0,26%)**, todos identificables uno por uno:
`M04/L078`, `M04/L079`, `M04/L080`, `M04/L061A`, `M04/L078A` (lotes retirados del maestro),
`M10/L191`, `M10/L195`, `M10B/L194` (módulo `M10` sin sufijo A/B), `M16/L000`, `M17/L042`,
`M17/L056B`, `M18/L077`, `M07/L031`, y las 3 filas de subtotal de H-06.

---

### N-4 · `(Modulo, Lote)` no identifica un lote · **Alto**

El maestro vigente tiene 879 filas y **870** combinaciones distintas de `(Modulo, Lote)`: hay
**9 pares que existen en las dos empresas a la vez**.

```
M01|L000 · M02|L000 · M03|L000 · M04|L000   → Aqu Anqa 1 (T00)  y  Aqu Anqa 2 (T00)
M02|L037 · M02|L038 · M02|L040 · M02|L041 · M02|L042
                                            → Aqu Anqa 1  y  Aqu Anqa 2, con turnos distintos
```

La causa es que **los módulos M01 a M04 pertenecen a dos fundos simultáneamente**:

| Módulo | Fundos a los que pertenece |
|---|---|
| M01 – M04 | `Aqu Anqa 1` (empresa `Aqu Anqa`) **y** `Aqu Anqa 2` (empresa `Aqu Anqa II`) |
| M05 | `Aqu Anqa 2` |
| M06 – M10B | `Aqu Anqa 3` |
| M12 – M15 | `Aqu Anqa 4` |
| M11, M16 – M18 | `Aqu Anqa 5` |
| M19 – M24 | `Aqu Anqa 6` |

**Consecuencia sobre el patrón de ETL propuesto.** `04_PLAN_MIGRACION.md` §4.2 resuelve así:

```sql
JOIN dim.fundo_alias fa ON fa.alias = trim(s.fundo)
JOIN dim.modulo m ON m.fundo_id = fa.fundo_id AND m.codigo = trim(s.modulo)
```

No funciona, porque el alias no determina el fundo: `Aqu Anqa II - Kawsay Allpa` corresponde a
`Aqu Anqa 3` en 211 lotes **y** a `Aqu Anqa 5` en 44. Un join por alias duplicaría filas.

**Corrección adoptada.** La identidad se resuelve por `(empresa, módulo, lote)` y el alias queda
como atributo informativo, nunca como clave. Ver
[ADR-0003](../adr/0003-identidad-de-lote.md).

---

### N-5 · `R08` tiene invertida la semántica de sus columnas de fundo · **Medio**

| Columna | Contenido real | Valores |
|---|---|---|
| `R08.Fundo` | **la empresa** (vocabulario B) | `Aqu Anqa II`=86.081 · `Aqu Anqa`=15.633 |
| `R08.FundoPPto` | **el fundo físico nuevo**, mezclado con alias antiguos | `Aqu Anqa 3`=24.786 · `Aqu Anqa 4`=21.435 · `Aqu Anqa 2`=20.055 · `Aqu Anqa 5`=15.255 · `Aqu Anqa 1`=15.111 · `Aqu Anqa 6`=1.380 · `Aqu Anqa II - Ayllu Allpa`=1.332 · `Aqu Anqa II - Kawsay Allpa`=1.014 · `Aqu Anqa II - Quri Allpa`=824 · `Aqu Anqa - Arena Azul`=522 |

Es exactamente lo contrario de `M_Lotes`, donde `Fundo` es el fundo y `FundoPPto` la empresa.
`R09` presenta el mismo problema mezclado dentro de una sola columna: `R09.Fundo` contiene a la
vez alias operativos (`Aqu Anqa II - Kawsay Allpa`=11.539) y fundos físicos nuevos
(`Aqu Anqa 4`=7.660, `Aqu Anqa 2`=7.425…), y `R09.FundPPTo` mezcla empresa con alias
(`Aqu Anqa II - Ampliación`=3.844).

**El lado bueno de este hallazgo: resuelve D-4.** El 96% de las filas de `R08` ya usa la
nomenclatura nueva, y la correspondencia alias ↔ fundo físico que se observa coincide exacta con
la del maestro vigente. **No hace falta preguntar a Agronomía** por el mapeo de `Ampliacion`,
`Vivadis` y `Sta.Teresa`: el maestro nuevo los sustituye y los datos confirman la equivalencia.

---

### N-6 · La variedad vive en los hechos, no en el maestro · **Medio**

`04_PLAN_MIGRACION.md` §2 deriva `dim.variedad` de `M_Lotes` y estima "~5 filas". En realidad
**`M_Lotes` tiene una sola variedad** — `Sekoya pop` en las 860 filas de Access y en las 879 del
maestro nuevo. Las variedades reales están en los hechos:

| `H00_VolumenCampo.Variedad` | Filas | | `M_Poda.Variedad` | Filas |
|---|---|---|---|---|
| `POP` | 30.545 | | `Sekoya pop` | 2.156 |
| `SEKOYA POP` | 98 | | `Variedades` | 2 |
| `AZRA BLUE` | 33 | | `TEST PLOT` | 1 |
| `ATLAS BLUE` | 31 | | | |
| `FCM15-005` | 27 | | | |
| `FCM14-057` | 26 | | | |
| `FCM17-132` | 25 | | | |
| `SEKOYA BEAUTY` | 17 | | | |
| `FCM-15`, `FCM-17` | 3 c/u | | | |
| `BIANCA`, `FCM-14`, `FCM 17-132` | 1 c/u | | | |

`POP` y `SEKOYA POP` son la misma variedad con dos grafías. `dim_variedad` se construye desde
los hechos con una tabla de alias, igual que el fundo.

---

### N-7 · `E05_DiametrosBayas`: una fila es una baya · **Medio**

`01_AUDITORIA.md` §5 describe el grano como "una medición en una hilera y fecha". Los datos
dicen otra cosa: 4.193 filas en **43** combinaciones de
`(Fecha, Modulo, Turno, Lote, Cortina, Hilera)` — unas **97 filas por combinación**. Coincide con
los conteos de los huérfanos, que aparecen en bloques de ~100 (`M10/L191`=100,
`M10/L195`=102, `M10B/L194`=102).

Una fila es **una baya medida**, y no hay columna que la identifique. No admite clave natural:
clave sustituta más un `nro_muestra` asignado en la carga por orden estable.

---

### N-8 · `E03_ConteoEstados` sí tiene clave natural, y no es la del DDL · **Medio**

| Clave | Combinaciones | Total |
|---|---|---|
| `Fecha, Fundo, Modulo, Lote, Cortina, Hilera, Planta` *(la del DDL)* | 18.502 | 18.714 |
| **`Item, Fecha, Modulo, Lote, Cortina, Hilera, Planta`** | **18.714** | 18.714 |

La clave del DDL rechazaría 212 filas; incluyendo `Item` la clave es exacta. Y como el
`DISTINCT` de las 16 columnas también da 18.714, **`E03` no tiene ni un duplicado exacto**: esas
212 filas son mediciones distintas del mismo punto, no recargas.

---

### N-9 · Claves que no existen: `E02` y `H00` · **Medio**

**`E02_ConteoFlores` no tiene ninguna clave natural única** (43.490 filas):

| Clave | Combinaciones |
|---|---|
| `Fecha, Fundo, Modulo, Lote, Cortina, Hilera, Planta` | 42.790 |
| `+ Hora` | 43.138 |
| `Item, Fecha, Modulo, Lote, Cortina, Hilera, Planta` | 43.329 |

Como el plan espera conservar las 43.490 filas, se carga con clave sustituta y las 161 filas que
colisionan por la mejor clave disponible se registran en cuarentena para revisión, sin bloquear.

**`H00_VolumenCampo` tiene 151 filas de exceso** en 34 grupos por
`(Campaña, Fecha, Fundo, Modulo, Lote)`; `H01_ProdHistorica` solo 1 por su clave equivalente.
Relevante porque §4.5 designa H00 como referencia de KG: la reconciliación debe agregar por la
clave, no asumir unicidad.

Otras claves verificadas, todas correctas: `E04_Brotes` `(Fecha, Piso, Fundo, Modulo, Lote,
Cortina, Hilera, Planta)` → 3.385 = total · `M_Poda` `(Campaña, Fundo, Modulo, Turno, Lote)` →
2.159 = total · `M_Lotes` `(Fundo, Modulo, Lote)` → 860 = total.

---

### N-10 · El total de filas de la base está mal sumado · **Medio**

Los cuatro documentos abren con la misma cifra: **683.180 filas**. Aparece en el encabezado de
alcance de `01_AUDITORIA.md`, en su resumen ejecutivo, en el anexo de cifras de control §7, en
`02_LOGICA_NEGOCIO.md`, en `04_PLAN_MIGRACION.md` y en
`evidencia\04_metricas_validacion.txt` §1, donde figura como `TOTAL 683.180 (suma)`.

**Los recuentos tabla por tabla son todos correctos** — se verificaron uno a uno contra la base
y coinciden exactamente con los publicados. Lo que no cuadra es la suma:

| Grupo | Tablas | Filas |
|---|---|---|
| Evaluaciones `E0x` | E01 94.236 · E02 43.490 · E03 18.714 · E04 3.385 · E05 4.193 | 164.018 |
| Cosecha, packing y clima `H0x` | H00 30.812 · H01 30.626 · H02 117.536 · H05 155.588 | 334.562 |
| Maestros `M_x` | M_Lotes 860 · M_Time 2.189 · M_Poda 2.159 · M_nMuestra 681 · M_Evaluadores 31 · M_EquivalenciaElifab 15 | 5.935 |
| Forecast `R0x` | R08 101.715 · R09 48.368 | 150.083 |
| `Errores de pegado` | — | 0 |
| **TOTAL** | **18 tablas** | **654.598** |

La diferencia es de **28.582 filas (4,4%)** y no corresponde a ninguna tabla ni a ninguna
combinación de ellas: es un error aritmético, no un recuento omitido.

**Por qué importa aunque no cambie ningún dato.** Es la cifra que encabeza los cuatro
documentos y la que se usará para decir "la migración está completa". Si el ETL carga 654.598
filas y alguien la compara contra 683.180, la conclusión inmediata será que faltan 28.582
filas y que la migración perdió datos. El contrato de aceptación de `raw` se fija en
**654.598**, y el ETL lo tiene como constante con la explicación al lado
(`etl/src/aquanqa_etl/catalogo.py::TOTAL_FILAS_ORIGEN`), con una prueba que impide
"corregirlo" hacia la cifra publicada.

---

### N-11 · Las campañas se solapan: una fecha no determina la campaña · **Alto**

`04_PLAN_MIGRACION.md` §3.2 añade `campana_productiva` como columna de la dimensión de
tiempo, y la decisión D-2 la formula como "para cada campaña C2022–C2026, la fecha de inicio y
fin". Eso presupone que las campañas se suceden sin solaparse. No es así.

**Rango real observado, solo en cosecha (`H00_VolumenCampo`):**

| Campaña | Desde | Hasta | Solape con la siguiente |
|---|---|---|---|
| C2022 | 2022-07-25 | 2023-01-05 | — |
| C2023 | 2023-05-31 | 2024-02-16 | **61 días** con C2024 |
| C2024 | 2023-12-18 | 2025-04-22 | **40 días** con C2025 |
| C2025 | 2025-03-14 | 2026-03-05 | **11 días** con C2026 |
| C2026 | 2026-02-23 | 2026-07-29 | — |

Incorporando poda y forecast semanal, el solape llega a **354 días** entre C2024 y C2025. Al
construir el calendario, **832 de los 2.189 días tienen más de una campaña activa**.

**No es un defecto de los datos, es cómo funciona el cultivo.** La campaña de un lote depende
de cuándo se podó ese lote, y los lotes no se podan a la vez: `M_Poda` reparte la poda de
C2024 entre junio de 2023 y noviembre de 2024. Dos lotes pueden estar el mismo día en
campañas distintas.

**Consecuencias.**

1. **`core.calendario` no lleva `campania_id`.** Asignar una campaña a cada día obligaría a
   elegir arbitrariamente entre dos, y el `LEFT JOIN` contra un rango solapado además
   duplicaría filas — de hecho, el primer intento de cargar el calendario falló con clave
   duplicada en 2022-12-28, que es precisamente un día compartido por C2022 y C2023.
2. **La campaña se resuelve por lote**, con `core.fn_campania_de_lote(lote_id, fecha)`: la
   campaña de un lote en una fecha es la de su poda más reciente anterior. Dentro de un mismo
   lote no hay solape, así que ahí sí es determinista.
3. **D-2 está mal planteada.** Lo que hace falta de Planeamiento no son "fechas de corte" —no
   existen como tales—, sino confirmar la regla de asignación por poda. Se registra como
   `campania.origen_fechas = 'derivado'` hasta entonces.
4. Explica de raíz el defecto de `H0103_ResModulo`, que agrupa por año y campaña a la vez y
   parte los totales: año y campaña no son jerárquicos, son ortogonales.

---

### N-12 · Diámetros imposibles y conteos negativos · **Medio**

Valores que ninguna restricción del origen impedía:

| Caso | Filas | Rango observado | Efecto si se excluyeran |
|---|---|---|---|
| Diámetro de rama > 50 mm | 29 de 90.459 | hasta **8.789 mm** | la media baja de 10,89 a 10,62 |
| Diámetro de baya > 40 mm | 3 de 4.193 | hasta **13.381 mm** | la media baja de 19,89 a 16,34 |
| Conteos negativos | 2 filas | `-1` en E02 y E04 | — |

Una rama de 8,8 metros y una baya de 13 metros son imposibles; el patrón sugiere decimales
perdidos. **Se cargan igual**, porque las cifras de control que publica la auditoría los
incluyen y excluirlos rompería el contrato de aceptación, pero quedan marcados con
`sospechoso = true` y registrados en cuarentena para que Agronomía decida. Los conteos
negativos sí se convierten a NULL: un conteo no puede ser negativo y el origen ya usa NULL
para lo no medido.

---

### N-13 · `R08_Forecast_Campaña` tiene también una fila de subtotal · **Alto**

H-06 documenta tres filas de subtotal de Excel en `H00` y `H01`, con 1.925.995 kg. Hay una
cuarta, en la tabla de forecast, y es mucho mayor:

```
Version  Fundo  FundoPPto  Modulo  Turno  Año  Semana  Campaña  |  KG Exp
(vacío)  (vac)   (vacío)   (vac)   (vac)  (v)   (vac)   (vac)   |  25.433.998
```

**Mismo patrón exacto que H-06**: todos los identificadores vacíos y un valor grande en la
columna de kilos. La auditoría la menciona de pasada —en la tabla de versiones de `R08`
aparece una fila `(vacío) | 1`— pero no la identifica como subtotal ni cuantifica su efecto.

**Y su efecto no es menor:** son **25.433.998 kg, el 3,9%** de los 648.044.713,14 que
`01_AUDITORIA.md` §7 publica como cifra de control de `SUM([KG Exp])`. Es decir, esa cifra de
control incluye una fila de subtotal de Excel. Sin ella, el total es **622.610.715,14**.

Como la fila no tiene versión y toda medida de forecast debe filtrar por versión, en la
práctica ya quedaba fuera de cualquier tablero bien construido — pero entraba en cualquier
total sin filtrar, que es justo lo que hacen los informes hoy (advertencia §5 de
`03_GUIA_REPORTES.md`).

**Corrección.** Va a cuarentena con motivo `SIN_IDENTIFICADORES`, igual que las de H-06, y el
contrato de aceptación usa 622.610.715,14 como valor de `core.forecast_campania`.

---

### N-14 · H-07 resuelto: `H00` y `H01` contienen la misma cosecha · **Alto**

H-07 documenta que `H01_ProdHistorica` tiene 187 filas menos que `H00_VolumenCampo` en C2023
y C2024, con 4.486,59 kg de diferencia, y concluye que *"`H01` aplica algún criterio de
consolidación —un umbral mínimo, o un agrupamiento de registros menores— que `H00` no
aplica"*, marcándolo como pregunta abierta para Agronomía (decisión D-3).

**No hay tal criterio de consolidación.** Tras normalizar los códigos y resolver la identidad
de lote, ambas tablas contienen exactamente los mismos registros:

| | `H00` | `H01` |
|---|---|---|
| Filas en el origen | 30.812 | 30.626 |
| Menos las que no resuelven lote | −276 | −90 |
| **Filas con lote identificado** | **30.536** | **30.536** |
| Claves `(lote, fecha, campaña)` distintas | 30.536 | 30.536 |
| Claves presentes solo en una de las dos | 0 | 0 |
| **Diferencia total de kilos** | colspan | **0,01 kg** |

La diferencia de 187 filas se explica entera por otra cosa: **cada tabla arrastra un conjunto
distinto de filas cuyos lotes ya no están en el maestro vigente** — 276 en `H00` y 90 en
`H01` — más las 3 filas de subtotal de H-06. Comparar los recuentos crudos, sin normalizar
los códigos de lote ni apartar esas filas, produce el desfase aparente.

**Consecuencias.**

1. **D-3 deja de ser una pregunta para Agronomía.** No hay que elegir una "fuente de verdad":
   las dos dicen lo mismo. `H00` se mantiene como referencia de kilos por convención, y `H01`
   aporta paña, peso y plantas, que solo él trae.
2. La reconciliación se sigue calculando y guardando en `qua.reconciliacion_cosecha`, ahora
   como evidencia de que cuadran en lugar de como registro de una diferencia sin explicar.
3. Lo que sí requiere revisión agronómica son los **276 y 90 registros de lotes retirados del
   maestro** (M04/L078-L080 y similares): son cosecha real de lotes que ya no figuran, y están
   en cuarentena con motivo `LOTE_INEXISTENTE`.

---

### N-15 · Dos hechos con FK nula sin el mismo tratamiento que el resto · **Medio**

Un inventario completo de las 41 claves foráneas declaradas en `core` — no solo las que ya
se habían revisado — muestra que **solo 4 tienen algún nulo real** hoy. Verificarlas una por
una encontró dos inconsistencias de implementación, no dos decisiones:

| Columna | Nulos | El problema |
|---|---|---|
| `forecast_campania.modulo_id` | 624 de 101.714 | El módulo del origen no resolvía contra el maestro, y esas filas **nunca se registraban en `qua.rechazos`** — a diferencia de todos los demás hechos (ramas, flores, estados, brotes, bayas, cosecha), donde una identidad sin resolver siempre deja rastro |
| `forecast_semanal.lote_id` | 23 de 48.368 | Sí se registraban en cuarentena, **pero además quedaban en `core` con `lote_id` NULL** — doble contabilidad: la fila estaba a la vez "excluida" (en cuarentena) y "incluida" (en `core`), sin que el patrón del resto de hechos se respetara |
| `cosecha.variedad_id` | 4 de 30.540 | Legítimo, no es un fallo: son las 4 filas que solo existen en `H01_ProdHistorica`, que **nunca tuvo columna de variedad** en el origen |
| `fundo_alias.fundo_id` | 7 de 23 | Por diseño: la tabla existe para registrar alias que no determinan un fundo físico; la columna `ambiguo` ya gobierna ese caso, no requiere cambio |

**Corrección adoptada (ADR-0005):** las tablas de hechos ya no dejan ninguna FK en NULL.
Cuando la identidad no resuelve, la fila apunta a una fila centinela `es_sentinel = true`
("Sin identificar") en la dimensión correspondiente — `empresa`, `fundo`, `modulo`, `turno`,
`variedad` y `lote` la llevan — y sigue registrándose en cuarentena con su motivo, como el
resto. Los recuentos de `core.forecast_campania` (101.714), `core.forecast_semanal` (48.368)
y `core.cosecha` (30.540) no cambian: el centinela repuebla el valor, no excluye la fila.

Al registrar las 624 filas de `forecast_campania` se usó al principio el motivo
`LOTE_INEXISTENTE`, ya existente. Fue un error: infló ese motivo de ~730 a 1.352 filas,
por encima de su tope (900, calibrado solo para lotes) y mezclando dos problemas distintos
en un mismo contador — el de `forecast_campania` es de **módulo**, no de lote. Se corrigió
con un motivo propio, `MODULO_INEXISTENTE` (tope 700), verificado tras recargar: 728 en
`LOTE_INEXISTENTE` y 624 en `MODULO_INEXISTENTE`, ambos dentro de su tope.

---

### N-16 a N-22 · Hallazgos de la auditoría de mapeo columna por columna

Al cruzar las **235 columnas** de `evidencia/02_esquema_tablas.txt` contra el esquema y los
datos reales de `core`, aparecieron siete hallazgos más. El detalle completo —el destino de
cada columna y la clasificación de todos los nulos— está en
[`../modelo/01_mapeo_access_core.md`](../modelo/01_mapeo_access_core.md).

| # | Hallazgo | Gravedad |
|---|---|---|
| **N-16** | **`packing.peso_kg` guarda el total del grupo, no el peso de la fila.** `Peso total (kg)` y `Peso total (kg)2` se trataron como duplicados y se eligió la segunda por tener menos nulos. Son numerador y denominador de un porcentaje: `% ≈ 100 × peso1 / peso2` con error medio de 0,25 pp, y `peso2` es constante dentro de (fecha proceso, módulo, turno, lote) en 2.535 de 2.591 grupos. `core.packing` reporta hoy **789.597.707 kg** frente a **32.386.650 kg** de cosecha real: sumar esa columna infla los kilos **~24 veces**. Es el mismo defecto estructural que B-4, en el otro extremo del pipeline | **Crítico** |
| **N-17** | **`E03_ConteoEstados.F16` es la hora de captura, no un residuo.** 13.230 valores no vacíos, el 100 % con formato de hora (`04:25:03`–`22:42:03`). Se descartó como basura, mientras que `E02` y `E04` sí conservan la suya | Medio |
| **N-18** | **El turno se descarta en cinco tablas** (`H01`, `E05`, `M_Poda`, `M_nMuestra`, `R09`) mientras `R08` sí lo persiste. Suele ser derivable del lote, pero nadie lo ha comprobado y no está documentado | Medio |
| **N-19** | **390 filas de packing traen un nombre de programa en `Contenedores volcados`**, con `Programa de clasificación` vacío en las 390. Hoy el casteo las anula sin dejar registro: es la causa de que `core` tenga 13.475 nulos donde Access tiene 13.085 | Bajo |
| **N-20** | **52 fechas de `M_Poda.FInicio` valen `1899-12-30`**, el cero de la época de Excel. Access declara 2 nulos cuando en realidad faltan 54. El casteo ya las convierte a NULL, que es lo correcto — la migración es más honesta que el origen, pero la diferencia parecía una pérdida | Bajo · *resuelto* |
| **N-21** | **Seis columnas de H02 descartadas por "duplicadas" no lo son**: `ACDT 2` coincide con `ACDT` en solo 15.950 de 117.536 filas; `ENSAYO` difiere de `Mercado` en 19.286; `S26`/`S271` son rangos distintos entre sí; `Packet` y `Clasificación` tienen valores propios no derivables. Son campos de Elifab sin documentar | Medio |
| **N-22** | **La cifra de N-9 quedó obsoleta para `H00`.** Hoy hay **0 grupos** con la clave natural repetida en `stg.h00_cosecha` y 0 rechazos con ese origen: los 116 de `CLAVE_NATURAL_REPETIDA` vienen todos de `E02_ConteoFlores`. La normalización de identidad (N-3) resolvió el problema, pero el código y el párrafo de N-9 más arriba siguen citando "34 grupos / 151 filas" | Bajo |

**Cobertura del mapeo:** 211 de 235 columnas tienen destino en `core`; 18 no lo tienen de forma
justificada (columnas 100 % vacías, duplicados reales o valores derivables) y 6 son las pérdidas
no justificadas de N-17, N-18 y N-21.

---

## 3 · Bloque B · Hallazgos sobre el BI en producción

Verificados en el TMDL de `pbi/` (`SEGUIMIENTO DE CAMPAÑA`, `SEGUIMIENTO DE PERSONAL`).

### B-1 · El reporting depende de un archivo en una carpeta de descargas · **Crítico**

Las particiones de **ambos** informes leen:

```
Access.Database(File.Contents("C:\Users\gsanchez\Downloads\BD_AQUANQA_26.accdb"))
```

`SEGUIMIENTO DE PERSONAL` lee además un Excel de tareo en una biblioteca SharePoint del mismo
usuario:

```
Excel.Workbook(File.Contents("C:\Users\gsanchez\AQUANQA\Oficinas Prize Peru - Cosecha y
  Operaciones\Gi Cosecha y Operaciones\Dt_Querys\AGRITRAICER\Query Tareo 2026.xlsx"))
```

Los tableros de gerencia dependen de dos archivos en el equipo personal de un usuario. No hay
servidor, ni copia, ni control de acceso. Es el argumento operativo más fuerte de la migración,
y no aparece en ninguno de los cuatro documentos.

### B-2 · Las dimensiones están fabricadas desde las tablas de hechos · **Alto**

`SEGUIMIENTO DE CAMPAÑA` no tiene dimensiones: las deriva con DAX de los propios hechos.

| Dimensión | Definición real | Problema |
|---|---|---|
| `LOTE` | `SUMMARIZECOLUMNS(H0101_ResumenHistoricos[Lote])` | **una sola columna, sin módulo**: `L001` de M01 y `L001` de M05 son la misma fila. Filtrar por lote mezcla lotes físicos distintos |
| `MODULO` | `SUMMARIZECOLUMNS(H0101_ResumenHistoricos[Modulo])` | sin fundo: M01–M04 pertenecen a dos fundos (N-4) y se colapsan |
| `TURNO` | `SUMMARIZECOLUMNS(H0101_ResumenHistoricos[Turno])` | igual: el turno solo tiene sentido dentro de un módulo |
| `EMPRESA` | `SUMMARIZECOLUMNS('0305_Brotes_Ramas'[Empresa])` | se deriva de una consulta que desciende de `0101_Diametros`, la del join roto de H-01 |
| `FUNDO_CAMPO` | `SUMMARIZECOLUMNS('0201_Flores'[FUNDO_CAMPO])` | columna calculada en Power Query, ver B-3 |

Las relaciones cruzan hechos contra dimensiones derivadas de **otro** hecho: `0201_Flores.Modulo
→ MODULO.Modulo`, donde `MODULO` sale de `H0101_ResumenHistoricos`. Un módulo que aparezca en
flores pero no en cosecha histórica queda fuera del filtro sin señal alguna.

Es H-02 manifestándose en producción: sin dimensiones ni claves declaradas en el origen, el
analista tuvo que inventarlas, y las inventó con el grano equivocado.

### B-3 · El mapeo módulo → fundo es incorrecto · **Alto**

Columna calculada presente en `0201_Flores` y `0301_ConteoEstados`:

```dax
SWITCH(TRUE(),
    [Modulo] IN {"M01","M02","M03","M04"},                          "Arena Azul",
    [Modulo] = "M05",                                               "Quri Allpa",
    [Modulo] IN {"M06","M07","M08","M09","M10A","M10B","M11","M16"},"Kawsay Allpa",
    [Modulo] IN {"M12","M13","M14","M15"},                          "Ayllu Allpa",
    BLANK())
```

Contra el maestro vigente:

| Módulos | Asigna | Correcto | Estado |
|---|---|---|---|
| M01–M04 | Arena Azul | **repartidos entre `Aqu Anqa 1`/Arena Azul y `Aqu Anqa 2`/Quri Allpa** | ✗ |
| M05 | Quri Allpa | Quri Allpa | ✓ |
| M06–M10B | Kawsay Allpa | Kawsay Allpa (`Aqu Anqa 3`) | ✓ |
| M11, M16 | Kawsay Allpa | Kawsay Allpa **ii** (`Aqu Anqa 5`) | ✗ (coincide solo porque se colapsan, ver abajo) |
| M12–M15 | Ayllu Allpa | Ayllu Allpa | ✓ |
| **M17, M18** | `BLANK()` | `Aqu Anqa 5` | ✗ |
| **M19–M24** | `BLANK()` | `Aqu Anqa 6` | ✗ |

Y en Power Query, `FUNDO_CAMPO` se obtiene partiendo `Fundo_pptom5` por `-` y aplicando cinco
`Table.ReplaceValue`, uno de los cuales colapsa dos fundos distintos:

```m
Table.ReplaceValue(..., "Kawsay Allpa ii", "Kawsay Allpa", ...)   // Aqu Anqa 5 → Aqu Anqa 3
```

**Efecto en el tablero:** los lotes de M01–M04 de la empresa `Aqu Anqa II` se reportan como
Arena Azul; `Aqu Anqa 5` no existe como categoría; y los cinco módulos M17–M24 aparecen en
blanco. Corregirlo **cambiará lo que ve gerencia**, y conviene anticiparlo igual que los cambios
del §5 de `03_GUIA_REPORTES.md`.

### B-4 · `KG/HA` está mal calculado · **Alto**

```dax
KG/HA = SUM(H0101_ResumenHistoricos[KG]) / SUM(H0101_ResumenHistoricos[Area])
```

`Area` es un atributo del lote que `H0101_ResumenHistoricos` trae repetido en cada fila de
cosecha (una por fecha y paña). `SUM(Area)` suma la superficie del lote tantas veces como
cosechas tenga: **el denominador se multiplica por el número de pañas y el rendimiento por
hectárea sale subestimado en la misma proporción**.

El área debe tomarse de la dimensión de lote —una vez por lote—, no sumarse desde el hecho.

### B-5 · El linaje de la auditoría no midió el consumo real · **Medio**

`01_AUDITORIA.md` H-12 y `02_LOGICA_NEGOCIO.md` §6 concluyen que `E05_DiametrosBayas`,
`M_Evaluadores` y `M_nMuestra` "no llegan a ningún tablero", y §7 plantea como preguntas sin
responder la predicción de calibre y la consistencia entre evaluadores.

`SEGUIMIENTO DE PERSONAL` **sí lee `E05_DiametrosBayas`**, directamente desde la tabla, y **sí
mide la consistencia entre evaluadores**, con medidas propias:

```
CV Evaluador · Desv Std Evaluador · Promedio Evaluador · Flores por Hora · Frutos por Hora
Plantas por Hora · Flores por Evaluador Día · Jornadas Evaluador · Evaluadores Activos
Horas Hombre Flores · HORAS TRABAJADAS
```

La conclusión de la auditoría es correcta **dentro de Access** —ninguna de las 40 consultas las
usa— pero incorrecta sobre el consumo real: Power BI lee tablas crudas, no solo consultas. El
linaje del modelo destino debe medirse sobre los dos informes, no sobre el `.accdb`.

### B-6 · Hay lógica de negocio que solo existe en Power Query · **Medio**

Cuatro tablas del modelo de PERSONAL no corresponden a ningún objeto de la base —se verificó:
la base tiene exactamente 18 tablas y 41 consultas, y ninguna se llama así—. Son
transformaciones definidas en Power Query:

| Tabla del modelo | Qué hace |
|---|---|
| `RESUM_FLORES` | `Table.Group(E02_ConteoFlores, {Fecha, Evaluador}, sum(nFlores))` |
| `RESUM_FRUTOS` | `Table.Group(E03_ConteoEstados, {Fecha, Evaluador}, count(*) as PLANTAS, sum(Total) as FRUTOS)` |
| `TAB RESUM_FL` | une ambas y filtra `PLANTAS = null and FLORES <> 0`: **jornadas con flores contadas y sin frutos registrados** — un control de calidad de captura que no existe en ningún otro sitio |
| `TAB RESUM_FR` | el simétrico |

Esa lógica debe bajar a `reporting` para no vivir en tres capas a la vez. `TAB RESUM_FL` merece
atención especial: es una regla de validación de negocio que hoy solo conoce un archivo `.pbix`.

Además, ambos informes tienen `__PBI_TimeIntelligenceEnabled = 1`, lo que genera **10 tablas
`LocalDateTable_*` automáticas** conviviendo con un `BD_Calendario` propio. Ese `BD_Calendario`
ya aporta el `Trimestre` que a `M_Time` le falta (H-04 caso 5) y las columnas `Año-Semana`,
`AñoMes`, `Día Semana` que `dim_tiempo` debe ofrecer para que el reapuntado no pierda nada.

---

## 4 · Bloque C · Efecto sobre las decisiones pendientes

| Decisión | Estado en `04_PLAN_MIGRACION.md` | Estado tras verificar |
|---|---|---|
| **D-1** · qué kilos compara `R0902` | Pendiente de Planeamiento | Se implementa con `[KG Exp]` (precedente de `R0801_ResCampaña`), parametrizado en `core.config_decision`. Cambiarlo es un `UPDATE` |
| **D-2** · fechas de corte de campaña | Pendiente de Planeamiento | **Mal planteada** (N-11): las campañas se solapan y una fecha no determina la campaña. Lo que hace falta confirmar es la regla de asignación por poda, no unas fechas de corte |
| **D-3** · reconciliación H00/H01 | Pendiente de Agronomía | **Cerrada por los datos** (N-14): las dos tablas contienen la misma cosecha, con 0,01 kg de diferencia. No hay que elegir fuente de verdad |
| **D-4** · correspondencia del vocabulario A | *"bloquea todo lo demás"* en la versión original | **Resuelta por los datos** (N-5): el maestro vigente sustituye el vocabulario A y R08/R09 confirman la equivalencia |
| **D-5** · los 5 lotes duplicados | Obsoleto | Confirmado obsoleto: `(Fundo, Modulo, Lote)` es único en las 860 filas de Access |
| **D-6** · filtros fijos de campaña | Regla de diseño | Sin cambios |

---

## 5 · Cifras de control corregidas

Sustituyen o complementan a `01_AUDITORIA.md` §7 y `04_PLAN_MIGRACION.md` §7.

### Se retiran

| Métrica | Valor publicado | Motivo |
|---|---|---|
| **Total de filas de la base** | **683.180** | **La suma de las 18 tablas es 654.598 (N-10)** |
| `E01 SUM([# Ramas])` | 730.318 | Suma de índices de rama, no un total de ramas (N-1) |
| `E01` filas únicas por clave de planta | 71.095 | La cifra es correcta, la clave no: son filas completas distintas (N-1) |
| `dim.variedad` ≈ 5 filas | — | `M_Lotes` tiene 1 variedad; los hechos tienen ~14 grafías (N-6) |

### Se incorporan

| Métrica | Valor verificado |
|---|---|
| **Total de filas de las 18 tablas del origen** | **654.598** |
| `E01` total de ramas declaradas (`Max<5 + Max>5` por planta) | **110.095** |
| `E01` cabeceras de planta evaluada | **5.384** |
| `E01` filas completas distintas *(objetivo de `rama_medicion`)* | **71.095** |
| `E01 AVG(Diametro)` sobre filas distintas | **10,8869165079781** |
| `E01` conflictos (punto + nro de rama con diámetro distinto) | **4.557** |
| `E05` bayas por combinación hilera/fecha | ~97 (43 combinaciones) |
| Maestro vigente: lotes · módulos · fundos · turnos | **879 · 25 · 6 · 13** |
| Huérfanos totales tras normalizar códigos | **~732 filas (0,26%)** |

> **Nota sobre `AVG(Diametro)`.** La auditoría publica 10,8870645965645 y la verificación da
> 10,8869165079781: difieren en el sexto decimal, probablemente por la precisión de `Single` en
> el promedio intermedio. El contrato de aceptación fija tolerancia **±1e-4** en esta métrica en
> lugar de igualdad exacta.

---

## 6 · Lo que la verificación confirma sin cambios

Para que quede constancia de qué parte de la auditoría se sostuvo íntegra:

- **H-01** · los cuatro vocabularios de fundo, tal como se describen, con sus conteos exactos.
- **H-02** · 0 FK, 4 índices, las tres PK y su evaluación.
- **H-03** · 23.141 filas de exceso en `E01_Ramas` y 5.383 grupos con duplicados (la
  verificación da 5.384 combinaciones totales, de las cuales 5.383 tienen más de una fila:
  coincide).
- **H-04** · las 6 consultas rotas y la causa de cada una.
- **H-05** · 9.040 → 487.368 filas y el grano diario de `M_Time`.
- **H-06** · las 3 filas de subtotal y sus 1.925.995 kg, aisladas de nuevo por su
  `(Modulo, Lote)` vacío.
- **H-07** · el desfase de 187 filas entre `H00` y `H01`, campaña por campaña.
- **H-08** · 2.079 grupos de clima duplicados.
- **H-09** · el enlace de evaluadores por DNI y los 2 sin maestro.
- **H-10** · el tipado de `H02_BDElifab` y sus 5 pares de columnas duplicadas.
- Todas las cifras de `evidencia\04_metricas_validacion.txt` §1 a §6.

El diagnóstico era sólido. Lo que faltaba era medir el grano antes de declarar las claves.
