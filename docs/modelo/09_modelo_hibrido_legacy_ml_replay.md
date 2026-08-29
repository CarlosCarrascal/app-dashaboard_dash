# Modelo híbrido Legacy–ML y replay histórico

**Fecha:** 2026-08-20
**Modelo:** `HibridoLegacyResidual_v1`
**Estado:** challenger experimental; R09 continúa como emisión operativa oficial.

## Qué se implementó

La plataforma ahora conserva tres referencias separadas:

1. `Real cosechado`: observación posterior, nunca predictor de su propia emisión.
2. `R09_publicado`: resultado operativo publicado por el equipo; no se etiqueta como
   algoritmo.
3. `MacroLegacy_v1` y `HibridoLegacyResidual_v1`: modelos reproducibles que compiten contra
   R09 bajo el mismo corte temporal.

El modelo híbrido no reconstruye toda la curva con varios modelos de machine learning. Parte
de la estructura agronómica legacy y corrige únicamente los residuos observados antes del
corte.

```text
curva legacy por lote
  + tres oleadas normales para frutos
  + peso exponencial y promedio ponderado
        ↓
Ridge regularizado con splines sobre residuos logarítmicos
        ↓
frutos híbridos = frutos legacy × exp(corrección de frutos)
peso híbrido   = peso legacy   × exp(corrección de peso)
kg             = plantas as-of × frutos híbridos × peso híbrido / 1000
```

El factor residual queda acotado (`exp(-1.5)` a `exp(1.5)` para frutos y `exp(-0.7)` a
`exp(0.7)` para peso). Los intervalos se calculan con cuantiles de residuos de entrenamiento;
si no hay muestra suficiente, el intervalo queda pendiente y no se inventa.

## Qué datos utiliza

La rejilla se construye como:

```text
campaña × emisión × lote × semana objetivo
```

Usa información disponible as-of de:

- maestro del lote y plantas;
- poda y días desde poda;
- cosecha real anterior al corte: acumulado, última paña y ventana reciente;
- fenología, clima y riego cuando tienen cobertura válida;
- campaña, fundo, módulo, variedad, calendario y horizonte;
- salida legacy calculada desde los parámetros de la curva.

No usa como predictor kilos, frutos, peso, calendario ni componentes de R09; tampoco usa
cosecha posterior a la emisión. Los resultados de Relaciones y Descubrimientos sirven para
definir hipótesis, rezagos y variables candidatas dentro del entrenamiento; no se copian como
coeficientes causales.

## Cómo se reconstruye la curva legacy

La implementación está en
[`macro_legacy.py`](../../packages/analitica/proyeccion/macro_legacy.py) y el ensamblaje
as-of en [`hibrido_legacy.py`](../../packages/analitica/proyeccion/hibrido_legacy.py).

Para cada lote y emisión se calibran parámetros nombrados equivalentes a `X/O/N` y `A/B`:

- tres incrementos de distribución normal acumulada para asignar frutos a la ventana;
- tres oleadas con medias, dispersiones y multiplicadores;
- tres pesos exponenciales;
- peso final ponderado por los frutos de las oleadas;
- identidad final de plantas, frutos/planta y peso.

Si la emisión es histórica, el parámetro se ajusta únicamente con cosecha anterior a esa
fecha. Si no existe historia suficiente, se marca `prior_legacy_sin_historia` y el resultado
queda con confianza baja. No se presenta ese prior como una medición real.

La macro original y el libro `Distribucion historicos_REC.xlsm` siguen siendo referencias de
paridad. No se copian sus celdas al modelo ni se usan silenciosamente como segunda base de
datos. La extracción productiva continúa siendo Access → PostgreSQL; un parámetro manual de
Excel solo podrá incorporarse mediante un adaptador explícito, con fuente, hash y vigencia.

## Replay ciego y curva completa

Para cada emisión histórica:

1. se congela el snapshot y se construye el panel as-of;
2. se calibra la curva legacy con datos anteriores;
3. se entrena la corrección residual solo con emisiones y objetivos anteriores;
4. se genera la predicción sin unir `real_kg` futuro;
5. después se incorpora la cosecha posterior para calcular el error.

La curva histórica del dashboard no es una única emisión maquillada. Para cada semana objetivo
selecciona la última emisión estrictamente anterior a esa semana y conserva su origen. Por eso
la primera gráfica puede mostrar simultáneamente:

- negro: curva completa real;
- azul grisáceo: R09 histórico;
- verde: híbrido Legacy–ML histórico;
- marrón, cuando existe: MacroLegacy reconstruida.

Cada punto guarda `fecha_emision`, `fecha_objetivo`, horizonte, versión, snapshot y estado de
evaluación. La vista operativa, en cambio, muestra solo real disponible hasta hoy y pronóstico
posterior.

## Cómo se decide si es mejor

Todos los modelos se comparan en el mismo universo de lote-semana y corte. Se reportan WAPE,
MASE, MAE, sesgo, RMSSE, cobertura P10–P90, ancho de intervalo y errores separados de
frutos/planta y peso. El R² no decide la promoción.

La promoción exige mejora simultánea de WAPE y MASE, sesgo absoluto ≤10 %, cobertura de
intervalo entre 75–85 %, cobertura de volumen ≥90 %, ausencia de deterioro relevante por
fundo, dos campañas externas, cero fugas y reproducción desde snapshot. Si no cumple:

> Sin mejora estadísticamente comprobada; R09 continúa como referencia operativa.

## Evidencia científica y límites de interpretación

La estructura de separar cantidad de frutos y peso es coherente con estudios de desarrollo y
componentes del rendimiento del arándano. La utilidad de flores, yemas y clima para predecir
frutos tiene respaldo específico en arándano, pero debe recalibrarse a variedad, localidad y
calidad de medición. Los modelos híbridos de proceso y ML pueden mejorar el error en algunos
ambientes, pero no garantizan superioridad local. La combinación de juicio experto con modelos
estadísticos también debe quedar versionada y evaluarse retrospectivamente.

Estas fuentes respaldan la hipótesis, no convierten las relaciones observadas en causalidad:

- [Predicción de frutos de arándano con yemas, flores y clima](https://www.sciencedirect.com/science/article/pii/S0304423811005607).
- [Modelos de proceso y machine learning para rendimiento agrícola](https://pubmed.ncbi.nlm.nih.gov/33452349/).
- [Modelo guiado por conocimiento experto en campos comerciales](https://arxiv.org/abs/2307.13466).
- [Combinación de juicio experto y pronósticos estadísticos](https://www.sciencedirect.com/science/article/pii/0272696395000399).

SHAP, correlaciones, ALE, ARDL y precedencia temporal son explicaciones asociativas o
predictivas. No se mostrarán como “impacto causal” sin intervención, controles negativos y
ajuste de confundidores previamente definido.

## Comandos

```powershell
npm run analytics:backtest -- --source postgres
npm run analytics:project -- --source postgres `
  --modelo-proyeccion HibridoLegacyResidual_v1 `
  --fecha-emision 2026-08-20 `
  --horizonte-semanas 10
```

La proyección experimental no modifica `reporting.proyeccion_vigente`. La página Proyección
lee el replay y la vista `reporting.curva_historica_modelos`; si la migración SQL aún no se ha
aplicado, muestra ausencia de curva en vez de inventarla.
