# Modelo híbrido de oleadas as-of: propuesta H1–H6

## Diagnóstico actual

El problema no es que falte probar otro algoritmo. El modelo nuevo no ha ayudado de
forma consistente porque se ha intentado aprender kilos agregados con una señal que
en realidad está organizada por oleadas y porque varias pruebas introducen información
que solo existe después del corte.

| Problema | Consecuencia |
| --- | --- |
| La curva manual contiene X/O/N y A/B por oleada, pero el residual actual corrige principalmente frutos y peso totales. | Puede mejorar un total sin explicar qué oleada se movió ni si el error fue de carga, fecha o calibre. |
| El modelo de componentes llegó a 1,148 filas en cero por la compuerta de ocurrencia y obtuvo WAPE 86.41% frente a 80.99% de R09 en su primera evaluación. | Un cero de la compuerta se convierte en una falsa ausencia de cosecha; no es una forma segura de proyectar seis semanas. |
| El nowcast mejora al incorporar lunes/martes reales, pero eso es una estimación de cierre de miércoles, no una predicción pre-semana. | No resuelve la necesidad de H1–H6 desde el corte. |
| El ajuste de corrección de horizonte H2–H6 no produjo mejora estable. | Cambiar el desplazamiento final no identifica el mecanismo de la oleada. |
| Hay una estación climática para varios fundos, pocas campañas con conteo de bayas y observaciones fenológicas no continuas. | Se pueden obtener asociaciones inestables, pero no evidencia suficiente para llamar causa a una variable. |

La evidencia y los números anteriores están documentados en [la plataforma predictiva](04_plataforma_analitica_predictiva.md), [el motor y replay](07_motor_proyeccion_y_replay.md), [el diagnóstico de bloques](05_analisis_por_bloques.md) y [el diagnóstico del nowcast](../seguimiento/15_nowcast_cierre_adaptativo_2026-08-26.md).

## Integración propuesta

La propuesta es un modelo estructural con aprendizaje regularizado, no sustituir el
proceso manual por un modelo opaco:

```text
Parametros y cálculos revisados de Excel
       X/O/N + A/B + factor de caída + calendario
                         |
                         v
       prior manual por lote / módulo / fundo
                         |
                         +--> CandidateParamDelta
                         |    aprende transiciones Excel anteriores al corte
                         v
       ajuste conjunto de carga, timing y dispersión con cosecha < corte
                         |
                         v
       curva de tres oleadas + peso por oleada, H1 ... H6
                         |
                         +--> kg P1/P2/P3, participación, peso y acumulado
                         +--> atribución mecánica del cambio frente al Excel
```

La implementación estructural vive en
[`oleadas_asof.py`](../../packages/analitica/dominio/modelos/hibrido/oleadas_asof.py) y
el orquestador manual/automático en
[`oleadas_candidato.py`](../../packages/analitica/aplicacion/parametros/oleadas_candidato.py).
La capa integrada que ya puede competir como challenger está en
[`estado_oleadas.py`](../../packages/analitica/aplicacion/procesos/estado_oleadas.py) y se
puede encender en el torneo con `incluir_estado_oleadas=True`; permanece apagada por
defecto y nunca se promociona sin los gates.

La integración tiene dos entradas separadas:

```text
R09 publicado (nivel y calendario H1...H6)
              |
              +--> residuales cerrados antes de la emisión
              |        -> factor_estado_asof -> P50 corregido
              |
              +--> panel opcional de oleadas manuales/gaussianas
                       -> participación P1/P2/P3 y ola principal
```

La ruta numérica no necesita Excel. Si se entrega la salida manual de oleadas adaptada
a la clave `campania × (lote_id o lote) × fecha_emision × fecha_objetivo`, se usa para explicar
el timing y repartir el P50; no se la deja sustituir el nivel R09, que fue la fuente de
la mala precisión del candidato gaussiano aislado.

