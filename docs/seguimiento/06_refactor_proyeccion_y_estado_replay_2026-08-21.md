# Refactor de Proyección y estado del replay

## Qué quedó implementado

La página activa de Proyección dejó de concentrar la interfaz en un único módulo. La ruta
activa se divide en coordinador, dominio, gráficos, vistas y callbacks. La implementación
anterior se conserva en `apps/dashboard/legacy/proyeccion_legacy.py`, fuera de `pages/`, y
no se importa desde la página activa. Esto evita que Dash la descubra automáticamente y
registre una segunda página/copia de callbacks para `/analitica/proyeccion`.

La primera sección de la página es la curva histórica. Lee
`reporting.curva_historica_modelos` y puede mostrar:

- Real cosechado completo.
- R09 histórico publicado.
- MacroLegacy reconstruida.
- Híbrido Legacy–ML.
- Fenológico por componentes.

Cada curva forecast conserva el rango de emisiones que originó el punto. R09 se trata como
emisión operativa publicada; no se presenta como algoritmo.

## Replay persistido

`run_id=53` terminó en estado `succeeded` el 21/08/2026 y contiene:

- `R09_publicado`;
- `MacroLegacy_v1`;
- `HibridoLegacyResidual_v1`;
- `FenologicoComponentes_v1`.

Las tres alternativas generan 8.170 filas para el mismo corte, 817 lotes y 10 semanas. La
comparación pareada usa 493 lote-semana con real común para todos los modelos. La decisión
persistida conserva R09 como campeón porque el híbrido y el fenológico no superan todos los
gates; MacroLegacy tiene menor WAPE en ese corte, pero no hay MASE estimable suficiente para
declarar una mejora estadística.

La vista histórica queda con las series Real, R09, MacroLegacy, Híbrido y Fenológico. La
consulta del dashboard filtra también el último run exitoso para no mezclar métricas antiguas
con la curva actual.

## Qué no debe afirmarse todavía

`run_id=53` es una comparación de cableado y desempeño de un corte común, no una validación
externa de ocho cortes ni una prueba de superioridad definitiva. El intento `run_id=54` de
ampliar el replay a ocho cortes fue cancelado por tiempo batch y quedó marcado como `failed`.
No se usa para métricas ni para decidir promoción.

Por tanto, el tablero debe comunicar:

> Sin mejora comprobada; R09 continúa como referencia operativa.

El MixedLM del challenger fenológico queda disponible como alternativa explícita, pero el
replay operativo lo desactiva por defecto para evitar que un ajuste inferencial lento y con
advertencias de singularidad bloquee el batch. Esto no convierte la ejecución rápida en una
prueba causal.

## Pruebas ejecutadas

- 36 tests de Proyección, contratos y layout antes de los cambios finales de persistencia.
- 19 tests específicos del modelo fenológico, híbrido y torneo, con dos advertencias de
  convergencia del MixedLM en la ruta diagnóstica.
- Verificación directa del gráfico: cinco trazas con datos en la vista SQL: Real (203 puntos),
  R09 (53), MacroLegacy (10), Híbrido (10) y Fenológico (10).

## Siguiente paso correcto

Optimizar la familia fenológica y la consolidación de métricas para terminar un replay de
varios cortes dentro del tiempo operativo. Solo después se podrá interpretar estabilidad
temporal y decidir si el híbrido mejora a R09 fuera de muestra.
