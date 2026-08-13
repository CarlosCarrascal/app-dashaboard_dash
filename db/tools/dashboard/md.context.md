# Contexto del Dashboard — Impacto agronómico y aporte predictivo

> **Proyecto:** `aquanqa-data-platform`  
> **Ruta:** `db/tools/dashboard/`  
> **Actualizado:** 2026-08-10  
> **Estado git:** branch `cierre-nulos-y-reestructura` — el directorio `db/tools/dashboard/` es **untracked** (aún no commiteado).

---

## 1. Propósito y límites del tablero

El tablero separa **asociación estadística**, **aporte predictivo** y **efecto agronómico estimado** entre clima, riego y rendimiento en arándano. Con la campaña 2025 implementa las dos primeras; la tercera queda pendiente de poda, fases y replicación.

### Lo que SÍ hace
- Mide la fuerza de asociación entre clima/riego y rendimiento con métricas honestas.
- Explica un modelo XGBoost con SHAP, sin llamar causal a ese reparto.
- Muestra las pruebas que sostienen **o desmienten** cada asociación.
- Exporta todo a Excel reproducible y autoexplicado.

### Lo que NO hace
- **No es un pronóstico operativo.** Evalúa capacidad predictiva fuera de muestra.
- No establece causalidad (son datos observacionales).
- No ejecuta DML hasta definir tratamiento, confusores, solapamiento y fases.
- No explica diferencias **entre módulos de la misma semana** (el clima es idéntico para todos los módulos en una semana dada).

---

## 2. Estado git al 2026-08-07

### Branch activo
```
cierre-nulos-y-reestructura
```

### Historial relevante (últimos commits)
| Hash | Mensaje |
|------|---------|
| `c5be853` | Mejorar el modelo (R² 0,176→0,283) y rediseñar la UI del reporte |
| `93b5f9f` | Rediseñar el reporte de relación de variables: entradas, metodología y dependencia |
| `db8b8f9` | Primer análisis de relación de variables con kg/ha (SHAP), Paso 3 del plan de IA |
| `519226c` | Cargar el riego real (fuente externa) y corregir M01 duplicado en el panel |
| `af10c0c` | Panel analítico módulo × semana, para relacionar variables con el kg/ha |
| `02534fa` | Reestructurar el monorepo: un solo lenguaje de backend (ADR-0006) |

### Archivos con cambios pendientes (no commiteados)
**Eliminados** (scripts de análisis ad-hoc, reemplazados por el dashboard):
- `db/tools/analisis_shap_kg_ha.py`
- `db/tools/analisis_shap_relacion_2025.py`
- `db/tools/cargar_riego.py`
- `db/tools/exportar_panel_excel.py`
- `db/tools/generar_reporte_shap_2025.py`
- `db/tools/plantilla_reporte_shap_2025.html`
- `db/tools/preparar_reporte_shap_2025.py`

**Modificados:**
- `package.json` — agrega `"dashboard": "node scripts/run.mjs dashboard"`
- `scripts/run.mjs` — agrega `cmdDashboard()`, registra `db/tools` en `PAQUETES_PYTHON`

**Untracked (nuevos, sin commitear):**
- `db/tools/dashboard/` ← **todo el tablero**
- `db/tools/pyproject.toml`
- `docs/data/` (contiene `IA.final.xlsx`)
- `docs/modelo/03_relacion_clima_riego_kgha_2025.md`

> **Acción pendiente:** el commit que consolida el dashboard y elimina los scripts viejos.

---

## 3. Cómo se lanza

```bash
# Lanzar el tablero (detecta el Python de conda automáticamente)
npm run dashboard

# Lanzar restringido a localhost
npm run dashboard -- --server.address=localhost

# Directo, sin npm
streamlit run db/tools/dashboard/app.py

# Apuntar a otro Excel sin tocar el código
AQUANQA_XLSX=ruta/al/archivo.xlsx npm run dashboard
```

**Instalar dependencias:**
```bash
npm run setup          # instala todos los paquetes del monorepo, incluido db/tools
# o manualmente:
pip install -e db/tools
```

---

## 4. Arquitectura del código

### Principio central
**Dependencia unidireccional estricta:** `vistas/` → `servicios/` → `nucleo/` → `config.py`

`nucleo/` **no importa Streamlit ni Plotly**: es cálculo puro, testeable sin levantar la app.
`verificar_capas.py` comprueba esta regla automáticamente.