El Excel es opcional en la ruta automática: `construir_prior_automatico` puede partir
de poda, área, plantas y una campaña histórica. Si existe un prior de campaña anterior,
se traslada al lote actual y se corrige con la historia as-of; si no existe, usa un
prior agronómico explícito y lo marca con advertencias de soporte.

### Contexto continuo sin depender del Excel

El puente [`contexto_oleadas.py`](../../packages/analitica/aplicacion/parametros/contexto_oleadas.py)
permite usar las mismas señales de poda, flores, clima, riego y cosecha sin convertirlas
directamente en kilos. `unir_contexto_asof` toma, para cada emisión, la última observación
estrictamente anterior; acepta claves físicas explícitas para no depender de nombres de
fundo que cambian entre fuentes. Luego `ModeloContextoOleadas` aprende, con ridge robusta,
el delta de `X/O/N/A/B` asociado al contexto y lo aplica después del prior automático o de
la fila manual.

El ajuste continuo solo se activa si el parámetro tiene al menos 24 transiciones válidas y
la emisión tiene al menos 50% de sus features disponibles. Los deltas se acotan por tipo de
parámetro y cada fila conserva las contribuciones por feature, el driver mecánico principal,
la cobertura y `sin_fuga=True`. La salida mantiene `etiqueta_causal=False`: “más GDD se
asocia con un X1 más tardío” puede ser una lectura del modelo, pero “el GDD causó el cambio”
requiere una intervención o experimento.

La ruta por lote queda así:

```python
from analitica.aplicacion.parametros import (
    ModeloContextoOleadas,
    proyectar_universo_automatico_oleadas,
    unir_contexto_asof,
)

# Cada fuente se une as-of y sus features se combinan por la identidad física.
# contexto_por_lote usa la clave (campania, fundo, modulo, turno, lote).
modelo_contexto = ModeloContextoOleadas(
    feature_names=("dias_desde_poda", "gdd_acum_poda_obs", "Rad", "ETo")
).fit(transiciones_con_parametros, fecha_corte=fecha_emision)

salida, metadata = proyectar_universo_automatico_oleadas(
    lotes, cosecha_h01, fecha_emision,
    semanas=6,
    modelo_contexto=modelo_contexto,
    contexto_por_lote=contexto_por_lote,
)
```

Si todavía no existen suficientes transiciones históricas de parámetros, el modelo no
fabrica una relación: conserva el prior y marca `sin_soporte_contexto`. Así se puede
operar sin Excel desde el inicio, mientras se acumula la base necesaria para que el
contexto llegue a modificar las oleadas.

Para que esa operación no dependa de preparar un libro a mano, el ensamblador
[`contexto_exportado.py`](../../packages/analitica/aplicacion/parametros/contexto_exportado.py)
construye las features desde las exportaciones planas. Agrega clima diario y GDD,
selecciona la poda vigente, resume flores/estados/brotes, y calcula cosecha acumulada
y de las últimas cuatro semanas. La función
`construir_contexto_por_lote_oleadas_asof` devuelve directamente el
`contexto_por_lote` que consume la ruta automática; cada fuente conserva su fecha y
cobertura as-of. La única unión global es clima. Flores, estados y brotes se unen por
las claves físicas que realmente traiga cada exportación; si la fuente no trae campaña,
no se debe usar sin filtrar la campaña cuando se mezclen varios ciclos.

El mismo adaptador reconoce los encabezados de las hojas revisadas: `VarClima` puede
entregar `Radiacion Solar`, `ETO` y `Suma de GDD`; `EvFlores`, `Promedio de Fecha`,
`Cantidad Flores` y `Dias desde Poda`; y `Riego`, `Agua/ha` o `m3/ha`. `Agua/ha` se
conserva como `riego_agua_ha` porque el encabezado no declara la unidad; solo un
encabezado explícito `m3/ha` alimenta `riego_m3_ha`. Las hojas sin campaña se rechazan
si se intenta mezclarlas con más de una campaña en la misma corrida.

