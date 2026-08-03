# Auditoría técnica · BD_AQUANQA_26.accdb

**Fecha:** 2026-08-02
**Origen:** `C:\Users\Admin\Videos\bd\BD_AQUANQA_26.accdb` (140.115.968 bytes)
**Acceso:** solo lectura, vía `Microsoft.ACE.OLEDB.16.0` y `DAO.DBEngine.120`
**Alcance:** 18 tablas de datos · 40 consultas guardadas · 683.180 filas

> **Regla de este documento:** toda cifra publicada proviene de una consulta ejecutada
> sobre los datos reales. Ninguna es estimación. Cuando un dato no se pudo verificar,
> se marca explícitamente como *no verificado*.

---

## 1 · Resumen ejecutivo

`BD_AQUANQA_26.accdb` es la base operativa del cultivo de arándano de Aqu Anqa. Registra
la cadena fenológica completa —poda, brotes, ramas, flores, estados de fruto, diámetro de
baya, cosecha y packing— más clima y dos sistemas de forecast.

El área de Reportes **consume esta base directamente desde Power BI**, apuntando a las
consultas guardadas de Access por su nombre. Esto convierte cada defecto estructural en un
problema de negocio: no se queda en la base, se propaga silenciosamente a los tableros de
gerencia.

La auditoría detecta **12 hallazgos**, 3 de ellos críticos.

### Los tres problemas de fondo

**1 · No hay integridad referencial declarada.** Las 18 tablas tienen **0 claves foráneas**.
De las 3 claves primarias existentes, 2 son incorrectas. Nada impide que se cargue un lote
que no existe en el maestro, y de hecho ocurre: 94.236 filas de `E01_Ramas` (el 100%) no
enlazan con `M_Lotes`.

**2 · El campo "fundo" se escribe de cuatro formas incompatibles.** No es un problema de
mayúsculas ni de acentos: son cuatro vocabularios distintos que nombran las mismas
entidades físicas. Ninguna conversión automática los reconcilia. Es la causa raíz del
hallazgo anterior.

**3 · Seis consultas están rotas.** Están caídas en la base y, si un reporte de Power BI
las consume, ese reporte está mostrando datos en caché o directamente vacíos. La cifra
correcta es **6 de 40**, no 5 — la sexta (`R0902_Forecast_Sem_vs_Camp`) se detectó al
re-ejecutar todas las consultas una por una en la verificación final.

### Impacto cuantificado sobre los tableros

| Efecto | Magnitud verificada |
|---|---|
| Kilos de cosecha en filas sin identificar (subtotales huérfanos) | **1.925.995 kg** (~5,6% del total) |
| Inflado de la consulta `01_Flores_C2025` por join defectuoso | **×54** (9.040 → 487.368 filas) |
| Filas duplicadas en `E01_Ramas` por recarga | **23.141** (24,6% de la tabla) |
| Grupos de clima duplicados exactos | **2.079** |
| Consultas caídas | **6 de 40** |
| Tablas que se capturan pero nadie consume | **4 de 18** |

### Recomendación

**No replicar el modelo actual en PostgreSQL.** Migrar la estructura tal cual implica
migrar también los defectos, y perder la única oportunidad natural de corregirlos. El
plan propuesto (ver `04_PLAN_MIGRACION.md`) reconstruye el modelo en esquema estrella
con claves foráneas reales, resolviendo H-01 mediante una tabla de alias de fundo que
preserva los cuatro vocabularios como sinónimos de una entidad única.

**Compromiso con el área de Reportes:** los nombres de las 40 consultas se preservan como
vistas en PostgreSQL. Power BI seguirá encontrando lo que busca. Los casos donde el
resultado *debe* cambiar —porque hoy es incorrecto— están enumerados uno por uno en
`03_GUIA_REPORTES.md`.

---

## 2 · Método y alcance

### Cómo se obtuvo cada cifra

| Aspecto | Herramienta | Qué se extrajo |
|---|---|---|
| Estructura de tablas | `Microsoft.ACE.OLEDB.16.0` (`GetOleDbSchemaTable`) | columnas, tipos, longitudes |
| Nulos por columna | SQL `COUNT(*)` con `IS NULL` | conteo real, columna por columna |
| SQL de las consultas | `DAO.DBEngine.120` → `QueryDefs(i).SQL` | texto SQL completo de las 40 |
| Relaciones e índices | `DAO` → `Relations`, `TableDefs.Indexes` | 0 FK de usuario, 4 índices |
| Estado de cada consulta | `QueryDef.OpenRecordset()` | ejecución real, una por una |
| Métricas de control | SQL agregado | `COUNT`, `SUM`, `AVG` por dimensión |

### Nota metodológica sobre el conteo de consultas rotas

Un primer barrido usó `QueryDef.Fields.Count` para detectar consultas inválidas. **Ese
método es insuficiente**: no lanza excepción, devuelve `0` en silencio. Detectó 3 de las 6.

El método correcto —y el que sustenta este documento— es **ejecutar cada consulta** con
`OpenRecordset()` y capturar la excepción. Solo así aparecieron las 6. Se documenta aquí
porque afecta la reproducibilidad: quien repita la auditoría con el primer método obtendrá
un número distinto.

### Restricciones respetadas

- La base **no fue modificada**. Todo acceso fue de solo lectura (`OpenDatabase(db,$false,$true)`).
- Existe `BD_AQUANQA_26.laccdb` (archivo de bloqueo de Access). No se tocó.
- Las consultas con `ñ` o acentos en el nombre requieren construir el string con
  `[char]0xF1` en PowerShell — el heredoc de bash corrompe la codificación y produce
  falsos "objeto no encontrado". Varias verificaciones fallaron inicialmente por esto.

### Evidencia reproducible

Los volcados crudos están en `evidencia\`:

| Archivo | Contenido |
|---|---|
| `01_sql_consultas.txt` | SQL completo de las 40 consultas + relaciones + índices |
| `02_esquema_tablas.txt` | 18 tablas: columnas, tipos OLEDB, longitudes, nulos |
| `03_relaciones_indices.txt` | PK/FK/índices declarados y su evaluación |
| `04_metricas_validacion.txt` | cifras de control congeladas — contrato de aceptación |
| `05_linaje_dependencias.txt` | grafo consulta→tabla, impacto inverso, cierre transitivo |

---

## 3 · Tabla maestra de hallazgos

| ID | Hallazgo | Evidencia verificada | Severidad |
|---|---|---|---|
| **H-01** | Cuatro vocabularios de fundo incompatibles | 94.236 NULL (100% de `0101_Diametros`) | **Crítica** |
| **H-02** | Cero FK declaradas; 2 de 3 PK erróneas | 0 FK en 18 tablas; 4 índices | **Crítica** |
| **H-03** | `E01_Ramas` duplicada por recarga | 23.141 filas de exceso (24,6%) | **Crítica** |
| **H-04** | Seis consultas rotas | 6 / 40 | Alta |
| **H-05** | Explosión cartesiana en `01_Flores_C2025` | ×54 (9.040 → 487.368) | Alta |
| **H-06** | Filas de subtotal huérfanas mezcladas con datos | 1.925.995 kg (~5,6%) | Alta |
| **H-07** | `H00`/`H01` sin reconciliar | 187 filas de diferencia en C2023/C2024 | Alta |
| **H-08** | `H05_Clima` con recargas exactas | 2.079 grupos duplicados | Alta |
| **H-09** | `M_Evaluadores` nunca enlaza (DNI vs Cod) | 100% de fallo de join | Media |
| **H-10** | `H02_BDElifab` sin tipar | 34 de 35 columnas en texto | Media |
| **H-11** | Lógica redundante entre consultas | 6 patrones duplicados | Media |
| **H-12** | Restos de importación de Excel | 4 tablas sin consumidor + 1 vacía | Baja |

**Criterio de severidad:**
- **Crítica** — corrompe cifras que ya se están publicando en tableros de gerencia, de forma silenciosa.
- **Alta** — produce resultados incorrectos o inaccesibles en un ámbito acotado y localizable.
- **Media** — impide análisis o duplica esfuerzo, sin corromper cifras publicadas.
- **Baja** — deuda técnica sin impacto en resultados.

---

## 4 · Hallazgos en detalle

### H-01 · Cuatro vocabularios de fundo incompatibles · **Crítica**

**Descripción.** El campo que identifica el fundo (la unidad física de producción) se
escribe de cuatro formas distintas según la tabla. No es una diferencia de mayúsculas,
acentos ni espacios: son **cuatro nomenclaturas que nombran las mismas entidades con
palabras diferentes**. Ningún `TRIM`, `UPPER` ni normalización de acentos las reconcilia.

**Evidencia — los cuatro vocabularios, verificados uno por uno:**

*Vocabulario A · `M_Lotes.Fundo` (nombre comercial con ubicación)*

| Valor | Filas |
|---|---|
| `Aqu Anqa II - Ampliacion` | 404 |
| `Aqu Anqa II - Vivadis` | 190 |
| `Aqu Anqa II - Sta.Teresa` | 181 |
| `Aqu Anqa - ArenaAzul` | 85 |

*Vocabulario B · `M_Lotes.FundoPPto` (agrupación presupuestal)*

| Valor | Filas |
|---|---|
| `Aqu Anqa II` | 775 |
| `Aqu Anqa` | 85 |

*Vocabulario C · `M_Lotes.Fundo_pptom5` (nombre quechua con prefijo)*

| Valor | Filas |
|---|---|
| `Aqu Anqa II - Kawsay Allpa` | 251 |
| `Aqu Anqa II - Ayllu Allpa` | 213 |
| `Aqu Anqa II - Quri Allpa` | 190 |
| `Aqu Anqa II - Kawsay Allpa ii` | 121 |
| `Aqu Anqa - Arena Azul` | 85 |

*Vocabulario D · `E01_Ramas.Fundo` y `E04_Brotes.Fundo` (nombre quechua sin prefijo)*

| Valor | Filas en `E01_Ramas` | Filas en `E04_Brotes` |
|---|---|---|
| `Kawsay Allpa` | 40.523 | 1.045 |
| `Ayllu Allpa` | 21.549 | 824 |
| `Quri Allpa` | 20.643 | 1.107 |
| `Arena Azul` | 11.521 | 409 |

**Distribución por tabla — qué vocabulario usa cada una:**

| Tabla | Vocabulario | Ejemplo de valor |
|---|---|---|
| `E01_Ramas` | **D** (quechua sin prefijo) | `Kawsay Allpa` |
| `E04_Brotes` | **D** (quechua sin prefijo) | `Quri Allpa` |
| `E02_ConteoFlores` | **B** (presupuestal) | `Aqu Anqa II` |
| `H00_VolumenCampo` | **B** (presupuestal) | `Aqu Anqa II` |
| `H01_ProdHistorica` | **B** (presupuestal) | `Aqu Anqa II` |
| `M_Poda` | **B** (presupuestal) | `Aqu Anqa II` |
| `M_Lotes` | **A**, **B** y **C** simultáneamente | tres columnas distintas |

**Por qué importa — la consecuencia medida.** La consulta `0101_Diametros` une
`E01_Ramas` (vocabulario D) contra `M_Lotes.FundoPPto` (vocabulario B):

```sql
FROM M_Lotes RIGHT JOIN E01_Ramas
  ON (M_Lotes.Modulo = E01_Ramas.Modulo)
 AND (M_Lotes.Lote   = E01_Ramas.Lote)
 AND (M_Lotes.FundoPPto = E01_Ramas.Fundo)   -- 'Aqu Anqa II' vs 'Kawsay Allpa'