```
db/tools/dashboard/
│
├── app.py                  Punto de entrada: menú lateral, cabecera, despacho de vistas
├── config.py               Constantes globales: features, etiquetas, glosario, params XGBoost, paleta, secciones
├── estilo.py               CSS inyectado vía st.markdown(); solo espaciado y tipografía
├── datos_origen.py         Control de selección del Excel (repo o upload)
├── verificar_capas.py      Comprueba la regla de dependencias en tiempo de ejecución
│
├── nucleo/                 Cálculo puro — sin Streamlit ni Plotly
│   ├── datos.py            Excel → Panel (Fundo×Módulo×Semana) + hallazgos de calidad
│   ├── clima.py            Estudio estadístico: correlación, control, rezagos, placebo, por módulo
│   ├── modelo.py           Ajuste XGBoost + SHAP (el modelo que se EXPLICA)
│   ├── evaluacion.py       Conjuntos, particiones, referencias, plan de validación (el modelo que se VALIDA)
│   ├── exportar.py         Motor de formato del .xlsx (xlsxwriter)
│   └── informe.py          Qué hojas lleva el .xlsx y cómo se explican
│
├── servicios/
│   └── cache.py            Envuelve nucleo/ en @st.cache_data / @st.cache_resource
│
└── vistas/                 12 módulos de UI, uno por sección
    ├── resumen.py
    ├── correlaciones.py
    ├── importancia.py
    ├── por_modulo.py
    ├── auditoria.py
    ├── clima.py
    ├── graficos.py
    ├── modelo.py
    ├── validacion.py
    ├── panel_consolidado.py
    └── comun.py
```

---

## 5. Datos de entrada

### Archivo fuente
`docs/data/IA.final.xlsx` (o el archivo que indique `AQUANQA_XLSX`)

### Hojas requeridas
| Hoja | Contenido |
|------|-----------|
| `KgHa` | Fundo, Módulo, Semana, Área (ha), Kilogramos cosechados |
| `Temp Max-Min` | TempMax, TempMin, VarDia por semana |
| `Rad y ET` | RadSolc (Radiación), ET-mm (ETo) por semana |
| `Riego` | Fundo, Módulo, Semana, Lt/planta, m3/ha |
| `DPV` | DPV (kPa) por semana |

### Panel resultante
- Grano: **Fundo × Módulo × Semana**
- ~452 filas (18 módulos × ~50 semanas con cosecha registrada)
- El clima se replica a cada módulo de la semana (es un dato del fundo, no del módulo)

---

## 6. Variables del modelo

### Features del modelo XGBoost (predictoras)

> **Alcance de las ventanas:** son ingeniería de variables predictivas sobre semanas calendario. No equivalen a fases biológicas. La codificación agronómica correcta requiere fecha de poda, días desde poda y fase por módulo.

| Columna en el panel | Etiqueta en la UI | Desfase | Cómo se calcula |
|---------------------|-------------------|---------|------------------|
| `DPV_lag` | DPV prom. móvil (kPa) | **7 semanas por defecto** | Ventana semanal completa, configurable de 1 a 8 |
| `riego_lag` | Riego prom. móvil (L/planta) | **1 semana por defecto** | Ventana por módulo, configurable de 1 a 8 |
| `Rad_lag` | Radiación prom. móvil | **7 semanas por defecto** | Ventana semanal completa, configurable de 1 a 8 |
| `ETo_lag` | ETo prom. móvil (mm) | **7 semanas por defecto** | Ventana semanal completa, configurable de 1 a 8 |
| `gdd_lag` | GDD prom. móvil (°C·día) | **7 semanas por defecto** | Ventana semanal completa, configurable de 1 a 8 |
| `TempMax` | Temp. máxima (°C) | **Lag 0** | Valor puntual de la semana de cosecha |
| `TempMin` | Temp. mínima (°C) | **Lag 0** | Valor puntual de la semana de cosecha |

### Variables originales (panel e impacto agronómico)
Las columnas `DPV`, `Rad`, `ETo`, `riego_lt_planta` **se conservan en el panel** (no se reemplazan) para el análisis observacional. Solo las versiones `_lag` entran al modelo XGBoost.

### Objetivo
- `KgHa` — Rendimiento (kg cosechados / ha), ponderado por área cuando hay varias filas por celda.

### Variables climáticas adicionales (para el estudio, no como features del modelo)
`TempMin`, `TempMax`, `VarDia`, `gdd_semana`, `gdd_acum`, `Rad`, `ETo`, `DPV`