El replay [`replay_oleadas_automatico.py`](../../packages/analitica/aplicacion/procesos/replay_oleadas_automatico.py)
repite la emisión para varias fechas, genera H1--H6 y solo mide semanas cuyo cierre
completo ya está disponible en H01. Una semana cerrada sin fila H01 se cuenta como cero;
una semana aún abierta queda fuera del denominador. Esto separa cobertura operativa de
precisión y permite medir la ruta automática antes de conectarla a una publicación.

La identidad por semana es:

```text
frutos_i,w = N_i · [Φ((t_fin - X_i) / O_i) - Φ((t_ini - X_i) / O_i)]
kg_i,w     = plantas · frutos_i,w · factor_caida · (A_i · exp(B_i · t_fin)) / 1000
kg_w       = kg_1,w + kg_2,w + kg_3,w
```

El código conserva los valores A1/B1, A2/B2 y A3/B3 del libro. El ajuste as-of puede
mover X/O/N y, si hay suficientes pesos observados, aplica una corrección común de
calibre; con pocas observaciones el prior manual domina explícitamente.

## Cálculos Excel que sí se reutilizan

Las hojas revisadas contienen cálculos aprovechables, pero cada uno debe conservar su
grano y su significado:

| Hoja/cálculo | Integración en el modelo | Qué no se debe hacer |
| --- | --- | --- |
| `HistoricosVolumen`: `Frutos por planta = Frutos Totales / NPlantas` | objetivo de carga para calibrar `N1/N2/N3` | tratar filas repetidas de módulo-semana como réplicas independientes |
| `EvFlores`: `Días desde poda = Fecha promedio de floración - Fecha poda` | señal de timing para `X1/X2/X3` y su dispersión | convertir una fecha de floración en kilos directamente |
| `VarClima`: GDD, temperatura, radiación, lluvia y ETo | señales as-of para timing, transición y peso | usar clima observado posterior a la emisión |
| `Riego`: agua/ha y nutrientes | señales de manejo para contrastar cuajado y llenado | sumar turnos que ya están expresados por hectárea |
| `M_Poda`: poda, área y plantas | reloj biológico y escala física del lote | sustituir una poda faltante por la fecha de emisión |
| `Panel`: `Finicio`, `FePas1...FePasN`, reingreso y fin de semana | calendario discreto de pasadas; se entrega mediante `ventanas` | inventar fechas de pasada con una frecuencia fija y presentarlas como observadas |

La tabla de contribuciones permite contestar “qué cambia el volumen” en el nivel que
los datos soportan: más `N_i` significa más carga de la oleada, un `X_i` mayor la
retrasa, un `O_i` mayor la dispersa, y A/B cambian el calibre. Eso es una explicación
mecánica del cálculo; para afirmar que el clima, el riego o una práctica **causó** el
cambio hace falta que la asociación sobreviva a cortes temporales, controles por módulo
y un experimento o intervención.

## Qué se puede explicar

La ruta estructural `oleadas_candidato.py` entrega para cada H1–H6:

- kg de P1, P2 y P3 y su participación;
- carga de cada oleada (`N1`, `N2`, `N3`);
- centro temporal (`X1`, `X2`, `X3`) y dispersión (`O1`, `O2`, `O3`);
- peso estimado por oleada y kilos acumulados; y
- cambio incremental atribuible a amplitud, timing, dispersión, calibre o merma frente al prior de Excel.

El challenger integrado `HibridoEstadoOleadas_v1` expone de forma más acotada el P50
corregido, la participación mecánica de las oleadas y el `driver_mecanico_principal`;
solo mostrará X/O/N/A/B si se le entrega un panel que los conserve. No debe confundirse
la explicación disponible del cálculo con una estimación causal completa.

