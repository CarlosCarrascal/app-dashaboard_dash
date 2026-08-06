# Relación entre variables y kg/ha — análisis con IA (SHAP)

**Fecha:** 2026-08-06. **Origen:** no viene de Access — sale de
`reporting.v_analitica_modulo_semana` (`db/sql/70_reporting/070_analitica_modulo_semana.sql`)
más el riego cargado el mismo día (`db/sql/10_raw/080_riego.sql` y siguientes). Responde al
Paso 3 del plan de `md_context/Estimación de Arándanos con IA.md`.

**Reporte interactivo:** `docs/modelo/relacion_variables_kg_ha_2025.html`.

---

## 1 · Qué se pidió y qué se entregó distinto

El documento original pedía un SHAP Summary Plot para **pronosticar a 1 semana** y "afirmar
con evidencia visual" una relación. Se construyó esa versión primero
(`db/tools/analisis_shap_kg_ha.py`) y **no se entregó**, porque no pasó una validación
honesta:

| Validación del pronóstico a 1 semana | MAE | R² |
|---|---|---|
| Corte temporal (entrena hasta dic-2025, valida después) | 341,0 kg/ha | **−0,331** |
| 5-fold agrupado por campaña | 554,4 kg/ha | **−0,089** |
| Nowcast sin autoregresivo, todo el histórico | 584,5 kg/ha | **−0,114** |

R² negativo en las tres formulaciones = predice peor que el promedio histórico. Se descartó.

Lo entregado es un análisis **explicativo**: qué acompaña a las semanas de alto rendimiento,
en 2025 (único año con riego medido), a nivel de módulo, sin fenología (E02-E05 solo cubren
C2026 y no son comparables entre años).

## 2 · Los dos esquemas de validación, y por qué son dos

- **(a) 5-fold aleatorio** — mide si el patrón se sostiene en semanas que no se usaron para
  ajustar. **Es la métrica con la que se elige la configuración.**
- **(b) Deja-un-módulo-fuera** — cada módulo se predice con un modelo que nunca lo vio. **Es
  la que se reporta como generalización honesta, y no interviene en ninguna decisión.** Si se
  eligiera mirándola, el número reportado quedaría inflado.

Esa separación importa: al recorrer 36 combinaciones de hiperparámetros, el R² del esquema (b)
varió entre **0,115 y 0,275**. Elegir mirando (b) habría producido un número optimista.

## 3 · Cómo se mejoró el modelo

Punto de partida y punto de llegada, ambos en el esquema difícil (b):

| Configuración | R² (a) fácil | R² (b) difícil | MAE |
|---|---|---|---|
| Baseline: predecir siempre el promedio | — | −0,014 | 642 |
| Baseline: promedio de cada módulo | 0,029 | — | 632 |
| **Versión inicial** (con `modulo_id`, prof. 4, lr 0,05) | 0,249 | **0,176** | 576 |
| Sin `modulo_id` | 0,256 | 0,212 | 537 |
| Con `log(kg/ha)` — descartado | 0,151 | 0,086 | 552 |
| Con 8 variables derivadas — descartado | 0,231 | 0,189 | 540 |
| Con las variables de lluvia | 0,305 | 0,277 | 514 |
| **Final: 14 variables, árboles simples** | **0,304** | **0,283** | **519** |

**Mejora neta en la métrica honesta: 0,176 → 0,283 (+61%)**, con el MAE bajando de 576 a
519 kg/ha.

### Lo que funcionó

- **Quitar `modulo_id`.** SHAP le daba el mayor peso de todos, y se leyó como "hay
  diferencias entre módulos que no medimos". La prueba dura lo desmiente: sacarla **mejora**
  la generalización, y el baseline de "promedio de cada módulo" da R² = 0,029. El peso era
  **memorización** del nivel de cada módulo — inservible para un módulo no visto.