### GDD (Grados-día de crecimiento)
- Temperatura base: **4,4 °C** (referencia estándar para arándano)
- `gdd_semana = 7 × max(0, (TempMax + TempMin)/2 − 4.4)`
- `gdd_acum` = suma acumulada desde la primera semana del año

---

## 7. Hallazgos de calidad de datos (automáticos)

`nucleo/datos.py` detecta y registra hallazgos al armar el panel:

| Clave | Gravedad | Descripción |
|-------|----------|-------------|
| `riego_agregacion_inconsistente` | **alta** | `m3/ha` viene sumada por turnos; `Lt/planta` promediada → magnitudes incomparables. El análisis usa solo `Lt/planta` |
| `riego_implausible` | **alta** | La lámina declarada no cae en el rango físicamente plausible (0,3–1,5 × ETo) ni como dato diario ni semanal |
| `cosecha_sin_riego` | media | Celdas con cosecha sin fila de riego → se descartan |
| `riego_cero` | media | Semanas con riego exactamente 0 (no se puede distinguir parada real de dato faltante) |
| `clima_semanal` | media | El clima se repite ~9,0 veces por semana; n efectivo = 50 semanas, no 452 celdas |
| `modulos_sufijados` | baja | M10A y M10B se fusionan en M10 (el riego no los distingue) |
| `cosecha_duplicada` | baja | Filas repetidas de cosecha: se consolidan sumando kilos y área |
| `riego_por_turno` | baja | El riego viene a nivel de turno → se promedia a módulo |
| `riego_diario` | baja | El riego viene por día, no por semana → se multiplica × 7 |
| `riego_coherente` | baja | (informativo) Las dos columnas de riego son coherentes entre sí |

> Los hallazgos de gravedad **alta** se muestran en rojo en el sidebar y en «Datos y calidad».

---

## 8. El modelo XGBoost

### Separación de roles
- **`nucleo/modelo.py` → el modelo que se EXPLICA:** entrenado sobre todo el panel, produce SHAP para importancia global y auditoría por celda.
- **`nucleo/evaluacion.py` → el modelo que se VALIDA:** reentrena por partición (nunca ve los datos de test), mide R² y MAE honestos.

### Hiperparámetros (seleccionados por barrido de 108 combinaciones, 2026-08-07)
```python
PARAMS = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.01,
    "min_child_weight": 10,   # ninguna hoja con menos de 10 observaciones
    "reg_lambda": 5,           # regularización L2
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 0,
    "n_jobs": 1,               # intencional: con 452 filas el paralelismo cuesta más de lo que ahorra
}
```

### Métricas de selección (promedio de 8 semillas)
| Esquema | R² selección | R² honesto | MAE |
|---------|-------------|------------|-----|
| Config anterior (prof 3, lr 0,03) | +0,344 | −0,116 | 757 kg/ha |
| **Config actual** | **+0,402** | **+0,053** | **686 kg/ha** |
| Baseline «predecir la media» | — | −0,147 | 756 kg/ha |

> La config anterior tenía el MAE del baseline: no medía nada útil. La mejora es robusta (5,1 σ de margen entre semillas).

---

## 9. Estudio estadístico del clima (`nucleo/clima.py`)

Cinco preguntas encadenadas, en el orden que tiene sentido hacérselas:

### 9.1 Correlación cruda
- Pearson y Spearman al grano semanal (n = 50 semanas).
- Intervalo de confianza vía transformación z de Fisher sobre n semanas (no sobre las 452 celdas).

### 9.2 Control del calendario (correlación parcial)
- Polinomio de grado **5** sobre el número de semana absorbe la forma de la campaña.
- Un control lineal no es suficiente: la cosecha tiene forma de joroba y una recta no la describe.
- Una variable "sobrevive" si p < 0,05 tras el control no lineal.

### 9.3 Rezagos
- Se prueban de 0 a 8 semanas.
- Solo la versión **sin tendencia** es interpretable: el rezago bruto sube la correlación por alineación de curvas estacionales, no por física.

### 9.4 Placebo
- Se contrasta contra series inventadas: onda anual (seno), onda anual (coseno), rampa lineal, ruido aleatorio puro.
- Resultado conocido: `onda anual (seno)` correlaciona r = −0,918 con kg/ha, más que `TempMin` (r = −0,706). Lo que se mide es la forma estacional, no la temperatura.

### 9.5 Por módulo
- Correlación de cada variable climática dentro de cada módulo.
- Si el signo cambia según cuándo arranca la cosecha del módulo, la correlación mide el solapamiento de calendarios, no fisiología.

