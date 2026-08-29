# HibridoParametrosAsOf_v1 — estado de implementación

> **Estado supersedido:** las corridas 81–83 fueron posteriormente auditadas como
> experimentales no comparables, quedaron rechazadas e inactivas y no alimentan el dashboard.
> El estado certificado vigente está en
> `docs/seguimiento/14_restauracion_replay_y_preflight_2026-08-25.md`.

Fecha: 2026-08-25
Estado: challenger experimental; `ModeloOperativoActual_v1` continúa como modelo operativo.

## Qué se implementó

`HibridoParametrosAsOf_v1` conserva la estructura del proceso ProySemanal:

```text
parámetros X/O/N/A/B → tres oleadas → peso por oleada →
calibración as-of → corrección residual limitada → kg
```

La identidad de cada predicción es:

```text
kg = plantas × frutos_por_planta × peso_baya_g / 1000
```

La réplica ahora conserva `A1/B1`, `A2/B2` y `A3/B3`. Si un snapshot antiguo solo tiene `A1/B1`, las otras oleadas usan explícitamente ese valor como compatibilidad histórica.

La calibración no usa R09 como predictor. Para cada emisión solo utiliza datos anteriores al corte y aplica jerarquía de lote, módulo, fundo/variedad y prior legacy. La mezcla Macro/residual se selecciona por banda de horizonte con validación histórica y shrinkage; no se fuerza 50/50.

## Fuentes Excel

La ingestión lee solamente los libros base de `ProyeccionSemanal_NN`. Las variantes `EDI`, `v2`, `v3`, `oli`, copias y sufijos equivalentes quedan fuera salvo promoción explícita. Cada libro seleccionado conserva nombre, semana, fundo, variante y SHA-256. Los faltantes se registran como `sin_datos`, nunca como cero.

## GDD

Se evalúan bases `0`, `4,4`, `7` y `8 °C` y ventanas de `7`, `14`, `21` y `28` días sin leer temperaturas posteriores a la emisión. GDD solo se aplica como desplazamiento fenológico por fila cuando un holdout temporal demuestra una mejora mínima del 5 % frente a la curva sin desplazar; si no, queda registrado como candidato sin efecto sobre p50. Esto evita declarar una mejora que el motor aún no demuestra.

## Validación ejecutada

Comando de dry-run de C2026:

```text
python -m analitica.scripts.persistir_hibrido_parametros_asof \
  --campania C2026 --max-cortes 1 --horizonte-semanas 10 \
  --excel-root C:\\Users\\CCARRASCAL\\Downloads\\Proyecciones --dry-run
```

Resultado:

- 1 emisión evaluable;
- 8.170 filas para `MacroLegacy_v1`;
- 8.170 filas para `HibridoOcurrenciaOnline_v2`;
- 8.170 filas para `HibridoParametrosAsOf_v1`;
- 2.508 filas de `R09_publicado` en el horizonte publicado;
- 2.400 filas Naive y 1.009 SeasonalNaive;
- 12.893 filas de parámetros Excel cargadas;
- 62 libros base incluidos en el manifiesto;
- 34 combinaciones emisión/fundo marcadas como faltantes;
- cero advertencias de calidad en la corrida;
- 817 snapshots de parámetros generados en memoria.

Las comparaciones entre modelos se calculan mediante intersección exacta por campaña, lote, emisión y semana objetivo. La cobertura de R09 se reporta aparte porque R09 no publica necesariamente la misma cantidad de lotes y semanas que la curva reconstruida.

Pruebas:

- suite analítica: `142 passed`, 2 advertencias de convergencia MixedLM existentes;
- pruebas focales del challenger, ocurrencia, paridad y no fuga: `20 passed`;
- dry-run reproducible: completado sin advertencias.

Durante el primer replay completo se detectó y corrigió un defecto real: el panel
de ocurrencia incluía semanas futuras con `real_kg = NULL` dentro del entrenamiento
del clasificador. El modelo ahora excluye esas filas de las etiquetas de entrenamiento
y conserva esas semanas únicamente como prueba futura. Se añadió una prueba de
regresión para impedir que vuelva a ocurrir.

## Persistencia y publicación

La migración crea `analytics.legacy_parameter_snapshot`, con prior, correcciones,
parámetros finales, GDD, fecha de corte y fuente. La migración fue aplicada en
PostgreSQL.

## Replay completo C2026

Se ejecutó y persistió la corrida `run_id = 81` con estado `succeeded`:

