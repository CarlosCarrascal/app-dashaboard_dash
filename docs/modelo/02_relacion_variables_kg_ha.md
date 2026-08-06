# Relación entre variables y kg/ha — primer intento con IA (SHAP)

**Fecha:** 2026-08-06. **Origen:** `docs/historico-access` no aplica aquí — este análisis
no viene de Access, viene de `reporting.v_analitica_modulo_semana` (ver
`db/sql/70_reporting/070_analitica_modulo_semana.sql`) más el riego cargado el mismo día
(`db/sql/10_raw/080_riego.sql` y siguientes). Responde al plan de
`docs/historico-access/../../md_context/Estimación de Arándanos con IA.md`, Paso 3.

## Qué se pidió y qué se entregó distinto

El documento original pedía un SHAP Summary Plot para **pronosticar a 1 semana** y
"afirmar con evidencia visual" una relación. Se construyó esa versión primero
(`db/tools/analisis_shap_kg_ha.py`) y **no se entregó** porque no pasó una validación
honesta:

| Validación | MAE | R² |
|---|---|---|
| Corte temporal (entrena hasta dic-2025, valida después) | 341,0 kg/ha | **−0,331** |
| 5-fold agrupado por campaña | 554,4 kg/ha | **−0,089** |
| Nowcast sin autoregresivo (misma semana, todo el histórico) | 584,5 kg/ha | **−0,114** |

R² negativo en las tres formulaciones significa que el modelo predice peor que el
promedio histórico. Mostrar el ranking de esa versión como "prueba matemática" habría
sido el mismo tipo de defecto que esta migración lleva corrigiendo desde la auditoría de
Access: un resultado que se ve convincente pero no sobrevive verificación.

## Lo que sí se entregó

Alcance acordado con el usuario: **explicar** la relación (no pronosticar), **solo 2025**
(único año con riego real cargado — ver `core.riego_semanal`), **a nivel de módulo**, sin
fenología (E02-E05 solo existen para C2026, no comparable entre años).

`db/tools/analisis_shap_relacion_2025.py` — XGBoost + SHAP sobre 471 filas (19 módulos ×
semanas ISO de 2025), explicando `kg_ha` de la misma semana:

| Validación | MAE | R² |
|---|---|---|
| 5-fold aleatorio | 514,2 kg/ha | **0,259** |
| Deja-un-módulo-fuera (generaliza a un módulo nunca visto) | 579,6 kg/ha | **0,157** |

Positivo en las dos, incluida la prueba más dura (módulo nunca visto). Es una relación
descriptiva modesta pero real, no una casualidad de un solo corte.

**Reporte completo, interactivo:** `docs/modelo/relacion_variables_kg_ha_2025.html`. Además
del ranking, incluye: las 4 fuentes de datos y su rol, estadística descriptiva (media,
percentiles, cobertura) de las 17 variables agrupadas por categoría, una muestra de 10 filas
reales tal como entraron al modelo, la metodología explicada paso a paso, y — la pieza nueva
— un gráfico de dependencia real (valor de la variable × contribución SHAP, punto por punto,
471 semanas) para cada una de las 6 variables de mayor peso, no solo su promedio.

## Los cuatro hallazgos que importan del ranking

1. **`riego_mm` (lámina) se asocia con más kg/ha; `riego_m3` (volumen bruto) con menos.**
   No es una contradicción: `riego_m3` está confundido con el tamaño del módulo (un
   módulo grande usa más m³ sin regar más intensamente por hectárea), mientras que
   `riego_mm` ya normaliza por área. Para leer el efecto del riego, usar `riego_mm`.
2. **`edad_dias` (días desde poda) es la variable agronómica con más peso** — coherente
   con que el propio modelo de macro que usa Agronomía hoy se basa en el tiempo desde la
   poda para proyectar maduración.
3. **`modulo_id` (identidad del módulo) pesa más que casi todo lo demás.** Significa que
   hay diferencias reales entre módulos —suelo, microclima, historia del lote— que
   ninguna de las variables medidas explica. No es una variable "accionable"; es la
   señal de que falta algo por capturar si se quiere explicar más que este 26%/16% de R².
4. **El clima solo sirve acumulado desde la poda de cada módulo, no como promedio semanal.**
   Las columnas de clima *semanal* (`temp_media`, `eto_semana_mm`...) son idénticas para
   los 19 módulos la misma semana — no pueden explicar diferencias entre módulos. Acumuladas
   desde la poda de cada uno (`gdd_acum_poda`, `eto_acum_poda_mm`), la misma estación única
   sí discrimina, y aparecen entre las variables de mayor peso.

## Qué no se puede afirmar con esto

- No es un modelo de pronóstico: la versión que intentaba predecir la semana siguiente
  no validó y se descartó (arriba).
- No es causal: es una relación estadística validada por generalización, no un
  experimento controlado.
- No cubre riego para M16-M18 ni Aqu Anqa 6 (sin fuente), ni ningún año fuera de 2025.

## Reproducir

Tres pasos, cada uno consume lo que escribió el anterior — ninguno vuelve a calcular lo
que ya calculó otro:

```
python db/tools/analisis_shap_relacion_2025.py     # entrena, valida (2 esquemas), SHAP
python db/tools/preparar_reporte_shap_2025.py       # describe los datos de entrada
python db/tools/generar_reporte_shap_2025.py        # ensambla el HTML final
```

Requiere el entorno `aquanqa` (pandas, xgboost, shap, psycopg) y las credenciales de
`.env`. Los `.json`/`.csv`/`.npy` intermedios se escriben en `data/salida/` (no
versionados); la plantilla del HTML sí está versionada:
`db/tools/plantilla_reporte_shap_2025.html`.