Por ejemplo, sí se puede decir: “la diferencia de H3 viene principalmente de un
aumento mecánico de la carga de P2 y no de un cambio de calibre”. No se debe decir
todavía: “la radiación causó el aumento”. Para esa frase hay que aprender la relación
entre clima/manejo y los parámetros con validación fuera de muestra y, si se quiere
causalidad, con una intervención o experimento.

## Cómo entran las otras hojas

Las hojas revisadas no deben mezclarse directamente en una columna de kilos. Deben
entrar como señales as-of que explican parámetros:

- `M_Poda`: fecha y dispersión de poda, para el reloj biológico;
- `EvFlores`: carga floral y días desde poda, agregada por lote/módulo-semana;
- `Riego`: lámina, reposición y nutrientes, agregados por lote/módulo-semana;
- `VarClima`: clima/GDD, con cobertura y estación identificadas; y
- `Resumen2025`/`HistoricosVolumen`: priors y replay por campaña, no filas independientes artificiales.

La integración queda habilitada por el contrato de fila manual y por `ventanas`: se
pueden conservar las fechas calculadas en Excel o generar H1–H6 con el calendario
semanal del panel. Los predictores futuros no se usan para construir una emisión
pre-semana.

### Auditoría de las exportaciones disponibles

Como el libro `ProySemanal_*.xlsm` vigente no está en el workspace, se añadió un
adaptador explícito para las exportaciones planas disponibles en
[`r09_exportado.py`](../../packages/analitica/aplicacion/procesos/r09_exportado.py).
La identidad no depende del nombre del fundo —que cambia entre R09 y H01—, sino de
`campania + modulo + turno + lote`; las filas descartadas y la cobertura del maestro
quedan en un manifiesto.

En la revisión del 31 de agosto de 2026, el adaptador encontró:

| Entrada | Evidencia disponible | Limitación para aprender una causa |
| --- | --- | --- |
| `r09_forecast_semanal.csv` | 56.753 filas, 827 lotes en el forecast; la emisión más reciente es C2026/S35, 24-ago-2026 | S35 trae H1–H5; H6 no es una observación publicada |
| `h01_prod_historica.csv` | 31.802 filas; en C2026 el panel completo tiene 821 lotes y 752 con real | 64 identidades de S35 no tienen historia H01 emparejada |
| `m_lotes.csv` | 860 identidades del maestro; 817 lotes del forecast tienen plantas y 9 quedan sin plantas | sin plantas no se puede atribuir escala física con seguridad |
| `Datos mes.xlsx` | clima hasta 26-jul-2026, flores C2026 hasta 07-ene-2026 y riego solo hasta 28-dic-2025 | no está sincronizado con el corte C2026/S35 |

Como prueba de que la dependencia del libro no es estructural, el puente as-of se reconstruyó
con las exportaciones planas de C2026/S35: poda cubrió 816 de 817 identidades (99,88%),
flores 816 (99,88%) y clima 817 (100%). El último contexto usado fue 30-jul para flores,
11-mar para poda y 26-jul para clima; en los tres casos quedó antes del corte 24-ago. El
riego del Excel no se imputó a C2026 porque su última fecha disponible es anterior a la
campaña y mezclarlo sin trazabilidad habría introducido una falsa señal de manejo.

La nueva construcción reproducible, usando `m_poda.csv` + `m_lotes.csv` como universo
físico, dejó 811 lotes C2026 con poda válida y 808 con área y plantas utilizables. En la
emisión 24-ago, el contexto cubrió 100% en poda, GDD/DPV/radiación/ETo, 99,38% en
flores, 99,51% en estados, 83,35% en brotes y 91,62% en cosecha previa. Riego quedó en
0% porque no hay una exportación C2026 sincronizada; no se imputó. El resultado prueba
que el Excel no es un requisito técnico para armar el estado del lote, pero todavía no
prueba que esas variables mejoren el pronóstico.

La salida viva sí puede solicitar seis semanas. Para S35 entrega 593, 459, 567, 538
y 710 lotes en H1–H5; H6 contiene 710 filas marcadas
`horizonte_extendido=True`. Esa cola hereda el último P50 R09 y el factor de estado de
la última semana publicada, pero no se cuenta como real ni como una sexta semana
aprendida. La llamada reproducible es:

