# ADR-0007 · Gobierno analítico y champion-challenger

## Estado

Aceptado · 2026-08-18

## Decisión

R09 permanece como campeón inicial. Ningún challenger se promueve por una sola métrica ni por
validación aleatoria. La promoción requiere mejora relativa de WAPE y MASE, sesgo, cobertura,
volumen, estabilidad por fundo, dos campañas externas, ausencia de fuga y reproducción.

MLflow administra tracking y registry en el esquema `mlflow`; el esquema `analytics` es el
contrato estable de negocio. PostgreSQL es la fuente principal y cualquier fallback Excel debe
quedar visible.

Las conclusiones se almacenan con clase de evidencia. SHAP, ALE, ARDL, precedencia temporal y
permutación no se etiquetan como causales.

## Consecuencias

- El dashboard ya no presenta XGBoost como ganador por defecto.
- Una ejecución se puede reconstruir desde snapshot, commit, configuración y ZIP.
- Una mejora puntual no cambia producción si incumple un control de seguridad estadística.
- CA244NI fundamenta el protocolo de medición y la descomposición, no una ecuación reproducible.

## Addendum · 2026-08-18 · Familia de componentes

Se incorpora al torneo la familia `Componentes_identidad`, que estima **frutos por planta** y
**peso de baya** con dos modelos separados y compone el rendimiento mediante
`kg = plantas × frutos por planta × peso / 1000`. Entra como challenger y queda sujeta a la
misma regla conjuntiva; no altera el campeón por sí sola.

Cuatro decisiones que acompañan la incorporación:

1. **La base de plantas es el maestro del lote.** El número de plantas no varía dentro de la
   campaña: con las que se inicia son las que se terminan, confirmado por el equipo agronómico
   y verificado en la base el 2026-08-19 (767 de 781 lotes con el mismo número en cosecha que
   en el maestro; razón media 1,0023; 2 de 1.959 combinaciones lote-campaña con variación
   interna). El maestro es además la única cifra disponible en el momento de emitir.
   El objetivo de frutos se despeja sobre esa misma base y cada fila declara `base_plantas`,
   no por desconfianza del dato —la diferencia medida entre bases es del 0,3 %— sino para que
   la métrica compare siempre contra la serie que corresponde y un cambio futuro en el
   registro de cosecha no pase inadvertido.
2. **La regla de promoción no incorpora umbrales de desempeño por componente.** Gobierna la
   cifra en kilos, y añadir umbrales sobre una métrica que hoy no distingue entre modelos
   sería rigor aparente. Sí se añade `requiere_identidad_coherente`, una comprobación
   estructural: un modelo que publica las tres piezas debe producir con ellas exactamente el
   kg que muestra.
3. **Se renombra `Fenologico_componentes` a `R09_componentes_publicados`.** No entrenaba nada
   —reexpresa `frutos_total × peso_baya / 1000` del propio forecast— y declaraba
   `version_fuente="plantas×frutos×peso"`, una fórmula que no calcula porque no interviene el
   número de plantas. Las filas ya persistidas conservan el nombre anterior; no se reescribe
   el histórico.
4. **La familia hereda de R09 el calendario de cosecha:** predice cuántos kilos salen de una
   semana que ya se espera productiva, no qué semanas lo son. Queda registrado como control
   de calidad, no como supuesto tácito.

Límite declarado: `frutos_reales_por_planta` es una identidad despejada desde los kilos
cosechados, no un censo independiente. El censo existe (`stg.v_e03_estados`) pero no está
reconciliado con cosecha, así que la familia **no** puede afirmar que predice el número de
frutos observado en campo.

### Intervalos: qué se publica y qué se diagnostica

Los intervalos publicados se calibran sobre el **producto**, con los residuos as-of de la
propia familia, igual que en el resto del torneo. Es lo que mantiene comparable el control
`0,75 <= cobertura <= 0,85` de la promoción: si una familia produjera intervalos con otra
semántica, ese check dejaría de comparar entre iguales.

Además existe `intervalos_producto_montecarlo`, **desactivado por omisión** y activable con
`--diagnostico-montecarlo`. Remuestrea parejas completas `(residuo de frutos, residuo de
peso)` de la misma fila, en bloques contiguos de emisiones, y escribe `p10_kg_mc` y
`p90_kg_mc` en columnas propias que caen dentro de `analytics.prediction.componentes`. Sirve
para saber cuánta incertidumbre aporta cada pieza; no sustituye a los intervalos oficiales.

Las parejas se remuestrean juntas a propósito: preservan la correlación empírica entre ambos
errores sin asumir ninguna forma de dependencia. Muestrear cada componente por separado daría
un intervalo demasiado ancho cuando los errores se compensan.

Queda advertido que **el producto de dos intervalos conformales no es conformal**: por eso
`intervalos_enbpi` no se aplica por componente para luego multiplicar.

### Alta de familias challenger

`FAMILIAS_CHALLENGER` en `torneo.py` es un registro de datos: añadir una familia es una
entrada más, sin tocar el cuerpo de `ejecutar_torneo`. Cada entrada debe declarar un
`aviso_vacia`, porque una familia que no emite filas tiene que decir por qué — si no, su
ausencia del ranking se lee como que compitió y perdió. Una familia que falla por una
dependencia ausente deja advertencia y no detiene la corrida.
