# 0011 · Descomponer proyección conservando su API

## Estado

Aceptado.

## Contexto

La proyección fenológica e híbrida crecieron alrededor de módulos grandes. Allí conviven
paneles, as-of, ajuste, métricas, evidencia, priors, replay, relaciones y cálculos macro.
Mover cada función sin una frontera deja ciclos de importación y hace difícil saber qué
parte es segura de cambiar.

## Decisión

Las responsabilidades se extraen a módulos cohesivos:

- fenología: contratos, especificación, panel, evidencia, ajuste y métricas;
- híbrido: macro, priors, residual y replay;
- ensamblaje: auditorías de merges; la lógica principal de relaciones sigue en
  `relaciones.py` y se extraerá en una fase posterior con su propia comparación;
- infraestructura: serialización, Git, persistencia y tracking.

`analitica.proyeccion` conserva su lista pública y resuelve sus símbolos mediante una fachada
lazy. Las rutas históricas (`fenologico_v1`, `macro_legacy`, `hibrido_legacy`, `relaciones` y
`gobernanza`) continúan disponibles y apuntan a las implementaciones extraídas. Así, una
persona puede seguir usando el paquete sin conocer su organización interna.

La extracción no autoriza cambiar resultados. En particular:

- se preservan el horizonte, el as-of y el grano de campaña/lote/fecha;
- se conservan las columnas y el orden esperado por consumidores;
- la calibración de volumen no se activa en una ruta que antes no la usaba;
- la exclusión actual de XGBoost para el objetivo `real_kg` queda identificada como una
  diferencia frente al blob histórico `5522b730b257c10f743d1c6ec0103da920eb9f7b`: el
  histórico agregaba XGBoost siempre y el estado actual lo excluye para `real_kg`. El estado
  actual usa Tweedie, SplineRidge, RandomForest e HistGradientBoosting para ese objetivo.
  No se declarará equivalencia histórica total hasta comparar el mismo snapshot, cortes,
  datos, versiones y métricas, y aprobar explícitamente el resultado.

## Consecuencias

- El import inicial de `analitica.proyeccion` y `analitica.nucleo` no carga sklearn,
  statsmodels, XGBoost, scipy, MLflow ni psycopg sin necesidad; resolver una función que
  realmente usa una de esas librerías sí la carga. La instalación completa sigue declarando
  esas dependencias para que las rutas de producción sean reproducibles.
- Las pruebas focales pueden verificar cada bloque y las pruebas de fachada verifican la
  compatibilidad.
- El paquete tiene más archivos, pero cada uno tiene una responsabilidad que se puede
  explicar y auditar.
- La equivalencia se afirma solo para el estado actual probado; una comparación histórica
  distinta se reporta como riesgo pendiente.
- Las fachadas no constituyen un mecanismo de rollback si la implementación anterior no está
  disponible en un commit/tag o wheel versionado.

## Alternativas descartadas

- Mantener un único módulo monolítico: dificulta el aislamiento y la carga opcional.
- Cambiar la API a la vez que se reorganiza: mezcla migración con refactorización.
- Activar automáticamente cálculos nuevos durante la extracción: alteraría resultados sin
  un experimento ni aprobación.