```python
from analitica.aplicacion.procesos.estado_oleadas import proyectar_estado_oleadas_asof
from analitica.aplicacion.procesos.r09_exportado import cargar_panel_r09_csv

panel, manifiesto = cargar_panel_r09_csv(
    "data/salida/r09_forecast_semanal.csv",
    "data/salida/h01_prod_historica.csv",
    "data/salida/m_lotes.csv",
)
salida, metadata = proyectar_estado_oleadas_asof(panel, horizonte_semanas=6)
```

El replay sobre estos CSV tampoco permite declarar victoria: en C2026 operativo el
R09 obtuvo WAPE 41,60% y el challenger 44,69%, con el sesgo pasando de +6,79% a
−28,71%. En planificación el WAPE bajó apenas de 51,16% a 50,05%, pero el sesgo pasó
de +17,41% a −25,47%. Difiere del replay oficial en Parquet (38,39% operativo y
47,46% planificación para el challenger), lo que demuestra sensibilidad al snapshot,
la selección de versiones y la cobertura; ambas evaluaciones no deben mezclarse como
si fueran el mismo dato.

## Resultado real preliminar

Primero se corrigió un problema de grano que invalidaba parte del ajuste: H01 puede
tener varias filas diarias para una misma `pana`. Si cada fila se convertía en una
ventana de siete días, las ventanas se solapaban y la misma pasada pesaba varias veces.
Ahora se agrupa por identidad de lote y pasada, se suma el kg, se pondera el peso por
kg con un peso equivalente que conserva `sum(kg/peso)`, y se reconstruyen intervalos
contiguos; el corte as-of se aplica antes de agrupar.

Después de esa corrección se hizo un replay rolling-origin con 452 lotes cuya identidad
física aparece en C2024 y C2025. Cada emisión entrega 2,712 filas (452 lotes × H1–H6)
y solo usa cosecha con fecha estrictamente anterior a la emisión. WAPE es
`sum(abs(pred-real)) / sum(real)` y el sesgo es `sum(pred-real) / sum(real)`:

| Emisión | Real kg | Predicho kg | WAPE | Sesgo |
| --- | ---: | ---: | ---: | ---: |
| 2025-09-15 | 3,628,355 | 2,304,933 | 95.9% | -36.5% |
| 2025-10-13 | 3,067,656 | 1,745,093 | 82.9% | -43.1% |
| 2025-11-10 | 2,619,110 | 1,175,319 | 79.0% | -55.1% |
| 2025-12-08 | 1,367,406 | 879,265 | 85.0% | -35.7% |
| 2026-01-05 | 546,519 | 447,675 | 101.4% | -18.1% |
| 2026-01-19 | 241,843 | 320,806 | 139.9% | +32.7% |

La corrección de pasada era necesaria, pero no vuelve útil al modelo por sí sola: la
curva sigue subestimando buena parte de la campaña y sobreestima en el corte tardío.
Una regla exploratoria de tendencia reciente mejora solo ese último corte, pero no de
forma estable en los cortes anteriores; por eso no se convirtió en un ajuste por
defecto.

También se ejecutó un smoke test C2026 con 12 lotes: produjo 72 filas, H1–H6 desde
2026-08-24 hasta 2026-10-05. Inyectar observaciones extremas posteriores a la emisión
 no cambió ninguna proyección, lo que confirma el corte temporal en esa ruta. Esto
valida la ejecución y la ausencia de fuga, no la precisión ni la causalidad.

Como control adicional, el replay automático sin `ModeloContextoOleadas` —es decir, el
prior explícito más el ajuste de oleadas con H01 anterior— se ejecutó en cuatro cortes
C2026 sobre 808 lotes, 19.392 filas H1--H6 y semanas completamente cerradas:

