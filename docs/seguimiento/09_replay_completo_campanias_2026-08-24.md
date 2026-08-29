# Replay completo por campaña — 2026-08-24

## Resultado

Se persistieron tres corridas independientes desde el mismo snapshot PostgreSQL (`snapshot_id=40`):

| Campaña | Run | Emisiones R09 | Cortes evaluables | R09 | MacroLegacy | Híbrido |
|---|---:|---:|---:|---:|---:|---:|
| C2024 | 71 | 15 | 15 | 2.123 | 68.400 | 68.400 |
| C2025 | 72 | 11 | 11 | 6.467 | 78.100 | 78.100 |
| C2026 | 73 | 24 | 22 | 30.180 | 179.740 | 179.740 |

`R09_publicado` es la emisión histórica publicada por el equipo; no se trata como
algoritmo. `MacroLegacy_v1` reconstruye la curva de tres oleadas y peso; el challenger
es `HibridoLegacyResidual_v1`.

## Reglas de la corrida

- Cada campaña se filtró antes de calibrar.
- Cada corte usa únicamente cosecha anterior a `fecha_emision`.
- La cosecha real se unió después de generar la predicción.
- Cada predicción conserva emisión, objetivo, horizonte, campaña, lote, versión y
  `es_replay_ciego=true`.
- Se rechazaron duplicados en la clave
  `modelo × campaña × lote × emisión × objetivo × versión_fuente`.
- PostgreSQL fue la fuente; no se abrió Excel durante el replay.
- C2026 tiene 24 emisiones R09, pero solo 22 cortes con objetivos reales evaluables.
  Las dos restantes no se inventaron ni se rellenaron con cero.
- C2022 y C2023 no se añadieron a este torneo porque el snapshot no tiene una serie
  R09 versionada comparable para esas campañas.

## Optimización aplicada

1. `MacroLegacy` e `HibridoLegacy` comparten la caché de parámetros as-of dentro de la
   misma campaña; el híbrido no recalibra de nuevo los mismos lote-corte.
2. La calibración reutiliza el óptimo del corte anterior como punto inicial.
3. Si un lote no tiene observaciones as-of, se usa directamente el prior explícito en
   vez de ejecutar una optimización vacía.
4. La persistencia usa `COPY ... FORMAT CSV` por bloques, en vez de adaptar una fila
   individual con `write_row`.
5. Se eliminaron warnings del corrector residual ocasionados por features que estaban
   presentes en el panel pero completamente ausentes en el subconjunto de entrenamiento
   del componente correspondiente.

Tiempos observados de generación: C2024 156,1 s Macro + 36,7 s Híbrido; C2025 201,2 s
Macro + 39,8 s Híbrido; C2026 261,5 s Macro + 102,5 s Híbrido. El dashboard no ejecuta
estas calibraciones: lee las corridas persistidas.

## Lectura objetiva

Las corridas quedan disponibles para el histórico, pero no promocionan el híbrido.
En el universo pareado contra R09, el WAPE operativo del híbrido fue aproximadamente:

- C2024: 99,9%.
- C2025: 103,4%.
- C2026: 138,6%.

Son resultados de replay ciego y no una afirmación de causalidad. R09 continúa siendo
la referencia operativa mientras no exista una mejora demostrada fuera de muestra.

## Reproducción

```powershell
$env:PYTHONPATH='packages'
& 'C:\Users\CCARRASCAL\miniconda3\envs\aquanqa\python.exe' `
  -m analitica.scripts.persistir_replay_campania `
  --campania C2024 --horizonte-semanas 10 --max-cortes 0
```

Cambiar únicamente `C2024` por `C2025` o `C2026`. El script crea un `forecast_run`
separado y finaliza en `succeeded` solo después de persistir predicciones, métricas,
comparación pareada y controles de calidad.
