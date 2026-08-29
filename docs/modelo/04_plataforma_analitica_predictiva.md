# Plataforma analítica y predictiva

## Decisión vigente

R09 es el campeón operativo inicial. XGBoost se conserva como modelo de relaciones 2025 y
challenger explicable, no como pronóstico oficial. En la comparación contemporánea existente,
Random Forest obtuvo mejor validación por bloque temporal (`R² 0,411`, `MAE 491 kg/ha`) que
XGBoost (`R² 0,331`, `MAE 537 kg/ha`); por tanto no existe sustento para declarar ganador a
XGBoost.

El torneo completo vigente (`analytics.forecast_run.run_id = 20`) comparó catorce familias y
retuvo R09. En operativo, Random Forest mejoró WAPE `12,23 %` y MASE `15,64 %` sobre los pares
comunes y cubrió `90,48 %` del volumen; no se promovió porque incumplió sesgo y deterioró un
fundo `12,19 %`. Ganó en `58,10 %` de los campaña-lotes, pero su IC95 de ΔWAPE
challenger−R09 fue `[-0,1424; 0,0349]` y cruzó cero. En planificación, R09 corregido mejoró
ambas métricas `5,30 %` y ganó en `60,60 %` de los campaña-lotes, pero incumplió sesgo y
cobertura P10–P90; su IC95 `[-0,0871; 0,0261]` también fue inconcluso. El veredicto es:
**sin mejora estadísticamente comprobada**.

La proyección vigente (`run_id = 21`) conserva R09 y contiene 2.600 lotes-semana, 817 lotes
físicos y P50 total de 3.911.651,5 kg entre 2026-08-10 y 2026-09-07. El histórico actual no
ofrece evaluación comparable de 7–10 semanas, por lo que escenario permanece explícitamente
sin challenger.

## Flujo ejecutable

```text
stg + dim
  -> snapshot con firma
  -> contrato lote-semana y semántica as-of
  -> relaciones / backtest rolling-origin
  -> torneo con cortes comunes
  -> intervalos + reconciliación
  -> regla champion-challenger
  -> analytics + MLflow + ZIP auditable
  -> dashboard
```

Comandos:

```powershell
npm run analytics:relations
npm run analytics:backtest
npm run analytics:train
npm run analytics:project
npm run analytics:export
npm run analytics:mlflow
```

MLflow usa `MLFLOW_BACKEND_STORE_URI` para sus tablas internas en el esquema `mlflow` y
expone `MLFLOW_TRACKING_URI` por HTTP al pipeline. `analytics:train` registra datasets,
firmas, artefactos y versiones de Ridge, Random Forest y XGBoost con alias de challenger;
solo una promoción aprobada puede asignar el alias champion. Si el servidor HTTP no está
configurado, la corrida registra `mlflow_no_configurado` y nunca cae a un almacén local oculto.
La corrida de entrenamiento y explicabilidad `run_id = 17` verificó este comportamiento.

`PostgreSQL` es la fuente principal. `--source excel` es un fallback explícito para exploración;
como el libro no conserva versiones R09, no puede publicar un backtest oficial. Toda activación
del fallback queda en el snapshot, los controles y el model card.

## Hipótesis y evidencia

Las seis hipótesis se materializan en siete rutas estimables y se evalúan con Pearson, Spearman,
correlación parcial, intervalos por bootstrap temporal de bloques, rezagos, placebos futuros,
estabilidad por módulo y Benjamini-Hochberg. MixedLM, ARDL/HAC y spline distributed-lag son
análisis complementarios. El tamaño
efectivo se informa por semanas porque el clima común a muchos lotes no crea réplicas climáticas.

La corrida inferencial vigente produjo 55 estimaciones/sensibilidades, 21 ajustes
complementarios y siete claims. MixedLM convergió en seis de siete rutas. ARDL/HAC y spline
tuvieron longitud temporal suficiente únicamente para la ruta clima/riego; las demás quedan
publicadas como insuficientes, no se rellenan con coeficientes bibliográficos.

Las conclusiones se materializan en `analytics.evidence_claim`. Solo pueden recibir las clases
`descriptiva`, `correlacional`, `temporal`, `predictiva` o `causal`; el `CHECK` impide publicar
una afirmación causal sin estado causal. En la implementación actual ninguna inferencia
observacional se etiqueta causal.

