# Hallazgos accionables: qué decidir hoy y qué medir para decidir mejor

**Fecha:** 2026-08-19 · **Corrida:** relations n.º 29 · **Fuente:** PostgreSQL, esquemas
`stg` → `core` → `analytics`

> **Revisión del 2026-08-19.** Una auditoría encontró seis defectos que inflaban los
> resultados: el riego duplicaba el 30 % del panel, el área del módulo se contaba una vez
> por día de cosecha, y la significancia se calculaba sobre el número de filas cuando la
> información independiente eran las semanas —una razón de hasta 629 a 1—. Corregidos los
> tres, **de 49 pares supervivientes quedan 23, y de 66 relaciones de packing quedan 7**.
> Las cifras de este documento son las posteriores a la corrección.
>
> Y una conclusión que cambia el tono de todo lo demás: con la inferencia bien hecha,
> **109 cruces sobreviven donde por azar se esperaban 74**. Es 1,5 veces el ruido. El
> conjunto no se separa del azar con holgura, así que nada de aquí sostiene hoy una
> decisión de manejo por sí solo.

Este documento no es un catálogo de correlaciones. Responde tres preguntas de negocio en
orden: qué permite explorar la medición existente, qué está a medio comprobar, y qué habría
que cambiar en la forma de medir para responder lo que hoy no se puede.

Se reparte en dos módulos del tablero, y el reparto es deliberado: **Relaciones** muestra la
evidencia —la matriz completa, el perfil de desfases, el tamaño de los efectos y el recuento
de lo descartado— y **Descubrimientos** publica lo que se puede afirmar con ella y hasta
dónde llega cada afirmación.

---

## 1. El punto de partida: la medición pone el techo, no el cultivo

La limitación no es biológica sino de medición, y cada una acota qué unidad de análisis es
legítima:

| Limitación real | Consecuencia sobre la unidad |
|---|---|
| Una estación meteorológica para 5 fundos | Todos los lotes de una semana comparten el mismo clima. La unidad es **semana**: ~183 observaciones independientes, no 30.000 filas |
| Packing en 15 de 26 módulos, al grano de módulo | **módulo × semana**. Repartir un calibre de módulo entre sus lotes inventaría variación que no se midió |
| Censo de bayas: 2 fechas, 36 lotes | Sin serie posible. El diámetro de baya no sostiene ningún desfase |
| Fenología: 2 campañas (2025 y 2026) | **lote × semana**, con réplica entre años suficiente para descartar coincidencias de un solo año |

Que el clima sea común a la semana no es un detalle: es lo que invalidaba la inferencia
anterior. Repetir el mismo dato en 260 lotes no crea información nueva, y calcular el
p-valor sobre las filas lo trataba como si la creara.

## 2. Cómo se filtra ahora

1.481 pruebas entre los dos barridos. Con ese volumen, unas **74 saldrían «significativas»
por puro azar** aunque no hubiera ninguna relación real. Los filtros, en orden:

1. **Descuento de calendario y módulo.** Sin él casi todo correlaciona: clima y cosecha
   siguen la misma estación del año.
2. **Placebo, medido en la misma escala.** Una serie futura desplazada que solo conoce la
   fecha, comparada contra la correlación parcial —antes se comparaba contra la cruda, que
   cargaba con todo el calendario ya descontado—. **729 pruebas cayeron aquí.**
3. **Significancia con errores agrupados** por semana y por lote, sobre la correlación
   parcial que es la que se publica. Se conserva el más conservador de los dos.
4. **Doble corrección de multiplicidad.** Šidák dentro del par por quedarse con el mejor de
   nueve desfases, y Benjamini-Hochberg sobre el total.

Sobreviven **109 pruebas**, que consolidadas por par dan **26 relaciones: 14 con más
respaldo y 12 hipótesis**. Contra 74 esperadas por azar, el margen es de 1,5 veces.

