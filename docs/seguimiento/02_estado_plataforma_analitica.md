# Contexto de continuidad · Plataforma analítica y predictiva

**Fecha:** 2026-08-18
**Repositorio:** `aquanqa-data-platform`
**Propósito:** dejar una referencia de continuidad para entender qué plan se ejecutó, qué
está activo, qué resultados existen y qué falta antes de considerar madura la proyección.

> **Copia versionada** de `.md/contexto-plataforma-analitica-2026-08-18.md`.
> La carpeta `.md/` está ignorada por Git
> (`.gitignore:54`), así que este archivo es el que sobrevive a un clon limpio y
> manda si ambos divergen. Replica aquí todo cambio de fondo.

## 1. Objetivo del trabajo

El objetivo dejó de ser solamente mostrar gráficos, correlaciones o una importancia de
variables. La plataforma debe:

- descubrir relaciones entre variables fenológicas, climáticas, de riego y de producción;
- separar asociaciones descriptivas, correlacionales, temporales, predictivas y causales;
- justificar técnicamente cada modelo y sus supuestos;
- predecir por componentes el rendimiento, especialmente frutos por planta y peso de baya;
- proyectar `kg por lote-semana` en horizontes operativos, de planificación y de escenario;
- comparar alternativas bajo los mismos cortes temporales;
- comunicar incertidumbre, limitaciones y razones de promoción o descarte;
- permitir que una conclusión navegue hasta sus datos, código, evidencia y ejecución.

La capa oficial para este objetivo es el módulo `/analitica/*`. La información histórica que
no cumple este contrato no participa en la navegación ni en las decisiones operativas.

## 2. Plan ejecutado

### 2.1 Gobierno científico y de modelado

- R09 se conserva como campeón operativo inicial porque es el forecast publicado que ya tiene
  sentido de negocio.
- XGBoost y Random Forest se tratan como alternativas/challengers, no como ganadores por
  defecto.
- La promoción exige mejora simultánea en error, sesgo, cobertura, volumen, fundos relevantes,
  campañas externas, fuga y reproducibilidad.
- `R²` queda como diagnóstico; las métricas principales son MASE y WAPE, complementadas con
  MAE, RMSSE, sesgo, pinball loss, cobertura, ancho e interval score.
- CA244NI se usa como referencia del proceso de medición y descomposición del volumen; no se
  convirtió en una ecuación predictiva reproducible ni en un coeficiente transferido al
  cultivo/localidad actual.
- Se creó un catálogo científico versionado con DOI/URL, cultivo, variedad, ubicación,
  muestra, variables, método, resultados, limitaciones y transferibilidad.

### 2.2 Arquitectura y persistencia

Se separaron dos esquemas con responsabilidades distintas:

- `mlflow`: tablas internas administradas por MLflow para tracking y registry;
- `analytics`: snapshots, ejecuciones, predicciones, métricas, afirmaciones, decisiones,
  calidad y artefactos de negocio.

La capa de negocio persistida incluye:

- `dataset_snapshot`;
- `forecast_run`;
- `prediction`;
- `metric`;
- `evidence_claim`;
- `model_decision`;
- `quality_result`;
- `artifact`.

PostgreSQL es la fuente principal. Excel solo puede utilizarse mediante un fallback explícito,
visible en el snapshot, el dashboard, los controles y la trazabilidad. No se permite un
fallback silencioso.

Se incorporaron contratos para lote-semana, semántica `as-of`, predicciones, intervalos,
componentes fenológicos y jerarquía de agregación.

### 2.3 Capa de relaciones e inferencia

Se implementó una matriz de hipótesis agronómicas que organiza el análisis en estas rutas:

1. poda y acumulación térmica hacia floración;
2. flores y cuajado hacia cantidad de frutos;
3. estados E1–E5 hacia la semana probable de cosecha;
4. estado/diámetro hacia el peso de baya;
5. plantas productivas × frutos por planta × peso hacia kg;
6. clima y riego hacia velocidad de transición y peso.

Cada resultado conserva estimación, intervalo, muestra efectiva, rezago, campaña, estabilidad
por módulo, supuestos y prueba placebo. El tamaño efectivo se reporta por semanas cuando el
clima es común a varios módulos; no se cuentan como réplicas climáticas independientes todas
las filas que repiten la misma semana.

Se implementaron:

- Pearson y Spearman con intervalos;
- correlación parcial controlando calendario, poda y módulo cuando los campos están disponibles;
- bootstrap temporal por bloques;
- estabilidad por módulo;
- placebos futuros;
- corrección Benjamini–Hochberg;
- modelos mixtos con interceptos por lote/módulo;
- ARDL/HAC para relaciones temporales agregadas;
- splines regularizados para relaciones retardadas y no lineales;
- análisis de sensibilidad a semanas, agregación y temperatura base;
- permutación por familias agronómicas;
- SHAP para reconstruir predicciones individuales;
- ALE para formas y umbrales evitando combinaciones irreales de variables correlacionadas.

La plataforma distingue explícitamente asociación de causalidad. SHAP, ALE, ARDL y precedencia
temporal no se etiquetan como efectos causales. Una conclusión causal requiere una intervención
o experimento natural, confundidores definidos antes del análisis, controles negativos y
análisis de sensibilidad.

### 2.4 Torneo de proyección

El objetivo operativo es `kg por lote-semana`; se derivan `kg/ha`, frutos por planta y peso.
Los horizontes son:

- 1–2 semanas: compromiso operativo;
- 3–6 semanas: planificación;
- 7–10 semanas: escenario.

El torneo compara con los mismos cortes temporales:

- R09 publicado;
- R09 corregido por sesgo;
- Naive, SeasonalNaive e HistoricAverage;
- AutoETS y AutoARIMA;
- Croston y ADIDA para series intermitentes;
- Ridge;
- Random Forest;
- XGBoost;
- modelo fenológico por componentes;
- combinación ponderada cuando resulta más estable que un único ganador.

La validación usa rolling-origin temporal anidada. Los folds internos sirven para parámetros y
temperatura base; los folds externos sirven para medir desempeño. No se utiliza K-fold aleatorio
para seleccionar o publicar resultados.

La reconciliación cubre:

`lote → módulo → fundo → empresa`

Bottom-Up garantiza la coherencia contable. MinT-shrink no negativo está implementado como
alternativa, pero no se conserva si no mejora fuera de muestra con pronósticos agregados
independientes comparables.

### 2.5 Trazabilidad y comunicación

Cada exportación auditable puede incluir:

- manifiesto;
- snapshot;
- referencias científicas;
- model card;
- firma del contrato;
- parámetros;
- métricas;
- predicciones;
- explicaciones;
- entorno;
- checksums SHA-256.

El dashboard oficial expone estas áreas:

- Relaciones;
- Descubrimientos;
- Modelo;
- Explicación;
- Proyección;
- Backtesting;
- Trazabilidad;
- Fundamento científico.

## 3. Estado verificable de las corridas

### Backtesting y decisión

La corrida completa de backtesting es `run_id = 20`. Comparó 14 familias y produjo 277.000
predicciones bajo cortes comunes.

La decisión vigente conserva R09:

- **Operativo:** Random Forest fue challenger, pero no se promovió. Mejoró WAPE 12,23 % y
  MASE 15,64 % en pares comunes, aunque incumplió controles de sesgo y deterioro por fundo.
  El intervalo bootstrap de la diferencia de WAPE cruzó cero.
- **Planificación:** R09 corregido por sesgo fue challenger, pero tampoco se promovió. Mejoró
  WAPE y MASE 5,30 %, pero incumplió sesgo y cobertura P10–P90; su intervalo también cruzó
  cero.
- **Escenario:** no existe todavía una comparación externa suficiente de 7–10 semanas.

El estado correcto es **sin mejora estadísticamente comprobada**. Una mejora puntual de un
modelo no cambia el campeón.

### Proyección

La proyección vigente es `run_id = 21`:

- 2.600 predicciones lote-semana;
- 817 lotes físicos;
- periodo del 2026-08-10 al 2026-09-07;
- P50 total: 3.911.651,5 kg;
- reconciliación jerárquica exacta, con diferencia de 0 kg.

Los cuantiles se agregan Bottom-Up para mantener coherencia contable. Eso no significa que el
P50 agregado sea automáticamente el cuantil exacto de una distribución conjunta; esta
limitación debe considerarse en decisiones de riesgo.

### Entrenamiento y explicaciones