## Torneo

Todos los modelos usan los mismos cortes externos:

- R09 publicado y corregido por sesgo;
- Naive, SeasonalNaive, HistoricAverage, AutoETS, AutoARIMA, Croston y ADIDA;
- Ridge, Random Forest y XGBoost como correctores residuales de R09;
- descomposición fenológica `frutos_total × peso / 1000`;
- combinación ponderada por errores históricos disponibles antes de cada emisión.

La combinación compite en cada fold. Bottom-Up se usa para coherencia contable de la proyección.
MinT-shrink no negativo está implementado mediante HierarchicalForecast, pero no se retiene sin
pronósticos agregados independientes comparables fuera de muestra; no se simula una victoria de
MinT usando agregados derivados del mismo Bottom-Up.

La selección de parámetros ML usa el último bloque temporal interno. El entrenamiento de una
emisión solo admite objetivos realizados antes de la fecha de emisión. Las métricas principales
son MASE y WAPE; también se guardan MAE, RMSSE, sesgo, pinball, cobertura, ancho e interval
score. `R²` es diagnóstico.

## Trazabilidad y aceptación

Los esquemas cumplen funciones separadas:

- `mlflow`: tablas internas administradas por MLflow;
- `analytics`: snapshots, runs, predicciones, métricas, claims, decisiones, calidad y artefactos;
- `reporting`: contratos de lectura para dashboard y BI.

Cada ZIP contiene Parquet, snapshot, catálogo científico, model card, firma de contrato, DAG,
regla de promoción, entorno, manifiesto y SHA-256. Los controles bloquean fuga futura,
intervalos desordenados, claves duplicadas y jerarquías incoherentes.

`analytics:backtest` incorpora monitoreo al llegar cosecha real: recalcula WAPE, MASE, sesgo y
cobertura; registra degradación por campaña/horizonte, PSI de variables as-of y lotes fuera del
rango de entrenamiento. Cambiar datos posteriores a una emisión está cubierto por una prueba
metamórfica y no puede alterar su panel ni su predicción histórica.

Solo `analytics:backtest` puede crear una decisión vigente. `train`, `project` y `export`
consumen esa decisión sin reescribirla; esto evita que una corrida parcial o sin modelos
estadísticos cambie producción.

## Límites vigentes

- Fenología se concentra en 2026 y los censos fuente no son bitemporales/versionados.
- Temperatura, DPV y GDD son colineales; una importancia individual puede ser engañosa.
- Poda se dispersa dentro del módulo y el clima es común a varios módulos.
- Faltan polinización, suelo, nutrición y pronóstico meteorológico futuro.
- La descomposición fenológica reutiliza componentes R09 hasta contar con campañas suficientes
  para estimar transición E1-E5, supervivencia y crecimiento de baya de forma externa.
- Los cuantiles sumados Bottom-Up garantizan coherencia contable, pero no son por sí solos el
  cuantil de una distribución conjunta; esto debe considerarse antes de decisiones de riesgo.

El catálogo versionado de evidencia está en `docs/cientifico/catalogo_evidencia.json`.

## Estado del módulo histórico `/modelo/*`

La aplicación no elimina los artefactos anteriores porque son útiles para auditoría y para
reproducir lecturas de la campaña 2025. Sin embargo, `XGBoost 2025`, `SHAP 2025` y `Qué
explica el R²` son exploratorios: trabajan principalmente con un ajuste/interpolación de la
misma campaña, no pronostican de forma oficial frutos por planta y peso, y sus importancias
SHAP describen el comportamiento del predictor, no efectos causales.

Por eso quedan como **legacy** y no se descubren ni se registran al iniciar el dashboard. La
navegación oficial usa exclusivamente `/analitica/*`, donde el campeón se decide con
backtesting temporal, intervalos, componentes de rendimiento, evidencia y trazabilidad. Para
una auditoría puntual se puede exponer el módulo histórico con:

```powershell
$env:AQUANQA_ENABLE_LEGACY_MODEL = "true"
npm run dashboard
```

La bandera no cambia el campeón, no habilita sus predicciones para `analytics:project` y no
convierte sus salidas en evidencia causal.