### Veredicto (objeto resumen del estudio)
```python
@dataclass(frozen=True)
class Veredicto:
    variable_mas_asociada: str
    r_mas_alta: float
    sobreviven_al_control: list[str]   # vacío = no hay relación robusta
    placebo_mas_fuerte: str
    r_placebo: float
    n_semanas: int
```

---

## 10. Plan de validación (`nucleo/evaluacion.py`)

### Las tres piezas que definen una medición
| Pieza | Qué decide |
|-------|-----------|
| `Conjunto` | Qué variables entran al modelo |
| `Partición` | Cómo se separa train/test (y qué pregunta responde) |
| `Referencia` | Un predictor sin modelo (el piso) |

### Conjuntos registrados
| Clave | Variables |
|-------|-----------|
| `completo` | Las 6 features |
| `clima` | Sin `riego_lt_planta` |
| `riego` | Solo `riego_lt_planta` |
| `calendario` | Solo `nsem` |
| `conjunto_sin(col)` | El completo menos una variable (aporte marginal) |
| `conjunto_solo(col)` | Una sola variable |

### Particiones registradas
| Clave | Nombre | Sesgo |
|-------|--------|-------|
| `aleatoria` | 5-fold aleatorio | **OPTIMISTA**: mete módulos de la misma semana en train y test |
| `por_modulo` | Deja-un-módulo-fuera | Pregunta: ¿sirve para un módulo nuevo? |
| `por_semana` | Deja-una-semana-fuera | Puede interpolar entre semanas vecinas |
| `por_bloque` | Deja-un-bloque-de-10-semanas-fuera | **HONESTA**: sin semanas vecinas en el entrenamiento |

### Plan de validación (7 pasos)
| Paso | Conjunto | Partición | Nota |
|------|----------|-----------|------|
| (a) | completo | aleatoria | Optimista |
| (b) | completo | por_modulo | ¿Módulo nuevo? |
| (c) | completo | por_semana | ¿Semana no vista? |
| (d) | completo | por_bloque | **Honesta** |
| (e) | calendario | por_semana | Referencia: solo el almanaque |
| (f) | clima | por_semana | ¿El clima aporta más que el almanaque? |
| (g) | riego | por_semana | La única variable que distingue módulos |

### Nota sobre paralelismo
`en_paralelo()` ejecuta en secuencia (no en paralelo) a propósito:
- Hilos Python: 24,4 s (el GIL y XGBoost se estorban)
- Procesos (`loky`): 10,2 s pero **aborta en Windows** por el JIT de LLVM al inicializar `shap → numba → llvmlite` en un proceso hijo
- Secuencial con `n_jobs=1`: **17,4 s** ← lo que se usa

---

## 11. Secciones del tablero (menú lateral)

| Sección | `clave` | Contenido | Tiempo (en frío) |
|---------|---------|-----------|-----------------|
| Pregunta, datos y límites | `resumen` | Objetivo, tres capas, grano y límites | ~5 s |
| Impacto agronómico | `impacto` | Asociación, calendario, rezagos, placebo, módulos, frutos y peso | 0,3 s |
| Qué explica el R² | `r2` | Techo, grupos, variables y esquemas de evaluación | a demanda |
| Modelo predictivo | `modelo` | Familias de modelo, XGBoost, ventanas y calibración | a demanda |
| Explicación del modelo | `explicacion` | SHAP global y auditoría local | 0,6 s |
| Datos y calidad | `datos` | Hallazgos, panel filtrable y exportación | 0,5 s |
| Marco metodológico y referencias | `metodologia` | Fuentes y condiciones previas a DML | 0,1 s |

> Los bloques caros (aporte marginal ~17 s, esquemas ~10 s, comparación de familias ~7 s) se calculan **a demanda**, detrás de un selector, y quedan en caché.

---

## 12. Caché

| Función | Decorador | Razón |
|---------|-----------|-------|
| `entrenar()` | `@st.cache_resource` | El modelo XGBoost pesa 376 KB; `cache_data` lo copiaría en cada acceso (~10 ms). `cache_resource` devuelve siempre la misma instancia. |
| Todo lo demás | `@st.cache_data` | Serializa y compara por valor; funciona con bytes, DataFrame y str. |
| `leer_archivo()` | `@st.cache_data` con `_mtime` | Si el archivo cambia en disco, la lectura se rehace automáticamente. |