| Emisión | Filas evaluables | WAPE | Sesgo |
| --- | ---: | ---: | ---: |
| 2026-04-27 | 4.848 | 101,19% | −39,84% |
| 2026-05-25 | 4.848 | 91,19% | −19,38% |
| 2026-06-22 | 4.848 | 97,03% | −11,98% |
| 2026-06-29 | 4.848 | 95,05% | −19,31% |
| **Agregado** | **19.392** | **95,62%** | **−18,94%** |

Por horizonte, el corte 29-junio obtuvo WAPE 91,59%, 68,87%, 95,32%, 105,87%,
108,55% y 93,21% en H1--H6, respectivamente. La ruta sí entrega seis semanas, pero
el prior automático subestima el nivel y no pasa un gate de precisión. En las 959 filas
comparables con R09 de ese mismo corte, el automático marcó WAPE 56,07% contra 68,25%
de R09, pero con sesgo −50,49% contra +55,79%; la muestra común es más pequeña y no
autoriza a declarar ganador al candidato. Es evidencia para calibrar escala y
transiciones, no para publicar el prior actual.

Por eso la curva gaussiana aislada sigue fuera de producción. El siguiente paso debe
aprender la escala y el estado actual del lote —idealmente con el cierre acumulado,
floración, riego/clima y disponibilidad de cosecha— sin dejar que una sola campaña dicte
la curva completa.

### Prueba sin Excel: transiciones inferidas desde H01

Como el libro manual vigente no está en el workspace, se añadió
[`transiciones_inferidas.py`](../../packages/analitica/aplicacion/parametros/transiciones_inferidas.py).
El módulo ajusta la misma curva Gaussian/exponencial a H01 en varios cortes y convierte
la diferencia entre cortes en una transición X/O/N/A/B. Así se puede probar el puente
contexto→parámetros sin fabricar una etiqueta manual. La salida queda marcada como
`h01_gaussian_asof_inferido`, `sin_fuga=true` y `etiqueta_causal=false`; no sustituye las
revisiones humanas del libro.

Con cuatro cortes tardíos de C2024 y cuatro de C2025 se obtuvieron 2.861 transiciones
de 15 parámetros sobre H01 anterior al corte. El puente se entrenó solo con reloj de
poda, GDD, clima, DPV, radiación y ETo; no se usó la cosecha futura ni el real de la
semana objetivo para definir el contexto. El holdout C2026, sobre 808 lotes y 19.392
filas H1--H6, dio:

| Emisión | Automático WAPE | Contexto inferido WAPE | Automático sesgo | Contexto inferido sesgo |
| --- | ---: | ---: | ---: | ---: |
| 2026-04-27 | 101,19% | 99,91% | −39,84% | −42,87% |
| 2026-05-25 | 91,19% | 89,81% | −19,38% | −18,28% |
| 2026-06-22 | 97,03% | 96,94% | −11,98% | −13,24% |
| 2026-06-29 | 95,05% | 94,57% | −19,31% | −21,95% |
| **Agregado** | **95,62%** | **95,04%** | **−18,94%** | **−20,54%** |

La mejora agregada es marginal (0,58 puntos de WAPE) y el sesgo empeora 1,60 puntos;
la ruta sigue subestimando el nivel. Esto responde la pregunta de si bastaba añadir
otro algoritmo: no. El candidato puede proyectar seis semanas y el contexto tiene
señal, pero los datos disponibles no identifican una calibración de escala estable ni
transiciones confiables de parámetros. Para promoción hace falta la revisión manual
real o una fuente operativa equivalente, además de un calibrador de nivel validado en
varias campañas.

## Challenger integrado: R09 + estado as-of + oleadas

Se incorporó un candidato separado, `HibridoEstadoOleadas_v1`. Su configuración para el
replay es explícita y reproducible: residuales globales por horizonte, últimas tres
observaciones cerradas, recencia 0,85, regularización cero, factor acotado entre 0,50 y
2,00 y escala de intervalo 1,30. La escala de intervalo se congeló usando C2024–C2025
como desarrollo; C2026 se conserva como holdout. No usa campañas futuras para calcular
una emisión y no usa Excel en la ruta numérica.