## 3. Lo que se puede explorar hoy

Las relaciones con más respaldo, con el efecto expresado como el cambio al pasar del cuarto
más bajo al más alto del predictor:

| Señal | Resultado | Correlación | Antelación | Respaldo |
|---|---|---:|---|---|
| Frutos por planta | Avance de maduración | +0,45 | 3 semanas | 63 sem |
| Avance de maduración | Peso del fruto | −0,44 | 4 semanas | 62 sem |
| Avance de maduración | Rendimiento | +0,42 | misma semana | 58 sem |
| Proporción en E1 | Peso del fruto | +0,40 | 8 semanas | 61 sem |
| Frutos por planta | Rendimiento | +0,37 | 6 semanas | 62 sem |
| Proporción en E1 | Rendimiento | −0,35 | 5 semanas | 62 sem |
| Calibre en línea | Rendimiento del módulo | +0,33 | 4 semanas | 94 sem |
| Radiación | Flores por planta | +0,30 | 4 semanas | 68 sem |

La más firme de toda la plataforma sigue siendo **calibre en línea → peso del fruto (0,66
sobre 98 semanas)**, y no es casualidad: es la única medida en una báscula industrial y no
por muestreo.

**Ninguna es una causa demostrada, y con este margen sobre el azar ninguna sostiene por sí
sola una decisión de manejo.** Sirven para orientar qué mirar y qué medir mejor.

## 4. Tres lecturas que se prestan a error

**Una correlación alta puede no servir para nada.** Lluvia y descarte tienen la correlación
más alta del bloque de packing (0,41) y el efecto práctico es cero: en la costa el cuarto
seco y el cuarto lluvioso son casi el mismo milímetro.

**Más flores no está dando más frutos.** Más flores por planta acompaña a *menos* frutos por
planta. Puede ser competencia por recursos o un efecto del muestreo —flores y frutos no se
cuentan sobre las mismas plantas—. No hay dato para distinguirlo.

**El riego asociado a más kilos no prueba nada.** El riego no se asigna al azar: se riega más
donde hay más carga que sostener.

## 5. Qué falta medir, por orden de lo que desbloquea

1. **Estaciones meteorológicas por fundo.** Hoy una sola para cinco. Es el techo de todo el
   bloque climático: por mucho que crezca la base, la información independiente sigue siendo
   ~183 semanas. Multiplica el dato real sin cambiar una línea de análisis.
2. **Censo de bayas semanal.** Dos fechas sobre 36 lotes. Por eso el diámetro de baya —lo
   que anticipa el peso— no sostiene ninguna serie. El procedimiento y la gente existen; es
   cadencia. Convertiría el peso en predecible con antelación, no solo explicable después.
3. **Registrar nutrición y sanidad.** No existe registro de fertilización ni de
   aplicaciones. Su efecto aparece hoy como ruido inexplicado en todos los modelos.
4. **Cargar la pérdida en campo.** El entierro de fruta está medido en el Access de 2025
   —564 toneladas, 6,6 % de lo cosechado— y no está en la base. El packing solo ve lo que
   entra a planta. Abre una pregunta que hoy no se puede ni formular: por qué un lote
   entierra el 15 % y otro el 2 %.
5. **Ensayos con tratamientos asignados.** 10–20 lotes comparables, dos niveles de una sola
   variable. Es el único camino a afirmaciones causales; sin él todo queda en anticipar.

## 6. Lo que este análisis no puede sostener

- **Causalidad.** Por lo dicho arriba, y no se resuelve con más datos observacionales.
- **Series de bayas y brotes con desfases largos.** Dos evaluaciones por lote no dan.
- **Nutrición, polinización, suelo, sanidad y pérdida en campo.** No existen en la base: su
  ausencia de los hallazgos no significa que no importen.
- **Extrapolar packing a los 11 módulos sin línea.**
- **Proyección climática.** Solo hay clima observado, sin pronóstico futuro.