- 22 emisiones históricas;
- 595.086 predicciones;
- 17.974 snapshots de parámetros;
- 15 métricas y 20 comparaciones;
- seis series en el mismo replay: R09 publicado, MacroLegacy, HibridoOcurrenciaOnline_v2,
  HibridoParametrosAsOf_v1, Naive y SeasonalNaive;
- cero advertencias de calidad.

La persistencia fue verificada directamente en PostgreSQL: cada una de las tres
series principales tiene 179.740 filas y los 17.974 snapshots pertenecen al mismo
`run_id`.

Resultado de aceptación para C2026: **no promover** `HibridoParametrosAsOf_v1`.
En la corrida completa, sus métricas por banda fueron:

| Modelo | WAPE operativo | WAPE planificación | WAPE escenario | MASE operativo |
|---|---:|---:|---:|---:|
| R09 publicado | 41,6 % | 51,2 % | no comparable | 0,610 |
| MacroLegacy_v1 | 166,4 % | 186,5 % | 166,6 % | 0,669 |
| HibridoParametrosAsOf_v1 | 182,3 % | 179,7 % | 177,9 % | 0,733 |
| HibridoOcurrenciaOnline_v2 | 146,9 % | 143,1 % | 128,1 % | 0,661 |

El nuevo modelo no supera a R09 ni mejora de forma consistente a la MacroLegacy.
La corrida queda como evidencia experimental para seguir ajustando la calibración;
no se maquilla como mejora y `ModeloOperativoActual_v1` continúa siendo el modelo
visible para operación. R09 se mantiene como emisión publicada de referencia, no
como algoritmo.

## Replays históricos completados

También se ejecutaron las campañas externas requeridas, cada una en un `run_id`
separado y con el mismo conjunto de modelos:

| Campaña | Run | Emisiones evaluables | Predicciones | Snapshots |
|---|---:|---:|---:|---:|
| C2024 | 83 | 13 | 181.984 | 5.928 |
| C2025 | 82 | 9 | 206.249 | 6.390 |
| C2026 | 81 | 22 | 595.086 | 17.974 |

Los replays terminaron con estado `succeeded`, sin advertencias de calidad y sin
mezclar campañas. Las métricas se guardaron por horizonte y por campaña.

El resultado transversal mantiene bloqueada la promoción. `HibridoParametrosAsOf_v1`
no gana de forma consistente a `HibridoOcurrenciaOnline_v2`, `MacroLegacy_v1` ni
a R09 publicado. En particular, sus WAPE operativos fueron:

| Campaña | HPA v1 | Ocurrencia v2 | R09 publicado |
|---|---:|---:|---:|
| C2024 | 695,2 % | 357,5 % | 48,6 % |
| C2025 | 686,5 % | 350,5 % | 72,4 % |
| C2026 | 182,3 % | 146,9 % | 41,6 % |

Estos porcentajes altos no se ocultan: muestran que el ajuste as-of de parámetros
Excel está sobreestimando volumen en este universo. La estructura Excel quedó
reconstruida y reproducible, pero su calibración automática todavía no es una
mejora predictiva. El modelo operativo visible permanece sin cambios.

Por tanto, el estado final del plan es:

```text
ModeloOperativoActual_v1: operativo
R09_publicado: referencia operativa publicada
HibridoOcurrenciaOnline_v2: challenger experimental anterior
HibridoParametrosAsOf_v1: challenger experimental, no promovido
```

La siguiente mejora debe atacar la sobreestimación de los parámetros ajustados —y
separar cobertura, volumen y sesgo por nivel de calibración— antes de añadir más
variables climáticas o cambiar el modelo visible.

## Lectura histórica en el dashboard

La vista `reporting.curva_historica_modelos` y las consultas de servicios fueron
corregidas para seleccionar la última corrida exitosa **por campaña**, no una única
corrida global. Por ello, el histórico puede mostrar simultáneamente C2024, C2025 y
C2026, cada una con su propio replay y sin sumar corridas entre campañas. La operación
diaria continúa leyendo su corrida publicada/operativa independiente; esta corrección
solo afecta la comparación histórica y sus métricas.

Verificación posterior a la corrección:

- curva histórica: 467 filas agregadas;
- campañas disponibles en replay: C2024, C2025 y C2026;
- métricas cargadas: 42 filas, correspondientes a las tres campañas;
- pruebas de dashboard focales: `73 passed`.