**Regla de nombres:** los parámetros con `_` inicial no entran en la clave de caché (se usan para objetos caros ya cacheados que no son hasheables por `cache_data`).

---

## 13. Exportación a Excel

### Hojas siempre presentes
1. **Panel** — celdas del panel (respeta los filtros activos en el tablero al exportar)
2. **Resumen semanal** — una fila por semana (el grano del clima)
3. **Calidad de datos** — hallazgos detectados al leer el archivo
4. **Metodologia** — decisiones de método y por qué se resolvieron así
5. **Limitaciones** — qué NO se puede concluir
6. **Glosario** — qué significa cada variable en lenguaje llano

### Hojas opcionales (activadas con checkboxes en la sección Datos)
- `"clima"` activa: Correlaciones, Control del calendario, Rezagos, Placebo
- `"modulo"` activa: Por módulo, Signo vs ventana

---

## 14. Restricciones de diseño importantes

### N efectivo del clima
- El clima (temperatura, radiación, ETo, DPV) tiene **un valor por semana** para todos los módulos.
- El panel tiene ~452 filas pero solo ~50 mediciones independientes de clima.
- Un intervalo de confianza calculado sobre 452 filas sería **√(452/50) ≈ 3,0 veces** más estrecho de lo correcto.
- **Todas las estadísticas climáticas del tablero y del Excel exportado usan n = semanas**, no n = celdas.

### Ventanas temporales de las features del modelo

Las features `DPV`, `Rad`, `ETo` y GDD usan **7 semanas por defecto**; riego usa **1 semana**. Cada ventana es configurable de 1 a 8 semanas desde la barra lateral de las secciones del modelo.

**Alcance:** las ventanas permiten probar señal acumulada, pero no deben llamarse fases ni rezagos biológicos demostrados. Las fases reales se construirán desde poda y fenología.

**Implementación:** `nucleo/datos._agregar_lags()` rueda el clima una vez sobre su serie semanal y el riego dentro de cada `(Fundo, Módulo)`, siempre por semanas de calendario. La ventana vigente es **inclusiva**: una ventana de 7 en `t` usa `t-6 a t` y riego=1 usa `t`; son ventanas predictivas contemporáneas, no rezagos pre-cosecha puros.

**Por qué promedio móvil y no lag simple:** un pico anómalo de DPV en una sola semana puede no dañar la planta si las semanas circundantes fueron favorables. El promedio captura el "estrés sostenido" durante el desarrollo, que es un predictor más robusto.

**Ventana completa:** `min_periods=ventana`. Si faltan semanas de calendario, la fila queda en NaN y se excluye del modelo; no se mezcla una ventana parcial con una completa.

### El riego: por qué se usa `Lt/planta` y no `m3/ha`
- En el archivo de campaña 2025, `m3/ha` está **sumado** sobre los turnos de riego y `Lt/planta` está **promediado**.
- El cociente `m3/ha / Lt/planta` es constante dentro de cada módulo pero salta entre módulos en proporción al número de turnos: esa es la firma inequívoca de la diferencia de agregación.
- `m3/ha` da ~171 mm/semana contra una ETo de 29 mm/semana (casi 6× la demanda hídrica): físicamente imposible.
- El análisis usa **`riego_lt_planta`** en todas partes. `m3/ha` se conserva solo para mostrar.

### Causalidad y campaña única
- El análisis es **descriptivo y observacional**, de una sola campaña.
- Para separar el efecto del clima del calendario de poda haría falta variación experimental o varias campañas.

---

## 15. Decisiones de arquitectura

| Decisión | Alternativa descartada | Razón |
|----------|----------------------|-------|
| Botones nativos para la navegación | Radio con CSS custom | Dependía de `:has()` y de la estructura interna del widget, que cambia entre versiones de Streamlit |
| `n_jobs=1` en XGBoost | `n_jobs=-1` (todos los hilos) | Con 452 filas: 1 hilo → 17,4 s; 2 hilos → 18,8 s. El overhead supera la ganancia. |
| Paralelismo secuencial en `en_paralelo()` | `ThreadPoolExecutor` / `loky` | Hilos: el GIL y XGBoost se estorban. Procesos: aborta en Windows por LLVM al importar `shap→numba`. |
| `nucleo/` sin Streamlit | todo en un solo módulo | Permite probar el cálculo sin levantar la app; mantiene la caché en un único lugar. |
| Colores de datos en `config.py` + Plotly | CSS | Lo que se ve en pantalla es lo mismo que sale exportado al Excel. |
| No estilizar la navegación con CSS | CSS custom sobre el radio | Fragilidad: depende de la versión de Streamlit. |