La salida conserva `p50_base_kg`, `factor_estado_asof` y `delta_estado_kg`. Cuando se
entrega el panel gaussiano, añade `kg_ola_1_ajustada`…`kg_ola_3_ajustada`, sus
participaciones y `driver_mecanico_principal`; cada fila marca `etiqueta_causal=False`.
Por tanto permite decir “la mayor parte del nivel proyectado está en P2 y el estado
reciente corrigió la amplitud”, pero no “el clima causó el aumento”.

Si una emisión R09 termina en H5, el motor puede completar H6 con el último P50
disponible del mismo lote y emisión. Solo lo hace cuando H5 existe: no rellena dos o más
semanas ausentes ni un hueco interno, porque eso podría convertir una semana sin cosecha
programada en kilos inventados. La fila se marca `horizonte_extendido=True`, conserva
`horizonte_origen_extension=5`, lleva `fuente_horizonte=cola_r09_ultimo_horizonte`
cuando la columna existe y hereda el factor de estado de H5 para evitar un salto
artificial. También recibe un intervalo más amplio. Es una continuidad conservadora para
cumplir H1–H6, no una curva Gaussiana aprendida ni evidencia de que H6 tenga el mismo
nivel; debe sustituirse por la oleada manual/Gaussiana conectada cuando el libro vigente
esté disponible.

El replay oficial disponible contiene 30.773 filas R09 pareadas. El panel no trae
columnas `kg_ola_1..3`, así que la mejora medida abajo pertenece al corrector de estado.
El nuevo `HibridoGaussEstado_v1` genera una forma as-of desde H01 para no bloquear la
prueba por la ausencia del libro; cuando llegue `ProySemanal`, sus oleadas manuales deben
compararse y, si tienen mejor soporte, reemplazar la forma inferida.

| Corte | Banda | R09 WAPE | Challenger WAPE | Mejora WAPE | R09 sesgo | Challenger sesgo | Cobertura challenger |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| C2024–C2025 desarrollo | operativo | 63,36% | 55,39% | 12,58% | 33,26% | 5,49% | 83,57% |
| C2024–C2025 desarrollo | planificación | 130,38% | 122,40% | 6,12% | 94,20% | 75,96% | 82,38% |
| C2026 holdout | operativo | 49,65% | 38,39% | 22,73% | 25,31% | −10,00% | 73,58% |
| C2026 holdout | planificación | 63,29% | 47,46% | 25,00% | 35,59% | −3,34% | 79,19% |

El resultado sí ayuda como corrección de nivel: en C2026 reduce WAPE de 49,65% a
38,39% en operativo y de 63,29% a 47,46% en planificación. Pero no es todavía un
campeón operativo: la cobertura H1–H2 del holdout queda por debajo del rango objetivo y
el sesgo operativo queda en el borde del límite. El agregador global puede marcarlo como
`promover` porque cumple los gates agregados, pero esa decisión no sustituye el control
por campaña/horizonte que hace falta para producción.

### Mezcla de seis semanas: nivel R09 + forma Gaussiana + estado

Para conectar la forma de oleadas con un nivel operativo se añadió el challenger
`HibridoGaussEstado_v1`, implementado en
[`gauss_estado_integrado.py`](../../packages/analitica/aplicacion/procesos/gauss_estado_integrado.py).
La secuencia es:

1. conservar el P50 R09 como nivel inicial;
2. ajustar la curva Gaussiana con H01 estrictamente anterior a la emisión;
3. escalar la forma por lote y emisión al total R09 publicado en las semanas comunes;
4. repartir ese nivel entre H1--H6 y P1/P2/P3;
5. aplicar el factor de estado as-of, calculado solo con cierres anteriores; y
6. completar H6 con la cola Gaussiana escalada cuando R09 solo publica H1--H5.