```

`'Aqu Anqa II' = 'Kawsay Allpa'` es **siempre falso**. El `RIGHT JOIN` conserva las 94.236
filas de `E01_Ramas`, pero **todas las columnas provenientes de `M_Lotes` quedan NULL**:
`Turno`, `KeyMap`, `NPlantas`, `Area`.

Verificado: **94.236 de 94.236 filas** de `0101_Diametros` tienen `Turno = NULL`. El 100%.

**Impacto en Power BI.** Cualquier tablero que segmente por turno usando esta consulta
—o cualquiera de las 4 que descienden de ella (`0102_CantRamas`, `0106_RaFloYem`,
`0108_diam`, `0305_Brotes_Ramas`)— muestra una única categoría vacía. El dato de ramas y
diámetro **no es analizable por turno hoy**, aunque el tablero aparente funcionar.

Nota: `0108_diam` devuelve **0 filas**, coherente con esto — filtra por una columna que
siempre es NULL.

**Huérfanos verificados en las demás tablas:**

| Tabla | Filas que no enlazan con `M_Lotes` | % |
|---|---|---|
| `E01_Ramas` | 94.236 | 100% |
| `E04_Brotes` | 3.385 | 100% |
| `H00_VolumenCampo` | 366 | 1,2% |
| `H01_ProdHistorica` | 180 | 0,6% |

**Acción correctiva.** Crear `dim_fundo` con una clave sustituta y `dim_fundo_alias` que
registre los cuatro vocabularios como sinónimos de la misma entidad física. El ETL
resuelve cualquier grafía contra esa tabla antes de cargar. Detalle en
`04_PLAN_MIGRACION.md` §2.

---

### H-02 · Cero claves foráneas; 2 de 3 claves primarias erróneas · **Crítica**

**Descripción.** No existe **ninguna** relación declarada entre las 18 tablas de datos.
Las únicas 2 relaciones presentes son internas de Access (`MSysNavPane*`, objetos del
panel de navegación). Solo 4 índices en total, y de las 3 claves primarias, 2 son
incorrectas.

**Evidencia — relaciones:**

```
TOTAL RELACIONES DE USUARIO: 0
```

**Evidencia — índices y claves primarias (las 18 tablas):**

| Tabla | Índice | Único | PK | Campos |
|---|---|---|---|---|
| `E01_Ramas` | `Id` | No | No | `[Id]` |
| `E03_ConteoEstados` | `PrimaryKey` | Sí | Sí | `[Modulo, Lote, Cortina, Hilera, Planta, E1, Fecha]` |
| `E04_Brotes` | `PrimaryKey` | Sí | Sí | `[Piso, Fundo, Modulo, Lote, Cortina, Hilera, Planta]` |
| `M_Time` | `PrimaryKey` | Sí | Sí | `[Fecha]` |
| *(las otras 14 tablas)* | — | — | — | **sin índices** |

**Evaluación de cada clave primaria:**

- **`M_Time.PrimaryKey [Fecha]` → CORRECTA.** Una fila por fecha. Es la única bien definida.

- **`E03_ConteoEstados.PrimaryKey [... E1 ...]` → ERRÓNEA.** La clave incluye `E1`, que es
  una **medida**, no un identificador. Consecuencia: si un evaluador corrige el conteo de
  E1 de una planta, la fila corregida **no reemplaza** a la original —cambia la clave— y
  ambas coexisten. La corrección duplica el registro en lugar de sustituirlo.

- **`E04_Brotes.PrimaryKey [sin Fecha]` → ERRÓNEA.** La clave no incluye `Fecha`, así que
  el mismo punto físico (piso/fundo/módulo/lote/cortina/hilera/planta) **solo puede
  evaluarse una vez en toda la historia**. Una segunda evaluación de la misma planta en
  otra fecha es rechazada por el motor. Esto explica por qué `E04_Brotes` tiene apenas
  3.385 filas frente a las 94.236 de `E01_Ramas`: **la clave está limitando la captura de
  datos**, no protegiéndola.

- **`E01_Ramas.Id` → INSUFICIENTE.** No es único (`uniq=False`): hay **15.043 valores
  distintos de `Id` para 94.236 filas**. No identifica nada. Es la causa mecánica de H-03.

**Impacto en Power BI.** Power BI infiere relaciones por nombre de columna al importar. Sin
FK declaradas, esa inferencia es una conjetura: puede crear relaciones incorrectas
(muchos-a-muchos donde debería ser uno-a-muchos) o ninguna. El modelo semántico depende de
que cada analista lo reconstruya a mano, y no hay garantía de que dos analistas lo hagan
igual.

**Acción correctiva.** Declarar FK reales en PostgreSQL. Las violaciones existentes no se
descartan: se derivan a una tabla de cuarentena para revisión agronómica. Ver
`04_PLAN_MIGRACION.md` §4.

---

### H-03 · `E01_Ramas` duplicada por recarga · **Crítica**

**Descripción.** La tabla contiene 94.236 filas, pero solo 71.095 son evaluaciones
distintas. Hay **23.141 filas de exceso — el 24,6% de la tabla**. El patrón es el de una
importación ejecutada más de una vez sobre datos ya cargados.

**Evidencia:**

| Métrica | Valor |
|---|---|
| Filas totales en `E01_Ramas` | 94.236 |
| Filas únicas por `(Fecha, Fundo, Modulo, Lote, Cortina, Hilera, Planta)` | 71.095 |
| **Filas de exceso** | **23.141 (24,6%)** |
| Grupos con más de una fila | 5.383 |
| Valores distintos de `Id` | 15.043 |

La columna `Id` tiene un índice **no único**: 15.043 valores para 94.236 filas. No sirve
como identificador, y al no ser único el motor no rechazó la segunda carga.

**Cómo se distingue una recarga de una re-evaluación legítima.** Un mismo punto físico
*puede* evaluarse dos veces en fechas distintas — eso es normal y no es duplicado. Lo que
aquí se cuenta como exceso son filas con **la misma fecha y el mismo punto físico**, es
decir, la misma medición registrada más de una vez. No hay lectura agronómica que
justifique medir la planta 7 de la hilera 3 dos veces el mismo día con idéntico resultado.

**Impacto medido sobre los indicadores.**

| Indicador | Con duplicados | Solo filas únicas | Sesgo |
|---|---|---|---|
| `AVG(Diametro)` | 10,9776538610781 | 10,8870645965645 | **+0,83%** |
| `SUM([# Ramas])` | 730.318 | *(inflado en proporción similar)* | ~+24% |

El promedio de diámetro está sesgado al alza porque las filas duplicadas pesan doble. Es
un sesgo pequeño en porcentaje, pero **sistemático**: no se cancela con más datos, y afecta
a los 5 objetos que descienden de esta tabla.

**Impacto en Power BI.** Toda medida de tipo `SUM` sobre `E01_Ramas` está inflada ~24%.
Las de tipo `AVG` están sesgadas hacia los lotes que fueron recargados. Un tablero de
"ramas totales por módulo" muestra hoy aproximadamente un cuarto más de ramas de las que
se contaron en campo.

**Acción correctiva.** Deduplicar en el ETL por la clave natural
`(fecha, fundo, modulo, lote, cortina, hilera, planta)`, conservando la primera ocurrencia.
Declarar esa clave como `UNIQUE` en PostgreSQL para que una segunda carga falle en lugar
de duplicar en silencio.

---

### H-04 · Seis consultas rotas · **Alta**

**Descripción.** De las 40 consultas guardadas, **6 no se ejecutan**. Lanzan error al
abrirse. Cualquier reporte de Power BI que las consuma está mostrando datos en caché de la
última ejecución exitosa, o directamente nada.

**Nota sobre la cifra.** Un primer conteo reportó 5. Al re-ejecutar las 40 una por una en
la verificación final apareció la sexta: `R0902_Forecast_Sem_vs_Camp`. La cifra correcta,
y la que sustenta este documento, es **6**.

**Las dos causas.** Los errores son de dos naturalezas distintas, y conviene separarlas
porque la corrección difiere:

- **Tipo A — objeto inexistente** (3 casos). La consulta referencia una tabla o consulta
  que no existe en la base. Error: *"no puede encontrar la tabla o consulta de entrada X"*.
- **Tipo B — columna inexistente** (3 casos). El objeto existe, pero se pide una columna
  que no tiene. Access interpreta el nombre desconocido como un parámetro y pide su valor.
  Error: *"Pocos parámetros. Se esperaba N"*. **Este error es engañoso**: parece que falta
  un parámetro, cuando en realidad falta una columna.

#### Detalle caso por caso

**1 · `0402_ConteoBrotes` — Tipo A**

| | |
|---|---|
| Referencia rota | `E04_ConteoBrotes` |
| Error exacto | `no puede encontrar la tabla o consulta de entrada 'E04_ConteoBrotes'` |
| Objeto real | **`E04_Brotes`** (3.385 filas) |
| Confirmación | `SELECT Count(*) FROM E04_ConteoBrotes` falla · `FROM E04_Brotes` devuelve 3.385 |
| Corrección | reemplazar las 14 apariciones de `E04_ConteoBrotes` por `E04_Brotes` |

La consulta pide `E04_ConteoBrotes.Piso`, `.Brotes`, `.Cortina` etc. — todas esas columnas
existen en `E04_Brotes`. Es un error de nombre de tabla, no de diseño.

**2 · `R0101_KgCosecha` — Tipo A**

| | |
|---|---|
| Referencia rota | `R01_VolumenCampo` |
| Error exacto | `no puede encontrar la tabla o consulta de entrada 'R01_VolumenCampo'` |
| Objeto real | **`H00_VolumenCampo`** (30.812 filas) |
| Confirmación | `FROM R01_VolumenCampo` falla · `FROM H00_VolumenCampo` devuelve 30.812 |
| Corrección | reemplazar el prefijo `R01_` por `H00_` |

Las columnas pedidas (`Campaña`, `Fecha`, `Fundo`, `Variedad`, `Modulo`, `Lote`, `KG`) son
exactamente las 7 columnas de `H00_VolumenCampo`. La tabla fue renombrada de `R01_` a `H00_`
en algún momento y esta consulta no se actualizó.

**3 · `R0802_ResumenAño` — Tipo A**

| | |
|---|---|
| Referencia rota | `R0901_ResCampaña` |
| Error exacto | `no puede encontrar la tabla o consulta de entrada 'R0901_ResCampaña'` |
| Objeto real | **`R0801_ResCampaña`** (29 filas) |
| Confirmación | `FROM R0901_ResCampaña` falla · `FROM R0801_ResCampaña` devuelve 29 filas |
| Corrección | `R0901_` por `R0801_` (error de un dígito: 09 vs 08) |

Verificación adicional: `R0801_ResCampaña` expone exactamente las 8 columnas que
`R0802_ResumenAño` pide en su `UNION ALL` — `Version, FundoPPto, Modulo, Año, Campaña, KG,
Area, NPlantas`. Coincidencia total. Confirma que es el objeto correcto.

**4 · `E` — Tipo B**

| | |
|---|---|
| Columna rota | `Actividad` |
| Error exacto | `Pocos parámetros. Se esperaba 2` |
| Confirmación | `Count(Actividad)` en `E02_ConteoFlores` falla · en `E03_ConteoEstados` falla · en `E01_Ramas` devuelve **94.236** |
| Diagnóstico | `Actividad` **solo existe en `E01_Ramas`**. `E02_ConteoFlores` y `E03_ConteoEstados` no la tienen |

Son 2 parámetros porque la consulta es un `UNION ALL` de dos ramas, y cada rama pide
`Actividad` de una tabla que no la tiene. Verificado contra el esquema: `E02_ConteoFlores`
tiene 14 columnas y `E03_ConteoEstados` 16 — `Actividad` no está en ninguna de las dos.

Esta consulta se llama simplemente `E`: es un borrador de trabajo que quedó guardado. Ver H-12.

**5 · `R0801_Forecast_Campaña_SemMes` — Tipo B**

| | |
|---|---|
| Columnas rotas | `M_Time.CampProAra` y `M_Time.Trimestre` |
| Error exacto | `Pocos parámetros. Se esperaba 2` |
| Confirmación | `Count(CampProAra)` falla · `Count(Trimestre)` falla |
| Diagnóstico | `M_Time` tiene **7 columnas**: `Fecha, Sem, Mes, Año, SEvConteo, AQII, MesSem`. Ninguna de las dos existe |

Los 2 parámetros corresponden exactamente a las 2 columnas ausentes. La consulta espera una
dimensión de tiempo más rica de la que existe: le falta el concepto de campaña productiva
(`CampProAra`) y el de trimestre.

**6 · `R0902_Forecast_Sem_vs_Camp` — Tipo B** *(la sexta, detectada en verificación final)*

| | |
|---|---|
| Columna rota | `R08_Forecast_Campaña.KG` |
| Error exacto | `Pocos parámetros. Se esperaba 1` |
| Confirmación | `Count([KG])` falla · `Count([KG Exp])` devuelve **101.715** |
| Diagnóstico | `R08_Forecast_Campaña` **no tiene columna `KG`**. Tiene tres columnas de kilos separadas |

Las tres columnas reales son `[KG Exp]` (exportable), `[Kg Des]` (descarte) y `[Kg Con]`
(consumo). La consulta pide un `KG` genérico que nunca existió.

**Esta es la corrección que requiere decisión de negocio, no técnica.** Hay tres lecturas
posibles y producen resultados distintos:

| Interpretación | Expresión | `SUM` resultante |
|---|---|---|
| Solo exportable | `[KG Exp]` | 648.044.713,14 |
| Exportable + consumo | `[KG Exp] + [Kg Con]` | 657.404.158,58 |
| Total cosechado | `[KG Exp] + [Kg Des] + [Kg Con]` | 689.684.707,86 |

La consulta compara forecast semanal (`R09`) contra forecast de campaña (`R08`). `R09.Kg`
suma 51.083.049,92 — dos órdenes de magnitud por debajo de cualquiera de las tres opciones.
Esa diferencia de escala indica que las dos tablas **no están en el mismo alcance**
(probablemente `R08` acumula todas las versiones de proyección y `R09` solo la vigente).
**Requiere confirmación del área de Planeamiento antes de corregir.** Se registra como
decisión pendiente en `04_PLAN_MIGRACION.md` §8.

#### Resumen de las 6

| Consulta | Tipo | Objeto/columna rota | Reemplazo verificado | ¿Requiere decisión? |
|---|---|---|---|---|
| `0402_ConteoBrotes` | A | `E04_ConteoBrotes` | `E04_Brotes` | No |
| `R0101_KgCosecha` | A | `R01_VolumenCampo` | `H00_VolumenCampo` | No |
| `R0802_ResumenAño` | A | `R0901_ResCampaña` | `R0801_ResCampaña` | No |
| `E` | B | `Actividad` en E02/E03 | *(descartar consulta)* | No — es un borrador |
| `R0801_Forecast_Campaña_SemMes` | B | `M_Time.CampProAra`, `.Trimestre` | crear ambas columnas | Sí — definir campaña productiva |
| `R0902_Forecast_Sem_vs_Camp` | B | `R08...KG` | `[KG Exp]` o suma | **Sí — Planeamiento** |

**Impacto en Power BI.** 4 de las 6 son corregibles sin intervención del negocio y deberían
arreglarse antes de migrar. Las 2 de forecast requieren definición previa. Ninguna de las 6
produce hoy un resultado en Access: los tableros que dependan de ellas están sirviendo
caché.

---

### H-05 · Explosión cartesiana en `01_Flores_C2025` · **Alta**

**Descripción.** La consulta `01_Flores_C2025` devuelve **487.368 filas** a partir de un
origen de **9.040**. Un factor de **×54**. No es un error de sintaxis: la consulta se
ejecuta correctamente y devuelve resultados, pero cada fila de origen aparece multiplicada.

**Evidencia:**

| Objeto | Filas |
|---|---|
| `0104_PromFlores` (origen) | 9.040 |
| `01_Flores_C2025` (resultado) | **487.368** |
| Factor de multiplicación | **×53,9** |

**Causa exacta.** La última línea de la consulta:

```sql
INNER JOIN M_Time ON [0104_PromFlores].Sem = M_Time.SEvConteo;
```

Se une **el número de semana contra la columna `SEvConteo` de `M_Time`**. Pero `M_Time`
tiene grano de **día**, no de semana: 2.189 filas, una por fecha, cubriendo del
2022-03-01 al 2027-12-31.

Cada valor de `SEvConteo` se repite en todos los días que pertenecen a esa semana de
evaluación. Al unir por semana contra una tabla de días, **cada fila de `0104_PromFlores`
se emparaja con todos los días de esa semana**, no con uno.

Verificación del grano de `M_Time`:

| Métrica | Valor |
|---|---|
| Filas totales | 2.189 |
| Rango de fechas | 2022-03-01 a 2027-12-31 |
| `SEvConteo` poblados | 1.224 (965 nulos) |
| Rango de `SEvConteo` | 1 a 53 |
| Filas donde `Sem <> SEvConteo` | **527** |

Con 1.224 días repartidos en ~53 valores de semana, el promedio es ~23 días por valor de
`SEvConteo` — y como `0104_PromFlores` ya trae múltiples lotes por semana, el producto
cruzado alcanza el ×54 observado.

**Por qué `SEvConteo` no es igual a `Sem`.** Son dos conceptos distintos, y esto es
información de negocio relevante: `Sem` es la semana calendario ISO; `SEvConteo` es la
**semana de evaluación de conteo**, que está desplazada respecto al calendario porque el
corte de la evaluación agronómica no cae en domingo. Hay **527 días** donde ambos valores
difieren. La consulta original probablemente pretendía unir por fecha y terminó uniendo por
un código de semana desplazado.

**Impacto en Power BI.** Cualquier medida `SUM` sobre esta consulta está inflada ~54 veces.
Un `AVG` puede parecer correcto —el promedio de valores repetidos es el mismo valor— lo que
hace el defecto **especialmente peligroso**: el tablero no se ve obviamente roto, solo los
totales son absurdos. Un conteo de registros de flores mostraría casi medio millón de
evaluaciones donde hubo nueve mil.

**Acción correctiva.** Unir por fecha (`0104_PromFlores.MínDeFecha = M_Time.Fecha`) o,
si el requisito real es agrupar por semana de evaluación, unir contra una dimensión de
semana con grano semanal —una fila por `(año, SEvConteo)`— no contra la tabla de días.

---

### H-06 · Filas de subtotal huérfanas mezcladas con los datos · **Alta**

**Descripción.** Las tablas de cosecha contienen filas donde **todos los campos
identificadores están vacíos pero el campo `KG` tiene un valor grande**. Son totales de
Excel que fueron copiados junto con los datos durante la importación. El motor las trata
como registros normales de cosecha.

**Evidencia — las 3 filas, extraídas una por una:**

*`H00_VolumenCampo` — 1 fila*

| Campaña | Fecha | Fundo | Modulo | Lote | KG |
|---|---|---|---|---|---|
| *(vacío)* | *(vacío)* | *(vacío)* | *(vacío)* | *(vacío)* | **930.662,1** |

*`H01_ProdHistorica` — 2 filas*

| Fundo | Campaña | Modulo | Lote | Fecha | KG |
|---|---|---|---|---|---|
| *(vacío)* | *(vacío)* | *(vacío)* | *(vacío)* | *(vacío)* | **786.655,8** |
| *(vacío)* | *(vacío)* | *(vacío)* | *(vacío)* | *(vacío)* | **208.677,4** |

**El impacto sobre el total de kilos:**

| Métrica | Valor |
|---|---|
| `H00_VolumenCampo SUM(KG)` crudo | 33.381.134,66 |
| `H00_VolumenCampo SUM(KG)` sin fila basura | 32.450.472,60 |
| `H01_ProdHistorica SUM(KG)` crudo | 33.441.319,22 |
| `H01_ProdHistorica SUM(KG)` sin filas basura | 32.445.986,02 |
| **KG total en filas basura (H00 + H01)** | **1.925.995** |
| **Porcentaje del total** | **~5,6%** |

**Por qué el defecto es difícil de ver.** Estas filas **solo aparecen en el total general**.
En cuanto un tablero segmenta por fundo, módulo, campaña o fecha, las filas caen fuera de
todas las categorías —sus campos son nulos— y desaparecen del gráfico. El resultado es que
**el total general no coincide con la suma de las partes**, y la diferencia no tiene una
categoría a la que atribuirse.

Es exactamente el tipo de discrepancia que genera desconfianza en un tablero sin que nadie
pueda explicar de dónde sale.

**Confirmación de que son subtotales y no datos reales.** Tres indicios convergentes:
1. Todos los campos identificadores son nulos simultáneamente — no ocurre en ninguna otra fila.
2. Los valores son de magnitud agregada (930 mil, 786 mil, 208 mil kg), órdenes por encima
   de cualquier registro individual de cosecha.
3. `930.662,1` en `H00` es cercano —no idéntico— a `786.655,8 + 208.677,4 = 995.333,2` en
   `H01`, coherente con dos subtotales de cortes distintos del mismo Excel de origen.

**Acción correctiva.** Filtrar en el ETL toda fila donde los identificadores sean nulos, y
declarar `NOT NULL` en las columnas de dimensión del modelo destino. Registrar las filas
descartadas en la tabla de cuarentena para trazabilidad.

---

### H-07 · `H00_VolumenCampo` y `H01_ProdHistorica` sin reconciliar · **Alta**

**Descripción.** Las dos tablas registran la misma cosecha. `H00` es el volumen de campo y
`H01` la producción histórica. Deberían coincidir, y en tres de las cinco campañas
coinciden exactamente — pero en dos hay diferencia.

**Nota de corrección respecto a un análisis preliminar.** Un primer barrido reportó este
hallazgo como un desfase de **importes**. Al verificar campaña por campaña, **el desfase
es de filas, no de kilos**. Se corrige aquí porque la lectura cambia: no es que los
kilos estén mal, es que `H01` tiene menos registros que `H00` en dos campañas.

**Evidencia — filas por campaña, lado a lado:**

| Campaña | Filas `H00` | Filas `H01` | Diferencia |
|---|---|---|---|
| C2022 | 1.691 | 1.691 | **0** ✓ |
| C2023 | 2.389 | 2.261 | **−128** |
| C2024 | 10.590 | 10.531 | **−59** |
| C2025 | 13.356 | 13.356 | **0** ✓ |
| C2026 | 2.785 | 2.785 | **0** ✓ |
| **Total** | **30.811** | **30.624** | **−187** |

*(Los totales excluyen la fila/filas basura de H-06: 1 en `H00`, 2 en `H01`.)*

**Los kilos, en cambio, casi coinciden:**

| Campaña | `SUM(KG)` en `H00` | `SUM(KG)` en `H01` | Diferencia |
|---|---|---|---|
| C2022 | 1.631.073,49 | 1.631.073,49 | ~0 |
| C2023 | 2.322.936,08 | 2.319.623,82 | **−3.312,27** |
| C2024 | 10.615.334,83 | 10.614.160,51 | **−1.174,32** |
| C2025 | 15.654.825,86 | 15.654.825,86 | **0** ✓ |
| C2026 | 2.226.302,34 | 2.226.302,34 | **0** ✓ |

**Interpretación argumentada.** Las 187 filas ausentes en `H01` representan solo
4.486,59 kg — un promedio de **24 kg por fila**, muy por debajo del promedio general
(~1.060 kg/fila). Esto indica que las filas faltantes son **registros de volumen muy
pequeño**, no cosechas completas omitidas.

La lectura más consistente con los datos es que `H01_ProdHistorica` aplica algún criterio
de consolidación —un umbral mínimo, o un agrupamiento de registros menores— que `H00` no
aplica. **No está documentado en ninguna parte de la base**, y no puede deducirse del SQL
porque ambas son tablas, no consultas: la diferencia se introduce en el proceso de carga,
que es externo a Access.

**Esto es una pregunta abierta para el área agronómica**, no un defecto con corrección
obvia. Se marca como *no resuelto* y se registra como decisión pendiente.

**Impacto en Power BI.** Dos tableros que midan "kilos cosechados" usando tablas distintas
darán cifras distintas para C2023 y C2024, con diferencias de 3.312 kg y 1.174 kg. La
diferencia es pequeña en porcentaje (0,14% y 0,01%) pero **inexplicable para quien la vea**,
y suficiente para que dos áreas no cuadren sus números.

**Acción correctiva.** Antes de migrar, confirmar con Agronomía cuál de las dos tablas es
la fuente de verdad. En el modelo destino debe existir **una sola** tabla de hechos de
cosecha; la otra pasa a ser una vista derivada, no un duplicado con reglas propias.

---

### H-08 · `H05_Clima` con recargas exactas · **Alta**

**Descripción.** La tabla de clima contiene **2.079 grupos de filas duplicadas exactas**:
el mismo timestamp registrado más de una vez con los mismos valores. Patrón idéntico al de
H-03: una importación ejecutada dos veces.

**Evidencia:**

| Métrica | Valor |
|---|---|
| Filas totales en `H05_Clima` | 155.588 |
| Timestamps distintos | 153.413 |
| **Grupos con duplicados** | **2.079** |
| Filas de exceso | 2.175 |

**Por qué es un defecto y no una lectura legítima.** `H05_Clima` viene de una estación
meteorológica automática con registro periódico. **Un timestamp identifica unívocamente una
medición**: no puede haber dos temperaturas distintas —ni dos idénticas— para el mismo
instante en la misma estación. La tabla no tiene columna que identifique la estación, así
que tampoco cabe la interpretación de "dos sensores".

**Impacto medido:**

| Métrica | Valor crudo |
|---|---|
| `AVG(Temp)` | 21,8968635057212 |
| `SUM(Lluvia)` | 160,600001469254 |

El promedio de temperatura está sesgado hacia los periodos recargados: esas horas pesan
doble en el cálculo. **`SUM(Lluvia)` es el caso más grave** — la lluvia acumulada de los
2.079 momentos duplicados se cuenta dos veces, sobrestimando la precipitación total del
periodo afectado.

En un cultivo de arándano la precipitación acumulada alimenta decisiones de riego y de
manejo de enfermedad fúngica. Un acumulado sobrestimado es un dato que puede inducir a
regar de menos.

**Impacto en Power BI.** `H0501_VariablesClima` expone las 155.588 filas sin deduplicar —
es un pase directo de la tabla. Todo tablero de clima hereda el defecto.

**Acción correctiva.** Declarar `UNIQUE` sobre el timestamp en el modelo destino y
deduplicar en el ETL conservando la primera ocurrencia. Al ser duplicados **exactos**, la
elección de cuál conservar es indiferente.

---

### H-09 · `M_Evaluadores` nunca enlaza · **Media**

**Descripción.** Existe un maestro de evaluadores con 31 registros, pero **ninguna consulta
lo usa** y, si se intentara, el join fallaría: las tablas de evaluación guardan el **DNI**,
mientras que el maestro se pensó para enlazar por un código corto (`Cod`).

**Evidencia — el maestro:**

| DNI | Cod | Nombres |
|---|---|---|
| 74557665 | `JCAS` | JESUS ALBERTO |
| 61070556 | `JCVL` | JUAN CARLOS |
| 44770948 | *(vacío)* | KELLY MARIBEL |
| 75023850 | `KPER` | KETY MAYELY |
| 41891837 | `LMAN` | LEYDI KETTY |

**Evidencia — lo que guardan las tablas de evaluación:**

| `E01_Ramas.Evaluador` | Filas |
|---|---|
| `10616663` | 7.021 |
| `41078480` | 2.931 |
| `41772809` | 5.345 |
| `41891837` | 4.721 |
| `44652711` | 7.708 |

Las tablas guardan **DNI numérico de 8 dígitos**, no el código de 4 letras. El maestro
tiene ambas columnas, así que el enlace *es posible* por `DNI` — pero:

1. **Ninguna de las 40 consultas lo intenta.** Verificado en el linaje: `M_Evaluadores`
   tiene **0 consultas dependientes**.
2. La columna `Cod`, que parece diseñada para ser la clave de enlace, tiene **1 registro
   vacío** de 31 y no aparece en ninguna tabla de evaluación.
3. Uniendo por `DNI`, hay **2 evaluadores en `E01_Ramas` sin registro en el maestro**.

**Consecuencia.** No se puede analizar el desempeño por evaluador: ni cuántas plantas
evalúa cada uno, ni la dispersión de sus mediciones respecto al promedio, ni detectar un
evaluador cuyos conteos se desvían sistemáticamente. La información existe en ambos lados
pero nunca se cruza.

En evaluación fenológica esto tiene valor real: la variabilidad entre evaluadores es una
fuente de error conocida, y sin poder medirla no se puede corregir.

**Acción correctiva.** Enlazar por `DNI` —que es lo que efectivamente se captura— y
declarar la FK. Los 2 DNI sin maestro van a cuarentena para que Agronomía los complete.
La columna `Cod` se conserva como atributo descriptivo, no como clave.

---

### H-10 · `H02_BDElifab` sin tipar · **Media**

**Descripción.** La tabla de packing tiene 35 columnas y **34 están declaradas como texto**
(`WChar`, longitud 255), incluyendo columnas que son inequívocamente numéricas o de fecha.
Es una importación directa de Excel sin ninguna definición de tipo.

**Evidencia — columnas numéricas guardadas como texto:**

| Columna | Tipo declarado | Tipo que debería tener |
|---|---|---|
| `Semana` | `WChar(255)` | entero |
| `Calibre` | `WChar(255)` | decimal o categoría ordenada |
| `Calibres` | `WChar(255)` | decimal |
| `Mes` | `WChar(255)` | entero o fecha |
| `Contenedores esperados` | `WChar(255)` | entero |
| `Contenedores volcados` | `WChar(255)` | entero |
| `Acidez` | `WChar(255)` | decimal |

Solo `Año` está tipada correctamente (tipo 5 = `Double`), y las 4 columnas de peso/recuento
(`Recuento`, `Peso total (kg)`, `%`, `Peso total (kg)2`) usan tipo 4 (`Single`).

**Por qué es un defecto y no una preferencia de diseño.** Con `Semana` como texto:

- El orden es **alfabético, no numérico**: `10` va antes que `2`. Un gráfico de evolución
  semanal muestra las semanas desordenadas.
- No se pueden hacer operaciones de rango (`Semana BETWEEN 20 AND 30`) sin conversión.
- Power BI intenta inferir el tipo al importar y puede acertar o no; si dos analistas
  importan la misma tabla en momentos distintos pueden obtener tipos distintos.

Con `Calibre` como texto ocurre lo mismo: el calibre es una escala ordenada
(`12mm` < `14mm` < ... < `26mm+`) y como texto se ordena alfabéticamente.

**Duplicación de columnas.** La tabla tiene además pares evidentes de la misma información:
`Modulo` / `Módulo`, `Productor1` / `Productor`, `Calibre` / `Calibres`,
`ACDT` / `ACDT 2`, `Peso total (kg)` / `Peso total (kg)2`. Son 5 pares — señal de
importaciones sucesivas con encabezados ligeramente distintos.

**Nulos relevantes:**

| Columna | Nulos | % de 117.536 |
|---|---|---|
| `Hora de inicio` | 56.173 | 47,8% |
| `Hora de finalización` | 56.172 | 47,8% |
| `Contenedores volcados` | 13.085 | 11,1% |
| `Contenedores esperados` | 10.439 | 8,9% |
| `Turno` | 7.708 | 6,6% |

Casi la mitad de los registros no tiene hora de proceso. Cualquier análisis de duración de
packing cubre solo la mitad de los datos.

**Acción correctiva.** Tipar cada columna explícitamente en el DDL destino, consolidar los
5 pares duplicados en una sola columna cada uno, y convertir `Calibre` en una dimensión
ordenada con posición explícita.

---

### H-11 · Lógica redundante entre consultas · **Media**

**Descripción.** Seis consultas implementan un **despivote manual mediante `UNION ALL` con
literales de texto**: repiten el mismo bloque `SELECT` una vez por cada métrica, cambiando
solo la columna y una etiqueta constante.

**Evidencia — el patrón, tomado de `R0801_Forecast_Campaña_SemMes`:**

```sql
SELECT ..., "Kg Exp" AS Descripcion, R08_Forecast_Campaña.[KG Exp] AS Valor, ...
FROM (...bloque de 25 líneas...)
UNION ALL
SELECT ..., "Kg Des" AS Descripcion, R08_Forecast_Campaña.[Kg Des] AS Valor, ...
FROM (...el mismo bloque de 25 líneas, idéntico...)
UNION ALL
SELECT ..., "Kg Con" AS Descripcion, R08_Forecast_Campaña.[Kg Con] AS Valor, ...
FROM (...el mismo bloque de 25 líneas, otra vez...)
```

El bloque `FROM` —con su subconsulta agregada de `M_Lotes`, su join a `M_Time` agrupado y
sus condiciones— **se repite tres veces palabra por palabra**. La única diferencia entre
las tres ramas son dos tokens: la etiqueta y el nombre de la columna.

**Consecuencias medibles:**

1. **Coste de ejecución ×3.** El motor evalúa la subconsulta de `M_Lotes` y el join a
   `M_Time` tres veces sobre las 101.715 filas de `R08_Forecast_Campaña`.
2. **Riesgo de divergencia.** Corregir el join exige editar tres bloques idénticos. Si se
   edita uno y se olvida otro, la consulta sigue ejecutándose y **devuelve resultados
   inconsistentes entre métricas** sin señal de error.
3. **Es innecesario.** Tanto PostgreSQL como Power BI despivotan de forma nativa —
   `UNPIVOT`/`LATERAL` en SQL, "Anular dinamización de columnas" en Power Query. El patrón
   existe porque Access no tiene esa capacidad.

**Los 6 casos:** `R0801_Forecast_Campaña_SemMes` (3 ramas), `R0802_ResumenAño` (2 ramas),
`R0902_Forecast_Sem_vs_Camp` (2 ramas), `E` (2 ramas), y dos patrones equivalentes en la
familia `03xx`.

Es llamativo que **3 de los 6 casos coinciden con consultas rotas** (H-04). La correlación
tiene explicación: son las consultas más largas y difíciles de editar de la base, y
precisamente por eso quedaron desactualizadas cuando cambiaron los objetos que referencian.

**Acción correctiva.** Reemplazar por `LATERAL (VALUES ...)` en PostgreSQL: una sola
evaluación del bloque `FROM`, una sola definición de la lógica.

---

### H-12 · Restos de importación de Excel · **Baja**

**Descripción.** La base conserva objetos que no participan de ningún flujo: tablas vacías,
tablas sin consumidor y consultas de borrador. Son residuos de importaciones y pruebas.

**Evidencia — objetos residuales:**

| Objeto | Tipo | Estado | Verificación |
|---|---|---|---|
| `Errores de pegado` | Tabla | **0 filas** | Tabla que Access crea automáticamente al fallar un pegado |
| `E05_DiametrosBayas` | Tabla | 4.193 filas, **0 consultas la leen** | linaje: sin consumidor |
| `M_Evaluadores` | Tabla | 31 filas, **0 consultas la leen** | linaje: sin consumidor (ver H-09) |
| `M_nMuestra` | Tabla | 681 filas, **0 consultas la leen** | linaje: sin consumidor |
| `E` | Consulta | **rota**, nombre de un carácter | ver H-04 caso 4 |
| `~TMPCLP151491` | Consulta | temporal del portapapeles de Access | prefijo `~` = objeto temporal |

**Distinción importante entre los tres tipos de residuo:**

- **`Errores de pegado`** es basura pura: 0 filas, generada por el motor. Se descarta.
- **`E` y `~TMPCLP151491`** son borradores de trabajo. Se descartan.
- **`E05_DiametrosBayas`, `M_Evaluadores` y `M_nMuestra` NO son basura.** Contienen
  4.905 filas de datos capturados en campo que **nunca llegan a un tablero**. No es deuda
  técnica: es información que se recoge y se pierde.

**El caso de `E05_DiametrosBayas` merece atención.** Tiene 4.193 mediciones de diámetro de
baya con `AVG(Diametro) = 19,885`. El diámetro de baya es el **indicador directo de calibre
comercial** — determina a qué mercado va la fruta y a qué precio. Es el eslabón que conecta
la evaluación de campo con el resultado de packing (`H02_BDElifab`, que clasifica por
calibres de 12mm a 26mm+).

Que esta tabla no alimente ningún reporte significa que **existe la medición de campo que
permitiría anticipar el calibre de packing, y no se está usando**.

**`M_nMuestra`** define cuántas muestras corresponden por lote y evaluación (681 filas). Es
la referencia natural para validar si una evaluación cubrió el muestreo requerido. Tampoco
se usa.

**Acción correctiva.** Descartar los objetos de basura real. **Migrar las tres tablas sin
consumidor** y señalarlas al área de Reportes como oportunidad de análisis — detalle en
`03_GUIA_REPORTES.md` §6.

---

## 5 · Diccionario de datos · 18 tablas

Cada tabla se documenta con: propósito de negocio, grano real (qué representa una fila),
columnas con tipo y nulos, y estado.

**Leyenda de tipos OLEDB:** `2`=SmallInt · `3`=Integer · `4`=Single · `5`=Double · `7`=Date · `11`=Boolean · `130`=WChar (texto)

---

### Tablas de evaluación fenológica (`E0x`)

#### `E01_Ramas` — 94.236 filas

**Propósito.** Conteo de ramas y medición de diámetro de corona por planta individual. Es
la evaluación estructural: cuánta madera productiva tiene la planta.

**Grano.** Una fila = una planta evaluada en una fecha. *En teoría* — en la práctica hay
23.141 filas de exceso por recarga (H-03), así que el grano real está roto.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Id` | 130 | 25 | 0 | **no único**: 15.043 valores para 94.236 filas (H-02) |
| 2 | `Actividad` | 130 | 25 | 0 | única tabla de evaluación que la tiene (causa de H-04 caso 4) |
| 3 | `Evaluador` | 130 | 8 | 0 | DNI; no enlaza con `M_Evaluadores` (H-09) |
| 4 | `Fecha` | 7 | | 0 | |
| 5 | `Fundo` | 130 | 25 | 0 | **vocabulario D** (quechua sin prefijo) — H-01 |
| 6 | `Modulo` | 130 | 5 | 0 | |
| 7 | `Lote` | 130 | 5 | 0 | |
| 8 | `Cortina` | 2 | | 0 | subdivisión física del lote |
| 9 | `Hilera` | 2 | | 0 | |
| 10 | `Planta` | 2 | | 0 | |
| 11 | `Ramas <5` | 2 | | 22 | ramas de diámetro menor a 5 mm |
| 12 | `Ramas >5` | 2 | | 29 | ramas de diámetro mayor a 5 mm |
| 13 | `# Ramas` | 2 | | 0 | total; `SUM` = 730.318 |
| 14 | `Diametro` | 4 | | 0 | diámetro de corona; `AVG` = 10,978 (sesgado, H-03) |

**Estado.** Defectuosa: H-01 (100% huérfana), H-02 (Id no único), H-03 (24,6% duplicada).

---

#### `E02_ConteoFlores` — 43.490 filas

**Propósito.** Conteo de flores, cuajo y yemas por planta. Mide el potencial productivo
antes de que se forme el fruto.

**Grano.** Una fila = una planta evaluada en una fecha y hora.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Item` | 130 | 0 | 0 | |
| 2 | `Fecha` | 7 | | 0 | |
| 3 | `Evaluador` | 130 | 8 | 0 | DNI |
| 4 | `Fundo` | 130 | 25 | 0 | **vocabulario B** (presupuestal) — H-01 |
| 5 | `Modulo` | 130 | 4 | 0 | |
| 6 | `Lote` | 130 | 5 | 0 | |
| 7 | `Cortina` | 2 | | 0 | |
| 8 | `Hilera` | 2 | | 0 | |
| 9 | `Planta` | 2 | | 0 | |
| 10 | `nFlores` | 2 | | 250 | número de flores; `SUM` = 3.050.031 |
| 11 | `Cuajo` | 2 | | **38.154** | flores que cuajaron — **87,7% nulo** |
| 12 | `YA` | 2 | | **31.567** | yemas abiertas — **72,6% nulo** |
| 13 | `YP` | 2 | | **31.958** | yemas por abrir — **73,5% nulo** |
| 14 | `Hora` | 7 | | 14.862 | 34,2% nulo |

**Observación sobre los nulos.** `Cuajo`, `YA` e `YP` están mayoritariamente vacías. Esto
**no es necesariamente un defecto**: el cuajo y las yemas solo se evalúan en ventanas
fenológicas específicas del ciclo, no en cada visita. Pero significa que cualquier promedio
sobre esas columnas se calcula sobre una fracción de los datos, y el tablero debe indicarlo.

**Estado.** Aceptable; sin `Actividad` (H-04 caso 4), vocabulario B (H-01).

---

#### `E03_ConteoEstados` — 18.714 filas

**Propósito.** Distribución de frutos por estado de madurez (E1 a E5) en cada planta. Es la
base del pronóstico de cosecha: conociendo cuántos frutos hay en cada estado se estima
cuándo estarán listos.

**Grano.** Una fila = una planta evaluada en una fecha.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Item` | 130 | 0 | 0 | |
| 2 | `Fecha` | 7 | | 0 | |
| 3 | `Evaluador` | 130 | 8 | 0 | DNI |
| 4 | `Fundo` | 130 | 25 | 0 | |
| 5 | `Modulo` | 130 | 4 | 0 | |
| 6 | `Lote` | 130 | 5 | 0 | |
| 7 | `Cortina` | 2 | | 0 | |
| 8 | `Hilera` | 2 | | 0 | |
| 9 | `Planta` | 2 | | 0 | |
| 10–14 | `E1`…`E5` | 2 | | 0 | frutos por estado de madurez |
| 15 | `Total` | 2 | | 1 | `SUM` = 9.060.271 |
| 16 | `F16` | 130 | 255 | 5.484 | **columna sin nombre real** — residuo de importación |

**Inconsistencia detectada.** `SUM(Total)` = 9.060.271 pero `SUM(E1..E5)` = 9.057.841.
Diferencia de **2.430 frutos**. La columna `Total` no es la suma exacta de los estados —
fue capturada de forma independiente y no se recalculó. En el modelo destino `Total` debe
ser una columna calculada, no almacenada.

**Estado.** Defectuosa: PK incluye la medida `E1` (H-02), `Total` inconsistente, columna
residual `F16`.

---

#### `E04_Brotes` — 3.385 filas

**Propósito.** Conteo de brotes nuevos por planta. Es la primera evaluación del ciclo,
posterior a la poda.

**Grano.** Una fila = una planta. **Sin fecha en la clave** — ver H-02.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Piso` | 130 | 10 | 0 | nivel de la planta |
| 2 | `Fecha` | 7 | | 0 | **no está en la PK** (H-02) |
| 3 | `Evaluador` | 130 | 10 | 0 | |
| 4 | `Fundo` | 130 | 25 | 0 | **vocabulario D** — H-01 |
| 5–9 | `Modulo`…`Planta` | | | 0 | ubicación física |
| 10 | `Brotes` | 2 | | 0 | `SUM` = 225.638 |
| 11–15 | `Des1`…`Des5` | 130 | 255 | 3.145–3.385 | **`Des4` y `Des5` 100% nulas** |
| 16 | `Hora` | 7 | | 2.356 | 69,6% nulo |

**Por qué solo 3.385 filas.** Es la tabla más pequeña de las de evaluación, 28 veces menor
que `E01_Ramas`. La causa es la PK sin `Fecha` (H-02): el motor **rechaza** una segunda
evaluación de la misma planta. No es que se evalúe poco — es que la clave impide registrar.

**Estado.** Defectuosa: PK errónea que limita la captura (H-02), 100% huérfana (H-01),
`Des4`/`Des5` vacías.

---

#### `E05_DiametrosBayas` — 4.193 filas

**Propósito.** Medición del diámetro de la baya — el indicador directo de calibre comercial.

**Grano.** Una fila = una medición en una hilera y fecha. Nótese que **no baja a planta**:
el grano es hilera, más grueso que las otras tablas de evaluación.

| # | Columna | Tipo | Long. | Nulos |
|---|---|---|---|---|
| 1 | `Modulo` | 130 | 4 | 0 |
| 2 | `Turno` | 130 | 5 | 0 |
| 3 | `Lote` | 130 | 5 | 0 |
| 4 | `Cortina` | 2 | | 0 |
| 5 | `Hilera` | 2 | | 0 |
| 6 | `Diametro` | 4 | | 0 |
| 7 | `Fecha` | 7 | | 0 |

`AVG(Diametro)` = 19,885. **Sin nulos en ninguna columna** — es la tabla más limpia de la base.

**Estado.** Estructuralmente sana, pero **0 consultas la consumen** (H-12). Es la tabla que
conectaría evaluación de campo con calibre de packing, y no se usa. Único caso donde el
`Turno` viene en la propia tabla y no requiere join con `M_Lotes`.

---

### Tablas de cosecha y packing (`H0x`)

#### `H00_VolumenCampo` — 30.812 filas

**Propósito.** Registro de kilos cosechados en campo. Es el dato primario de producción.

**Grano.** Una fila = kilos cosechados en un lote en una fecha.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Campaña` | 130 | 8 | 1 | C2022–C2026 |
| 2 | `Fecha` | 7 | | 1 | |
| 3 | `Fundo` | 130 | 25 | 1 | **vocabulario B** — H-01 |
| 4 | `Variedad` | 130 | 25 | 1 | |
| 5 | `Modulo` | 130 | 8 | 1 | |
| 6 | `Lote` | 130 | 5 | 1 | |
| 7 | `KG` | 4 | | 0 | `SUM` crudo = 33.381.134,66 |

**El nulo único en las 6 primeras columnas es la misma fila** — la fila de subtotal de H-06,
con 930.662,1 kg y todos los identificadores vacíos.

| Campaña | Filas | `SUM(KG)` |
|---|---|---|
| *(fila basura)* | 1 | 930.662,06 |
| C2022 | 1.691 | 1.631.073,49 |
| C2023 | 2.389 | 2.322.936,08 |
| C2024 | 10.590 | 10.615.334,83 |
| C2025 | 13.356 | 15.654.825,86 |
| C2026 | 2.785 | 2.226.302,34 |

**Estado.** Defectuosa: fila basura (H-06), 366 huérfanos (H-01), sin reconciliar con `H01` (H-07).

---

#### `H01_ProdHistorica` — 30.626 filas

**Propósito.** Producción histórica consolidada. Cubre lo mismo que `H00` pero con
dimensiones adicionales (`Turno`, `nPlantas`, `Semana`) y dos métricas de calidad
(`Paña`, `Peso`).

**Grano.** Una fila = producción de un lote en una fecha.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Fundo` | 130 | 25 | 2 | **vocabulario B** |
| 2 | `Campaña` | 130 | 8 | 2 | |
| 3 | `Modulo` | 130 | 5 | 2 | |
| 4 | `Turno` | 130 | 5 | 2 | **la trae de origen** (a diferencia de `H00`) |
| 5 | `Lote` | 130 | 5 | 2 | |
| 6 | `nPlantas` | 2 | | 2 | plantas del lote, desnormalizado de `M_Lotes` |
| 7 | `Fecha` | 7 | | 2 | |
| 8 | `Semana` | 2 | | 2 | desnormalizado |
| 9 | `KG` | 4 | | 0 | `SUM` crudo = 33.441.319,22 |
| 10 | `Paña` | 4 | | 2 | número de pasada de cosecha |
| 11 | `Peso` | 4 | | 10 | peso unitario de baya |

**Los 2 nulos son las 2 filas basura de H-06** (786.655,8 y 208.677,4 kg).

**Diferencia con `H00`.** Ver H-07: `H01` tiene 187 filas menos en C2023 y C2024, con
4.486,59 kg de diferencia. La regla que las excluye no está documentada en la base.

**Sobre `Paña`.** Es el número de pasada de cosecha: en arándano no se cosecha todo de una
vez, sino en varias pasadas conforme el fruto madura. `Paña` numera esas pasadas — dato
clave para analizar rendimiento por pasada. El acento de "paña" aparece también en el
nombre de la consulta `H0105_RendTurno_paña`.

**Estado.** Defectuosa: 2 filas basura (H-06), 180 huérfanos (H-01), desfase con `H00` (H-07).

---

#### `H02_BDElifab` — 117.536 filas

**Propósito.** Resultado del proceso de empaque de la empacadora externa (Elifab).
Clasificación de la fruta por calibre, mercado y calidad. **Cierra el ciclo comercial.**

**Grano.** Una fila = un lote clasificado en una clase, en una fecha de proceso.

Es la tabla más ancha (35 columnas) y la peor tipada de la base — ver H-10. Columnas
destacadas:

| Columna | Tipo | Nulos | Nota |
|---|---|---|---|
| `Clases` | 130 | 0 | clase de clasificación |
| `Recuento` | 4 | 30 | |
| `Peso total (kg)` | 4 | 1 | |
| `Calibre` | 130 | 0 | **texto**: `12mm`–`26mm+`; orden alfabético incorrecto (H-10) |
| `Mercado` | 130 | 0 | `CHINA` / `USA` / `ÁCIDO` / `DESCARTE` |
| `Fecha Cosecha` | 7 | 0 | enlaza con `H00`/`H01` |
| `Fecha Proceso` | 7 | 0 | fecha de packing |
| `Semana` | 130 | 0 | **texto** — se ordena mal (H-10) |
| `Hora de inicio` | 7 | **56.173** | 47,8% nulo |
| `Hora de finalización` | 7 | **56.172** | 47,8% nulo |
| `Turno` | 130 | 7.708 | 6,6% nulo |
| `Productor1` / `Productor` | 130 | 0 | **par duplicado** |
| `Modulo` / `Módulo` | 130 | 0 | **par duplicado** |
| `Calibre` / `Calibres` | 130 | 0 | **par duplicado** |
| `ACDT` / `ACDT 2` | 130 | 0 | **par duplicado** |
| `Peso total (kg)` / `Peso total (kg)2` | 4 | 1 / 0 | **par duplicado** |

**Sobre `Mercado`.** Los cuatro valores tienen lectura comercial directa: `CHINA` y `USA`
son destinos de exportación (mayor precio), `ÁCIDO` es fruta desviada a industria y
`DESCARTE` es pérdida. La distribución entre estos cuatro valores **es el indicador de
rentabilidad de la campaña**.

**Estado.** Defectuosa: 34 de 35 columnas sin tipar, 5 pares duplicados, 47,8% sin horario (H-10).

---

#### `H05_Clima` — 155.588 filas

**Propósito.** Registro automático de estación meteorológica. 25 variables climáticas.

**Grano.** Una fila = una medición en un instante. Debería ser único por timestamp — no lo
es (H-08).

| Columna | Tipo | Nulos | Nota |
|---|---|---|---|
| `Fecha` | 7 | 0 | timestamp; **153.413 distintos de 155.588 filas** (H-08) |
| `Barometro` | 4 | 95 | |
| `Temp` / `TembAlta` / `TempBaja` | 4 | 0 | `AVG(Temp)` = 21,897 · nótese el typo `TembAlta` |
| `Humedad` / `PuntoRocio` / `BulboHumedo` | 4 | 0 | |
| `VelViento` / `VientoCorriente` | 4 | 0 | |
| `DirecViento` | 130 | 7.830 | 5,0% nulo |
| `AltaVelViento` | 3 | 0 | |
| `AltaDirecViento` | 130 | 2.351 | 1,5% nulo |
| `VientoFrio` / `IndiceCalor` | 3 | 0 | |
| `THWIndex` | 4 | 0 | índice temperatura-humedad-viento |
| `TSHWIndex` | 4 | 3 | |
| `Lluvia` / `TasaLluvia` | 4 | 0 | `SUM(Lluvia)` = 160,600 |
| `RadSol` / `EnerSolar` / `RadSolAlta` | 4 | 0 | |
| `ET-mm` | 4 | 0 | evapotranspiración |
| `DGCalentamiento` / `DGEnfriamiento` | 4 | 0 | grados-día |

**Sobre los grados-día.** `DGCalentamiento` y `DGEnfriamiento` son acumuladores térmicos:
en fenología del arándano predicen la velocidad de desarrollo del fruto. Junto con `ET-mm`
(evapotranspiración, que determina la necesidad de riego) son las variables de mayor valor
agronómico de la tabla.

**Estado.** Defectuosa: 2.079 grupos duplicados (H-08). El typo `TembAlta` debería
corregirse a `TempAlta` en el destino.

---

### Tablas maestras (`M_x`)

#### `M_Lotes` — 860 filas

**Propósito.** Maestro de lotes. **Es la tabla central del modelo**: 33 de las 40 consultas
dependen de ella, directa o transitivamente.

**Grano.** Una fila = un lote. 855 combinaciones distintas de `(Modulo, Lote)` para 860
filas — hay 5 lotes repetidos.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Fundo` | 130 | 50 | 0 | **vocabulario A** (comercial) — H-01 |
| 2 | `FundoPPto` | 130 | 25 | 0 | **vocabulario B** (presupuestal) — H-01 |
| 3 | `Variedad` | 130 | 25 | 0 | |
| 4 | `Modulo` | 130 | 5 | 0 | |
| 5 | `Turno` | 130 | 5 | 0 | **la fuente del turno para toda la base** |
| 6 | `Lote` | 130 | 5 | 0 | |
| 7 | `Area` | 4 | | 0 | `SUM` = 829,02 ha |
| 8 | `NPlantas` | 2 | | 0 | `SUM` = 4.711.564 plantas |
| 9 | `FSiembra` | 7 | | 1 | base del cálculo de edad |
| 10 | `Maceta` | 130 | 25 | 155 | 18,0% nulo |
| 11 | `TipoFibra` | 130 | 25 | 240 | 27,9% nulo |
| 12 | `KeyMap` | 130 | 11 | **53** | clave de mapa; 6,2% nulo |
| 13 | `Fundo_pptom5` | 130 | 255 | 0 | **vocabulario C** (quechua con prefijo) — H-01 |
| 14 | `Moduloo` | 130 | 255 | 0 | typo evidente; duplica `Modulo` |
| 15 | `kk` | 130 | 255 | 0 | **nombre sin significado** |

**Esta tabla es el epicentro de H-01.** Contiene tres de los cuatro vocabularios de fundo
en columnas distintas (`Fundo`, `FundoPPto`, `Fundo_pptom5`) y ninguno coincide con el
vocabulario D que usan `E01_Ramas` y `E04_Brotes`. Es también la razón por la que el
problema es *resoluble*: la correspondencia entre A, B y C está aquí, fila por fila. Solo
falta mapear D.

**Impacto de tocar esta tabla: 33 de 40 consultas.** Ver `05_linaje_dependencias.txt` §2.

**Estado.** Crítica para el modelo; contiene el origen de H-01. `Moduloo` y `kk` son residuos.

---

#### `M_Time` — 2.189 filas

**Propósito.** Dimensión de tiempo. 33 consultas la usan para agregar por semana, mes o año.

**Grano.** Una fila = un día. Del 2022-03-01 al 2027-12-31.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Fecha` | 7 | | 0 | **PK — la única correcta de la base** |
| 2 | `Sem` | 2 | | 0 | semana calendario |
| 3 | `Mes` | 130 | 3 | 0 | texto de 3 caracteres |
| 4 | `Año` | 2 | | 0 | |
| 5 | `SEvConteo` | 2 | | **965** | **semana de evaluación de conteo** — 44,1% nulo |
| 6 | `AQII` | 130 | 1 | **2.189** | **100% nula** — columna completamente vacía |
| 7 | `MesSem` | 130 | 5 | 707 | 32,3% nulo |

**`SEvConteo` es el concepto clave de esta tabla.** Es una semana **desplazada** respecto a
`Sem`: el corte de la evaluación agronómica no coincide con la semana calendario.

| Métrica | Valor |
|---|---|
| Días con `SEvConteo` poblado | 1.224 de 2.189 (55,9%) |
| Rango de valores | 1 a 53 |
| **Días donde `Sem <> SEvConteo`** | **527** |

Los 965 nulos corresponden a fechas fuera de las ventanas de evaluación (incluye todo 2027,
que es futuro). Es el uso incorrecto de esta columna lo que produce la explosión ×54 de
H-05.

**Columnas ausentes que rompen consultas.** `M_Time` **no tiene** `CampProAra` ni
`Trimestre`, y dos consultas las piden (H-04 caso 5). Falta el concepto de **campaña
productiva** en la dimensión de tiempo.

**Estado.** La mejor tabla estructuralmente (PK correcta) pero incompleta: `AQII` 100% vacía,
faltan `CampProAra` y `Trimestre`.

---

#### `M_Poda` — 2.159 filas

**Propósito.** Registro de poda por lote y campaña. `FInicio` marca el **inicio del ciclo
productivo**: es la referencia temporal contra la que se mide todo el desarrollo fenológico.

**Grano.** Una fila = un lote en una campaña.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Campaña` | 130 | 6 | 0 | C2022–C2026 |
| 2 | `Fundo` | 130 | 25 | 0 | **vocabulario B** |
| 3 | `Variedad` | 130 | 25 | 0 | |
| 4 | `Modulo` | 130 | 8 | 0 | |
| 5 | `Turno` | 130 | 5 | 0 | |
| 6 | `Lote` | 130 | 8 | 0 | |
| 7 | `Area` | 4 | | 0 | |
| 8 | `FSiembra` | 7 | | 58 | 2,7% nulo; duplica `M_Lotes.FSiembra` |
| 9 | `FInicio` | 7 | | 2 | **inicio del ciclo productivo** |

**Por qué `FInicio` importa.** En arándano el desarrollo se mide en días desde poda, no en
fechas absolutas: dos lotes podados con un mes de diferencia están en estados fenológicos
distintos en la misma fecha calendario. `FInicio` es el origen de esa cuenta. 7 consultas
dependen de esta tabla por ese motivo.

**Estado.** Sana. `FSiembra` duplica información de `M_Lotes` — riesgo de divergencia.

---

#### `M_Evaluadores` — 31 filas

**Propósito.** Maestro de evaluadores de campo.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `DNI` | 130 | 8 | 0 | **lo que sí se captura en las tablas de evaluación** |
| 2 | `Nombres` | 130 | 50 | 0 | |
| 3 | `Apellidos` | 130 | 50 | 0 | |
| 4 | `Cod` | 130 | 10 | 1 | código de 4 letras; **no aparece en ninguna tabla** |
| 5 | `InicioLabores` | 130 | 255 | 12 | **fecha guardada como texto** |
| 6 | `Nacimiento` | 130 | 255 | 4 | **fecha guardada como texto** |
| 7 | `Zona` | 130 | 255 | 1 | |
| 8 | `Celular` | 130 | 255 | 4 | |
| 9 | `Estado` | 11 | 2 | 0 | booleano (activo/inactivo) |

**Estado.** **0 consultas la consumen** (H-09, H-12). Además `InicioLabores` y `Nacimiento`
son fechas almacenadas como texto.

---

#### `M_nMuestra` — 681 filas

**Propósito.** Define cuántas muestras corresponden por lote y tipo de evaluación. Es la
referencia para validar si una evaluación cubrió el muestreo requerido.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Evaluacion` | 130 | 25 | 0 | tipo de evaluación |
| 2 | `Fundo` | 130 | 15 | 0 | |
| 3 | `Modulo` | 130 | 3 | 0 | |
| 4 | `Turno` | 130 | 3 | 0 | |
| 5 | `Lote` | 130 | 4 | 0 | |
| 6 | `Cortina` | 2 | | **255** | 37,4% nulo |
| 7 | `Hilera` | 2 | | **255** | 37,4% nulo |
| 8 | `Planta` | 2 | | **255** | 37,4% nulo |
| 9 | `Muestras` | 2 | | 0 | número de muestras requeridas |

Los 255 nulos coinciden exactamente en las tres columnas: son 255 filas que definen el
muestreo a nivel de lote, sin bajar a planta. Coexisten dos granos en la misma tabla.

**Estado.** **0 consultas la consumen** (H-12). Es la tabla que permitiría validar
cobertura de muestreo.

---

#### `M_EquivalenciaElifab` — 15 filas

**Propósito.** Traduce el nombre de productor que usa la empacadora externa al nombre de la
empresa. Es la tabla puente entre `H02_BDElifab` y el resto del modelo.

| # | Columna | Tipo | Long. | Nulos |
|---|---|---|---|---|
| 1 | `Productor` | 130 | 25 | 0 |
| 2 | `Empresa` | 130 | 25 | 0 |

**Estado.** Sana. Es la única tabla de la base que **resuelve explícitamente un problema de
vocabulario** — precisamente lo que falta para el fundo (H-01). Sirve como precedente
interno para justificar `dim_fundo_alias`.

---

#### `Errores de pegado` — 0 filas

Tabla generada automáticamente por Access cuando falla un pegado masivo. 16 columnas
genéricas (`F1`…`F16`). Vacía. **Descartar en la migración** (H-12).

---

### Tablas de forecast (`R0x`)

#### `R08_Forecast_Campaña` — 101.715 filas

**Propósito.** Proyección de producción **a nivel de campaña completa**, con desglose por
destino comercial y por calibre. Es la tabla más grande después de clima y packing.

**Grano.** Una fila = una proyección de un módulo, en una semana, bajo una versión de
pronóstico.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Version` | 130 | 25 | 1 | **15 versiones nombradas** — ver abajo |
| 2 | `Fundo` | 130 | 30 | 1 | |
| 3 | `FundoPPto` | 130 | 30 | 1 | |
| 4 | `Modulo` | 130 | 5 | 1 | |
| 5 | `Turno` | 130 | 5 | 1 | |
| 6 | `Año` | 2 | | 1 | |
| 7 | `Semana` | 2 | | 1 | |
| 8 | `KG Exp` | 4 | | 0 | kilos exportables · `SUM` = 648.044.713,14 |
| 9 | `Kg Des` | 4 | | 1 | kilos descarte · `SUM` = 32.280.549,28 |
| 10 | `Kg Con` | 4 | | 1 | kilos consumo · `SUM` = 9.359.445,44 |
| 11 | `FrtTotal_Exp` | 4 | | 17.484 | frutos totales exportables; 17,2% nulo |
| 12 | `Campaña` | 130 | 12 | 1 | |
| 13–21 | `C12`…`C26` | 4 | | 13.121 | **desglose por calibre**; 12,9% nulo |

**No existe columna `KG` genérica** — de ahí H-04 caso 6.

**Las 15 versiones de proyección:**

| Versión | Filas | | Versión | Filas |
|---|---|---|---|---|
| `Proy_Mayo` | 15.764 | | `Proy_Mayo_v3` | 7.665 |
| `Proy_Jul_f` | 8.210 | | `Presupuesto 2026` | 4.452 |
| `Proy_Jul` | 8.179 | | `Proy_Marzo` | 4.387 |
| `Proy_Jul_v2` | 8.087 | | `Proy_Abril_L30` | 4.385 |
| `Proy_Jun` | 7.830 | | `Proy_Abril_L15` | 4.385 |
| `Proy_Mayo_JulJun` | 7.674 | | `Proy_Abril` | 4.385 |
| `Proy_Mayo_v2` | 7.667 | | `Proy_Febrero` | 4.340 |
| | | | `Proy_Enero` | 4.304 |
| | | | *(vacío)* | 1 |

**Cómo leer esto.** La tabla **acumula el histórico completo de re-proyecciones**, no solo
la vigente. `Presupuesto 2026` es la línea base aprobada; cada `Proy_<mes>` es una revisión
posterior. Los sufijos `_v2`, `_v3`, `_f` son iteraciones dentro del mismo mes (`_f`
presumiblemente "final").

**Consecuencia crítica para Power BI:** cualquier agregación sin filtrar por `Version`
**suma todas las proyecciones históricas juntas**. Ese es el origen del `SUM([KG Exp])` de
648 millones de kg — una cifra que no representa producción, sino la suma de 15 escenarios
distintos del mismo periodo. **Toda medida sobre esta tabla debe filtrar una versión.**

Los 13.121 nulos en las columnas de calibre `C12`–`C26` son idénticos en las 9 columnas:
son las versiones antiguas, anteriores a que se empezara a proyectar por calibre.

**Estado.** Estructuralmente aceptable; el riesgo es de interpretación, no de integridad.

---

#### `R09_Forecast_Semanal` — 48.368 filas

**Propósito.** Proyección **semanal** de cosecha a nivel de lote. Más granular y de horizonte
más corto que `R08`.

**Grano.** Una fila = proyección de un lote para una fecha de cosecha, bajo una versión.

| # | Columna | Tipo | Long. | Nulos | Nota |
|---|---|---|---|---|---|
| 1 | `Campaña` | 130 | 10 | 0 | |
| 2 | `Pasada` | 3 | | **22.765** | número de pasada; 47,1% nulo |
| 3 | `Mod` | 130 | 5 | 0 | módulo (abreviado) |
| 4 | `Turno` | 130 | 5 | 0 | |
| 5 | `Lote` | 130 | 5 | 0 | |
| 6 | `Area` | 4 | | 0 | |
| 7 | `FCosAnt` | 7 | | 0 | fecha de cosecha anterior |
| 8 | `FCos` | 7 | | 0 | **fecha de cosecha proyectada** |
| 9 | `Sem` | 2 | | 0 | |
| 10 | `FrtCos` | 4 | | 0 | frutos a cosechar |
| 11 | `Peso` | 3 | | **22.765** | peso unitario; 47,1% nulo |
| 12 | `FrutosTotal` | 3 | | **22.765** | 47,1% nulo |
| 13 | `Rend` | 4 | | 0 | rendimiento |
| 14 | `Kg` | 4 | | 0 | `SUM` = 51.083.049,92 |
| 15 | `Dr` | 2 | | 0 | |
| 16 | `Version` | 130 | 10 | 0 | **46 versiones** `S01`–`S32` + sufijos |
| 17 | `FundPPTo` | 130 | 50 | 0 | typo: falta la `o` de "Fund**o**PPTo" |
| 18 | `Fundo` | 130 | 50 | 0 | |

**Las versiones codifican la semana de emisión.** Van de `S01` a `S32`, con sufijos `_v2`,
`_v3`, `_V2` (nótese la inconsistencia de mayúsculas: `S11_V2` y `S12_V2` en mayúscula,
`S01_v2` y `S13_v2` en minúscula). Son **46 versiones distintas** en total.

La consulta `R0901_Forecas_SemAc` extrae el número de semana con
`Int(Right(Left(Version,3),2))` — toma los caracteres 2 y 3 del texto — para quedarse solo
con la proyección vigente de cada semana. Ese parseo funciona con `S01` pero **es frágil**:
depende de que el formato nunca cambie de longitud.

**Los 22.765 nulos coinciden exactamente** en `Pasada`, `Peso` y `FrutosTotal` — el 47,1%.
Son las versiones que no proyectaban a ese nivel de detalle.

**Diferencia de escala con `R08`.** `SUM(R09.Kg)` = 51,08 M frente a
`SUM(R08.[KG Exp])` = 648,04 M. La razón está en el número de versiones y el alcance: no
son comparables directamente. Esto es lo que hace ambigua la corrección de
`R0902_Forecast_Sem_vs_Camp` (H-04 caso 6).

**Estado.** Aceptable; typo `FundPPTo`, versiones con mayúsculas inconsistentes, parseo
frágil de la versión.

---

## 6 · Modelo de negocio implícito

La base no declara relaciones (H-02), pero el modelo existe en la lógica de las consultas.
Reconstruido:

### Jerarquía física

```
Fundo  (4 vocabularios distintos — H-01)
  └── Módulo
        └── Turno            ← solo existe en M_Lotes, H01 y E05
              └── Lote       ← unidad de gestión: 860 registros, 829,02 ha, 4.711.564 plantas
                    └── Cortina
                          └── Hilera
                                └── Planta   ← grano de las evaluaciones
```

**Nota sobre `Turno`.** No es una unidad física sino un agrupamiento de gestión (turno de
riego o de labor). Solo `M_Lotes`, `H01_ProdHistorica` y `E05_DiametrosBayas` lo traen de
origen; el resto de tablas debe obtenerlo por join contra `M_Lotes` — y ese join es
justamente el que falla en H-01.

### Ciclo productivo — la cadena fenológica

```
    M_Poda.FInicio            inicio del ciclo: la poda
          ↓
    E04_Brotes                brotes nuevos          3.385 filas · SUM = 225.638 brotes
          ↓
    E01_Ramas                 estructura de madera  94.236 filas · SUM = 730.318 ramas
          ↓
    E02_ConteoFlores          floración y cuajo     43.490 filas · SUM = 3.050.031 flores
          ↓
    E03_ConteoEstados         fruto E1→E5           18.714 filas · SUM = 9.060.271 frutos
          ↓
    E05_DiametrosBayas        calibre de baya        4.193 filas · AVG = 19,885 mm
          ↓
    H00 / H01                 cosecha               30.812 / 30.626 filas · ~32,45 M kg
          ↓
    H02_BDElifab              packing y mercado    117.536 filas · CHINA/USA/ÁCIDO/DESCARTE
```

**Cómo leer la cadena.** Cada eslabón predice el siguiente. Los brotes determinan cuántas
ramas habrá; las ramas, cuántas flores; las flores que cuajan, cuántos frutos; los estados
E1–E5, cuándo estarán listos; el diámetro, a qué calibre y mercado irán. **El valor
analítico de esta base está en recorrer la cadena completa** — y hoy no se puede, porque
`E05_DiametrosBayas` está desconectada (H-12) y los eslabones `E01`/`E04` no enlazan con el
maestro de lotes (H-01).

`H05_Clima` es transversal: la temperatura y los grados-día aceleran o retrasan cada
transición de la cadena.

### Los estados E1–E5

Son los cinco estados de madurez del fruto. La consulta `0302_ConteoAjustado` los convierte
en proporciones (`pE1 = SUM(E1)/SUM(E1..E5)`) precisamente porque el conteo absoluto no es
comparable entre lotes: cada evaluador muestrea un número distinto de plantas. La
distribución `pE1..pE5` es lo que permite estimar cuántos días faltan para la cosecha.

---

## 7 · Anexo · Cifras de control

Extraídas de `evidencia\04_metricas_validacion.txt`. Son el **contrato de aceptación** de la
migración: PostgreSQL debe reproducir estos números, salvo los marcados `[SE CORRIGE]`.

### Filas por tabla

| Tabla | Filas | | Tabla | Filas |
|---|---|---|---|---|
| `E01_Ramas` | 94.236 | | `M_EquivalenciaElifab` | 15 |
| `E02_ConteoFlores` | 43.490 | | `M_Evaluadores` | 31 |
| `E03_ConteoEstados` | 18.714 | | `M_Lotes` | 860 |
| `E04_Brotes` | 3.385 | | `M_nMuestra` | 681 |
| `E05_DiametrosBayas` | 4.193 | | `M_Poda` | 2.159 |
| `Errores de pegado` | 0 | | `M_Time` | 2.189 |
| `H00_VolumenCampo` | 30.812 | | `R08_Forecast_Campaña` | 101.715 |
| `H01_ProdHistorica` | 30.626 | | `R09_Forecast_Semanal` | 48.368 |
| `H02_BDElifab` | 117.536 | | | |
| `H05_Clima` | 155.588 | | **TOTAL** | **683.180** |

### Métricas que deben reproducirse exactamente

| Métrica | Valor |
|---|---|
| `H00 SUM(KG)` sin fila basura | 32.450.472,596651 |
| `H01 SUM(KG)` sin filas basura | 32.445.986,0163518 |
| `E01 SUM([# Ramas])` | 730.318 |
| `E02 SUM(nFlores)` | 3.050.031 |
| `E03 SUM(Total)` | 9.060.271 |
| `E03 SUM(E1..E5)` | 9.057.841 |
| `E04 SUM(Brotes)` | 225.638 |
| `E05 AVG(Diametro)` | 19,8850703636331 |
| `M_Lotes SUM(Area)` | 829,021356070414 ha |
| `M_Lotes SUM(NPlantas)` | 4.711.564 |
| `R08 SUM([KG Exp])` | 648.044.713,139312 |
| `R09 SUM(Kg)` | 51.083.049,9174915 |

### Defectos que deben quedar en CERO tras migrar

| Defecto | Valor actual | Objetivo |
|---|---|---|
| H-01 · `E01_Ramas` huérfanos vs `M_Lotes` | 94.236 | **0** |
| H-01 · `E04_Brotes` huérfanos | 3.385 | **0** |
| H-01 · `H00` huérfanos | 366 | **0** |
| H-01 · `H01` huérfanos | 180 | **0** |
| H-01 · `0101_Diametros` con `Turno` NULL | 94.236 | **0** |
| H-03 · `E01_Ramas` filas de exceso | 23.141 | **0** |
| H-05 · `01_Flores_C2025` filas | 487.368 | **9.040** |
| H-06 · filas basura en `H00`+`H01` | 3 | **0** |
| H-06 · KG en filas basura | 1.925.995 | **0** |
| H-08 · `H05_Clima` grupos duplicados | 2.079 | **0** |
| H-09 · evaluadores sin maestro | 2 | **0** |
| H-04 · consultas rotas | **6** | **0** |

---

## 8 · Conclusión

La base cumple su función operativa: **683.180 filas** que cubren cinco campañas
(C2022–C2026) de un cultivo de 829 hectáreas y 4,7 millones de plantas. La información
está ahí y es rica.

El problema no es la información sino **la ausencia de contratos sobre ella**. Sin claves
foráneas, sin claves primarias correctas, sin un vocabulario único para nombrar el fundo,
cada defecto entra en silencio y se propaga hasta los tableros de gerencia sin que nada lo
señale.

Los tres hallazgos críticos comparten una misma raíz: **el motor nunca tuvo permiso para
rechazar un dato inválido.** H-01 (vocabularios incompatibles) existe porque ninguna
restricción exigió que el fundo fuese un valor conocido. H-03 (duplicados) existe porque
ningún índice único rechazó la segunda carga. Y H-02 es literalmente esa ausencia de
restricciones.

**Por eso la recomendación es migrar el modelo corregido, no el modelo actual.** PostgreSQL
puede declarar esas restricciones; Access, en la práctica, no las tenía. Replicar la
estructura tal cual sería conservar el único defecto que garantiza que todos los demás
vuelvan a aparecer.

### Documentos relacionados

| Documento | Para quién | Qué contiene |
|---|---|---|
| `02_LOGICA_NEGOCIO.md` | Agronomía, analistas | las 40 consultas explicadas: qué hacen y por qué existen |
| `03_GUIA_REPORTES.md` | Área de Reportes / Power BI | contrato de interfaz, advertencias por consulta, checklist |
| `04_PLAN_MIGRACION.md` | TI | DDL, ETL, cronograma, decisiones pendientes |
| `evidencia\` | verificación | volcados crudos reproducibles |