---

## 16. Evolución histórica del análisis

```
af10c0c  (2026-08-06)  Panel analítico módulo×semana. Primer acercamiento a las variables.
519226c  (2026-08-06)  Riego real cargado desde 4 Excel externos (78.326 filas). Corrige M01 duplicado.
db8b8f9              Primer análisis SHAP: analisis_shap_relacion_2025.py
                       R²=0,26 (5-fold aleatorio), R²=0,16 (deja-un-módulo-fuera) ← sí valida
                       analisis_shap_kg_ha.py descartado: R² negativo en 3 formulaciones
93b5f9f              Rediseño del reporte: metodología y dependencia explicitadas
c5be853  (2026-08-07)  Dashboard Streamlit completo + mejora del modelo
                       R² honesto: −0,116 → +0,053 | MAE: 757 → 686 kg/ha
                       barrido de 108 configuraciones con validación cruzada honesta
```

### Scripts eliminados y su equivalente en el dashboard
| Script eliminado | Equivalente en `dashboard/` |
|-----------------|----------------------------|
| `analisis_shap_kg_ha.py` | `nucleo/modelo.py` + `vistas/importancia.py` |
| `analisis_shap_relacion_2025.py` | `nucleo/modelo.py` + `nucleo/evaluacion.py` |
| `cargar_riego.py` | Integrado en `nucleo/datos.py` (lectura del Excel) |
| `exportar_panel_excel.py` | `nucleo/exportar.py` + `nucleo/informe.py` |
| `generar_reporte_shap_2025.py` | `vistas/` (todas las secciones) |
| `plantilla_reporte_shap_2025.html` | Streamlit (sin plantilla HTML manual) |
| `preparar_reporte_shap_2025.py` | `nucleo/datos.py` (cargar_panel) |

---

## 17. Dependencias Python (pyproject.toml)

```toml
[project]
name = "aquanqa-analitica"
requires-python = ">=3.12"
dependencies = [
    "pandas>=2.2",
    "numpy>=1.26",
    "openpyxl>=3.1",        # lectura del Excel de campaña
    "xlsxwriter>=3.2",      # escritura del Excel de resultados, con formato
    "scipy>=1.14",          # pruebas de hipótesis del estudio climático
    "psycopg[binary]>=3.2", # scripts que leen el panel desde reporting
    "python-dotenv>=1.0",
    "scikit-learn>=1.5",    # métricas y esquemas de validación cruzada
    "xgboost>=2.1",
    "shap>=0.46",
    "matplotlib>=3.9",      # figuras de los reportes HTML
    "streamlit>=1.40",      # tablero interactivo
    "plotly>=5.24",         # gráficos del tablero
]
```

> **Sin `pyodbc` ni `fastapi`** a propósito: el análisis lee de PostgreSQL y de Excel, no del Access histórico ni por HTTP (ADR-0006).

---

## 18. Archivos clave con sus roles

| Archivo | Rol |
|---------|-----|
| `app.py` | Punto de entrada Streamlit. Menú, despacho de vistas, pie de estado. |
| `config.py` | Única fuente de verdad de features, etiquetas, glosario, PARAMS, paleta, SECCIONES. |
| `estilo.py` | CSS mínimo: tipografía, espaciado, métricas. Sin tocar colores de dato. |
| `datos_origen.py` | Control de selección del Excel (repo o upload). |
| `verificar_capas.py` | Comprueba que `nucleo/` no importe Streamlit ni Plotly. |
| `nucleo/datos.py` | `cargar_panel(bytes) → Panel`. Toda la lógica de lectura y validación del Excel. |
| `nucleo/clima.py` | Las 5 pruebas estadísticas + `Veredicto`. |
| `nucleo/modelo.py` | `entrenar(tabla) → Ajuste` (XGBoost + SHAP). `verificar_consistencia()`. |
| `nucleo/evaluacion.py` | Conjuntos, Particiones, Referencias, `tabla_validacion()`, `aporte_por_variable()`, `comparar_familias()`. |
| `nucleo/exportar.py` | Motor xlsxwriter: formato de celdas, colores, anchos. |
| `nucleo/informe.py` | Qué hojas van en el Excel y cómo se explican. |
| `servicios/cache.py` | Envuelve `nucleo/` en `@st.cache_data` / `@st.cache_resource`. |
| `vistas/` | 12 módulos de UI. Cada uno expone `render(panel, ...)`. |