La salida conserva el nivel R09, el total Gaussiano escalado, el factor de escala, la
participación de cada oleada, el `driver_mecanico_principal` y la marca
`horizonte_extendido`. No lee Excel para calcular y no etiqueta causas. El contexto de
Excel o de las exportaciones planas puede modificar X/O/N y A/B mediante el puente
as-of, pero siempre como señal asociativa y con `sin_fuga=True`.

En el universo común de C2026 con real observado y R09 publicado (H1--H5), la mezcla
se comportó así:

| Emisión | n filas | R09 WAPE | Estado WAPE | GaussEstado WAPE | Lectura |
| --- | ---: | ---: | ---: | ---: | --- |
| 2026-04-27 | 296 | 33,08% | 35,63% | 35,68% | no mejora el estado |
| 2026-05-25 | 442 | 45,67% | 33,00% | **31,70%** | mejora al estado |
| 2026-06-22 | 915 | 76,91% | 42,86% | **41,25%** | mejora al estado |
| 2026-06-29 | 962 | 68,25% | 38,42% | **36,83%** | mejora al estado |

La forma integrada mejora al challenger de estado en tres de cuatro cortes, pero no
gana de forma universal a R09 ni supera todavía la prueba de dos campañas. En desarrollo,
C2024-2025-01-20 pasó de 36,70% en R09 a 43,37% y C2025-2025-12-29 de 89,29% a
91,03%; en cambio C2025-2026-01-19 pasó de 100,65% a 52,81%. Esa variabilidad es
precisamente la razón para conservarlo como challenger y seleccionar el peso de forma
con rolling-origin, no por el último corte favorable.

La corrección de nivel cero también es explícita: si la curva Gaussiana no tiene masa en
las semanas R09 comunes, el lote conserva R09 y queda marcado sin escala Gaussiana; no se
propaga un `NaN` ni se inventan kilos. El contrato unitario cubre además la extensión H6
y la invariancia frente a cosecha posterior a la emisión.

En una emisión viva de C2026/S35 (24-ago-2026), con 808 lotes físicos válidos, la ruta
produjo 3.684 filas: 593 en H1, 459 en H2, 567 en H3, 538 en H4, 710 en H5 y 817 en
H6. Las 817 filas H6 quedaron marcadas como extendidas, no hubo P50 nulos ni reales
posteriores incorporados, y 9 lotes conservaron R09 por no tener una escala Gaussiana
identificable. Es un contrato de ejecución y trazabilidad; sin el cierre de esas semanas
no es una medición de precisión.

## Qué falta para afirmar que ayuda

El archivo de las hojas `ProySemanal_*.xlsm` no está disponible en el workspace en
este momento. Ya existe una prueba con transiciones inferidas desde H01, pero todavía
no hay etiquetas confiables de qué cambió manualmente ni una comparación de negocio
contra el libro vigente. El camino pendiente es:

1. recibir los libros manuales actuales y sus revisiones;
2. extraer las transiciones X/O/N/A/B reales de esas revisiones y unirles el contexto
   exportado con fecha estrictamente anterior; las inferidas quedan solo como
   baseline técnico;
3. congelar el peso de forma y el calibrador de escala/estado con rolling-origin de seis
   semanas, incorporando la salida vigente de Excel/manual como baseline, además de
   C2024, C2025 y C2026;
4. comparar contra Excel/manual, R09 y los candidatos actuales usando WAPE, MASE,
   sesgo, cobertura y deterioro por fundo;
5. revisar la estabilidad de las atribuciones P1/P2/P3; y
6. publicar solo si supera los gates en al menos dos campañas sin fuga temporal.

Hasta completar esa comparación con el baseline vigente, el panel de oleadas del libro y
los gates por campaña/horizonte, el resultado correcto es **challenger GaussEstado
auditable**, no “modelo ganador”.
