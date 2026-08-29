# Corrección agnóstica al horizonte — 2026-08-26

## Objetivo

Atacar el problema de volumen perdido en el forecast previo de H2–H6. El
`NowcastCierreSemanal_v1` queda fuera de esta comparación porque observa kilos
reales de lunes y martes y solo sirve para cerrar la semana.

## Implementación

Se añadió al screening candidate-only una corrección residual de amplitud con
estas reglas:

- H1 conserva `HibridoOcurrenciaOnline_v2` aprobado.
- H2–H6 parten de `MacroLegacy_v1` multihorizonte.
- Las configuraciones pueden aprender un factor global o por fundo.
- `por_horizonte=False` permite compartir errores de H2–H6 ya cerrados para
  estabilizar el aprendizaje cuando cada horizonte tiene pocas semanas.
- Solo entran resultados cuyo domingo de cierre es anterior a la emisión.
- El candidato conserva el mismo universo, no usa R09, Excel, clima futuro ni
  nowcast, y no persiste ni publica.

También se corrigió el lector del replay para usar los replays
multihorizonte por campaña (`C2024=71`, `C2025=72`, `C2026=73`) y la release H1
aprobada correspondiente (`C2024=76`, `C2025=78`, `C2026=76`).

## Resultado

El replay no demuestra una mejora de H2–H6:

| Campaña | Macro H2–H6 | Candidato H2–H6 | Decisión |
|---|---:|---:|---|
| C2026 | 26,72 % | 26,96 % | Descartado |
| C2025 | 258,12 % | 258,12 % | Descartado |

En C2026, H2, H3, H5 y H6 conservaron la Macro; H4 empeoró 1,22 puntos
porcentuales. Por tanto, no se fuerza una corrección para aparentar mejora.

## Estado

`ForecastResidualAsOfHorizonteAgnostico_v1` queda como experimento descartado,
candidate-only y sin release. Las releases operativas e históricas aprobadas no
se modifican.

Archivos principales:

- `packages/analitica/proyeccion/pronostico_horizonte.py`
- `packages/analitica/scripts/loop_forecast_horizontes.py`
- `packages/analitica/tests/test_pronostico_horizonte.py`