La corrida de entrenamiento/explicabilidad registrada como `run_id = 17` dejó preparados los
artefactos, firmas, versiones de modelos y explicaciones. Cuando no existe un servidor HTTP de
MLflow configurado, el estado queda explícitamente como `mlflow_no_configurado`; no se crea un
almacén local oculto ni se presenta el resultado como tracking completo.

## 4. Comandos reproducibles

```powershell
npm run analytics:relations
npm run analytics:backtest
npm run analytics:train
npm run analytics:project
npm run analytics:export
npm run analytics:mlflow
```

El flujo conceptual es:

```text
stg + dim
  → snapshot as-of
  → contrato lote-semana
  → relaciones / backtest
  → torneo champion-challenger
  → intervalos y reconciliación
  → analytics + MLflow
  → dashboard y ZIP auditable
```

## 5. Limitaciones que siguen siendo reales

- La fenología se concentra en 2026 y todavía no hay suficientes campañas externas para
  estimar de forma independiente transición E1–E5, supervivencia/cuajado y crecimiento de baya.
- `R09_componentes_publicados` (antes `Fenologico_componentes`) no entrena: reexpresa la
  aritmética interna del forecast publicado y sirve como control de consistencia. El modelo
  que sí estima los componentes es `Componentes_identidad`, que usa las plantas del catálogo
  como base y hereda de R09 el calendario de semanas con cosecha.
- Temperatura, DPV y GDD son colineales; los rankings individuales no deben leerse como efectos
  aislados.
- El clima común a varios módulos reduce el tamaño muestral efectivo.
- La poda puede estar dispersa dentro del módulo y los censos fuente no son completamente
  bitemporales/versionados.
- Faltan actualmente variables de polinización, suelo, nutrición completa y pronóstico
  meteorológico futuro.
- La relación agua–producción publicada en otros ambientes o variedades no se transfiere como
  coeficiente universal.
- No se debe llamar causal a una asociación solo porque tenga significancia, SHAP alto,
  precedencia temporal o buen desempeño predictivo.
- Los resultados de 7–10 semanas todavía son de escenario, no de compromiso operativo.

## 6. Pendientes para madurez productiva

1. Ejecutar el flujo oficial contra PostgreSQL productivo con el esquema `analytics` y MLflow
   HTTP persistente.
2. Incorporar campañas externas y verdaderos folds de evaluación prospectiva.
3. **Parcialmente implementado (2026-08-18).** Existe la familia `Componentes_identidad`:
   dos modelos separados para frutos por planta y peso de baya, compuestos por la identidad
   `plantas x frutos/planta x peso / 1000`. Entra como challenger bajo la regla conjuntiva de
   ADR-0007. Queda pendiente reconciliar el censo de estados (`stg.v_e03_estados`) con
   cosecha, para poder validar los frutos contra una observacion independiente y no solo
   contra la identidad despejada de los kilos.
4. Añadir pronóstico meteorológico futuro y variables de polinización, suelo y nutrición.
5. Cerrar el ciclo de monitoreo cuando llegue la cosecha real: WAPE, MASE, sesgo, cobertura,
   deriva, lotes fuera de rango y degradación por campaña/horizonte.
6. Completar validación de despliegue en Render con URL, logs y medición de cold start.

## 7. Archivos de referencia

- [Plan y plataforma analítica](../modelo/04_plataforma_analitica_predictiva.md)
- [Gobierno y champion–challenger](../adr/0007-gobierno-analitico-y-champion-challenger.md)
- [Catálogo científico](../cientifico/catalogo_evidencia.json)
- [Índice de decisiones arquitectónicas](../adr/README.md)
- [Controles SQL de analítica](../../db/sql/90_checks/030_analytics.sql)
- [Pruebas de layout y navegación analítica](../../apps/dashboard/tests/test_analytics_layout.py)
- [Auditoría de Impacto agronómico](./04_auditoria_impacto_agronomico.md)

## 8. Criterio de continuidad

Antes de cambiar el modelo oficial, revisar este documento junto con el snapshot de datos, la
decisión de `analytics.model_decision`, el backtesting temporal, los claims de evidencia y el
model card. La pregunta de continuidad no es “¿qué modelo tiene el R² más alto?”, sino:

> ¿El challenger mejora fuera de muestra, con incertidumbre cuantificada, sin fuga, con
> coherencia jerárquica y con una explicación agronómica que no confunda asociación con causa?
