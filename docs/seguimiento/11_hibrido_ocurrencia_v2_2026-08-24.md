# HibridoOcurrenciaOnline_v2 — resultado validado

## Estado

- Corrida analítica: `run_id = 76`.
- Estado de corrida: `succeeded`.
- Campañas incluidas: C2024, C2025 y C2026; C2025 es una ventana parcial.
- Filas persistidas: 146.105 predicciones.
- Filas por serie: 29.221.
- Estado de gobierno: `challenger`, no promovido.

## Qué se implementó

La versión v2 conserva la estructura agronómica de `MacroLegacy_v1` y aplica una corrección
online calculada solamente con semanas cerradas anteriores. El calentamiento deja de borrar
lotes: si todavía no existe evidencia para corregir, conserva la predicción legacy y registra
el estado de la corrección.

La evaluación persiste en la misma rejilla:

```text
campaña × lote × semana objetivo × modelo
```

para R09 publicado, MacroLegacy, Ocurrencia v1, Ocurrencia v2 y Naive. R09 es una salida
publicada de referencia y nunca entra como feature.

## Resultado C2026

| Serie | WAPE semanal | MASE | Sesgo | Cobertura volumen |
|---|---:|---:|---:|---:|
| R09 publicado | 21,23 % | 0,780 | +5,57 % | 80,92 % |
| MacroLegacy_v1 | 25,60 % | 0,941 | −10,11 % | 100,00 % |
| Ocurrencia v1 | 21,08 % | 0,775 | −4,92 % | 97,24 % |
| Ocurrencia v2 | **20,00 %** | **0,735** | **−3,28 %** | **100,00 %** |
| Naive lag-1 | 26,36 % | 0,969 | — | 100,00 % |

La mejora frente a R09 en WAPE semanal C2026 es aproximadamente 5,8 % relativa. El objetivo
de 15 % no se alcanzó.

## Qué ocurrió en C2025

C2025 no fue evaluada como campaña completa en `run_id = 76`. La rejilla disponible para
las cinco series empieza el 05/01/2026 y termina el 23/02/2026: ocho semanas y 924.162 kg
reales. Sin embargo, H01 contiene 15.654.825 kg de C2025 desde el 14/03/2025 hasta el
05/03/2026. Faltan en esa rejilla las semanas de marzo a diciembre de 2025 y la última
semana parcial de marzo de 2026.

Dentro del tramo que sí se comparó, v2 proyectó 1.650.001 kg frente a 924.162 kg reales:
sesgo agregado de +78,54 % y WAPE semanal de 96,87 %. El exceso se concentra en:

- `Aqu Anqa 2`/Quri: 665.758 kg proyectados frente a 120.664 kg reales;
- `Aqu Anqa 1`/Arena: 260.670 kg frente a 111.163 kg;
- `Aqu Anqa 4`/Ayllu: 410.011 kg frente a 327.871 kg;
- `Aqu Anqa 5`/Kawsay II: 66.206 kg frente a 1.613 kg.

`Aqu Anqa 3`/Kawsay fue el único fundo claramente subestimado: 247.356 kg frente a
362.851 kg. Por tanto, no fue un error único de toda la campaña: hubo una combinación de
colas legacy que continuaron después del último real de algunos fundos y subestimación en
otro fundo.

Además, las primeras cinco semanas de v2 son `calentamiento_base`: la versión conserva
MacroLegacy sin aplicar corrección online. Solo quedan tres semanas para aprender, demasiado
pocas para corregir una curva que ya venía mal escalada. Esto explica por qué v2 mejora la
cobertura, pero hereda el exceso de Quri/Arena/Ayllu y no alcanza a corregirlo.

## Por qué no se promovió

- C2024 mejora ligeramente WAPE, pero el sesgo de +12,54 % excede el gate de 10 %.
- En la ventana parcial de C2025 empeora fuertemente: WAPE 96,87 % frente a 40,84 % de R09.
- No hay mejora demostrada en dos campañas externas.
- El WAPE lote-semana C2026 permanece en 80,27 %, aunque el agregado semanal sea 20,00 %.

Conclusión obligatoria:

> Sin mejora estadísticamente comprobada entre campañas. R09 continúa como referencia
> operativa y HibridoOcurrenciaOnline_v2 permanece como challenger.

## Semántica de cobertura

- `WAPE operacional`: incluye toda la rejilla evaluable y penaliza una predicción ausente.
- `WAPE condicionado`: evalúa únicamente filas donde el modelo emitió predicción.
- `cobertura de lotes`: proporción de lote-semana con emisión.
- `cobertura de volumen`: proporción de kg reales representados por esas emisiones.

En v2 la cobertura es 100 % porque durante el calentamiento se conserva MacroLegacy en lugar
de eliminar filas. Esto no significa que la precisión lote-semana sea buena.

## Variables agronómicas no promovidas

GDD, clima, riego y fenología siguen en el catálogo científico, pero no entraron a esta
versión. Las pruebas actuales no demostraron mejora fuera de muestra. Incorporarlas sin esa
prueba habría convertido plausibilidad agronómica en un coeficiente no validado.

## Verificación

- Suite analítica: 129 pruebas aprobadas.
- Suite de Proyección del dashboard: 25 pruebas aprobadas.
- Inspección visual: selector v2 por defecto, métricas de cobertura visibles y consola sin
  errores.
- La semana parcial C2026 17–23/08 queda fuera de las métricas cerradas.

## Próximo trabajo útil

La siguiente mejora no debe ser otro algoritmo general. Primero hay que reconstruir la rejilla
completa de C2025 con emisiones y semanas de marzo–diciembre de 2025; después investigar el
fallo por fundo, nivel de calibración y horizonte. Solo entonces conviene volver a probar GDD
o variables fenológicas dentro de folds temporales.