- **Quitar las variables de lluvia.** `lluvia_acum_poda_mm` encabezaba el ranking con
  |SHAP| 148 aunque acumula ~24 mm en ~275 días contra ~1.200 mm de demanda ETO: en desierto
  costero es despreciable. Tenía solo 54 valores distintos, uno por fecha de poda — era una
  **huella de la cohorte de poda** disfrazada de lluvia. La decisión se tomó por el argumento
  físico; recién después se comprobó que el modelo no pierde nada (0,277 → 0,283).
- **Quitar `riego_dias_con_registro`.** Vale 7 en 463 de 471 filas; su |SHAP| fue exactamente
  0,000 — el modelo nunca la usó. Es metadato de calidad, no una variable explicativa.
- **Simplificar los árboles.** Profundidad 3 y lr 0,03 en vez de 4 y 0,05: con 471 filas, menos
  capacidad generaliza mejor.

### Lo que no funcionó (resultados negativos, documentados para no repetirlos)

- **`log(kg/ha)`** para corregir la asimetría (1,18): empeora fuerte (0,212 → 0,086).
- **8 variables derivadas** con sentido agronómico —balance hídrico (riego + lluvia − ETO),
  ritmo térmico por día, estacionalidad cíclica—: empeoran (0,212 → 0,189). Con 471 filas, más
  variables generalizan peor. **El techo no está en cómo se combinan las variables, está en
  cuántas semanas hay.**

## 4 · Hallazgos

1. **Dos de las variables que parecían más importantes eran memorización.** `modulo_id` y
   `lluvia_acum_poda_mm`, ambas detectadas con la validación dura y ambas fuera del modelo
   final. Es el argumento más fuerte a favor de validar antes de presentar: las dos habrían
   sostenido conclusiones falsas con apariencia de rigor.
2. **La edad del fruto es el factor medible de mayor peso** (±144 kg/ha), coherente con que el
   modelo de macro que Agronomía ya usa proyecte la maduración desde la fecha de poda.
3. **El clima solo discrimina entre módulos acumulado desde la poda.** Las columnas semanales
   son idénticas para los 19 módulos (una sola estación) y solo explican el momento del año.
   `gdd_acum_poda` tiene el **efecto positivo más fuerte de todo el ranking (+15,8)**.
4. **El riego pesa, pero su efecto no es lineal.** `riego_m3` (±84) y `riego_mm` (±60) tienen
   peso real y efecto *promedio* casi nulo (−0,3 y +0,4): suma en unos tramos y resta en otros.
   Y el volumen bruto está confundido con el tamaño del módulo (correlación 0,31 con área):
   **para decidir riego hay que leer la lámina, no el volumen.**

## 5 · Qué NO se puede afirmar

- **No es un pronóstico** — esa versión no validó (§1).
- **No es causal.** Generaliza a módulos y semanas no vistos, pero no autoriza "si subo el
  riego X mm, la cosecha sube Y kg".
- **El R² es modesto (~28%)**, y eso también es información: el resto es ruido de la cosecha
  por pañas y factores que hoy no se miden. Sirve para ordenar factores, no para reemplazar el
  criterio agronómico.
- **Alcance:** solo 2025; sin fenología; sin riego para M16-M18 ni Aqu Anqa 6.

## 6 · Reproducir

Tres pasos; cada uno consume la salida del anterior y ninguno recalcula lo del otro:

```
python db/tools/analisis_shap_relacion_2025.py            # entrena, valida (2 esquemas), SHAP
python db/tools/analisis_shap_relacion_2025.py --buscar    # + repite la búsqueda de 36 configs (lento)
python db/tools/preparar_reporte_shap_2025.py              # describe las entradas, formato columnar
python db/tools/generar_reporte_shap_2025.py               # ensambla el HTML
```

Requiere el entorno conda `aquanqa` (pandas, xgboost, shap, psycopg) y las credenciales de
`.env`. Los `.json`/`.csv`/`.npy` intermedios van a `data/salida/` (no versionados); la
plantilla del reporte sí está versionada: `db/tools/plantilla_reporte_shap_2025.html`.
