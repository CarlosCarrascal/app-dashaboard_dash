# 0008 · Mantener el módulo predictivo histórico como legacy

## Estado

Aceptado.

## Contexto

El módulo anterior de `/modelo/*` contiene XGBoost, SHAP y una lectura del R² de la campaña
2025. Tiene valor para revisar decisiones y reproducir pantallas antiguas, pero no cumple el
contrato del producto analítico actual: no es un backtest rolling-origin, no demuestra
pronóstico prospectivo de frutos por planta y peso, y SHAP no identifica causalidad.

Además, el ranking visible de XGBoost podía confundirse con la decisión operativa, aunque el
torneo vigente conserva R09 y encuentra a Random Forest por delante de XGBoost en la evaluación
por bloque temporal.

## Decisión

Se conservan los archivos y las pruebas del módulo como referencia histórica, pero no se
registran automáticamente sus páginas en Dash. La capa oficial es `/analitica/*` y sus
decisiones provienen de `analytics:backtest` y de la regla champion–challenger.

El módulo histórico solo se expone si la persona operadora establece explícitamente
`AQUANQA_ENABLE_LEGACY_MODEL=true`. Cuando se habilita, sus páginas aparecen bajo
`Legacy / Exploración` y llevan el prefijo `Legacy ·`.

## Consecuencias

- El dashboard de producción no presenta el instrumento histórico como modelo vigente.
- La auditoría conserva el código, las funciones y la posibilidad de reproducirlo.
- Ninguna ejecución `analytics:train`, `analytics:project` o `analytics:export` depende de
  estas páginas.
- El acceso legacy es una herramienta de comparación, no una excepción al gobierno del
  modelo ni una fuente para conclusiones causales.

## Alternativas descartadas

- Eliminar el módulo: perdería trazabilidad y comparabilidad con la campaña 2025.
- Dejarlo visible junto a las páginas oficiales: mantendría una ambigüedad de producto y
  permitiría interpretar SHAP/R² como evidencia de manejo.
