# Modelo Fenológico por Componentes y Mesa de Cosecha

**Fecha:** 2026-08-20
**Estado:** implementado y visible como challenger; R09 continúa como proyección oficial.

### Corrección de evaluación y curva operativa

R09 se denomina en la interfaz **forecast operativo vigente**, no modelo científico. Es la
salida publicada por el proceso actual —que incluye la macro legacy y sus ajustes operativos—
y se conserva como baseline de negocio. La cosecha real se obtiene de `stg.v_h01_cosecha` y
no de R09.

La comparación visual no debe enfrentar dos emisiones de fechas distintas como si fueran un
backtest. La página ahora muestra primero la curva real disponible hasta el corte común y,
desde allí, continúa con R09 y `FenologicoComponentes_v1`. La precisión se calcula únicamente
con replay temporal: una emisión se entrena con datos reales anteriores y sus objetivos
posteriores quedan reservados para evaluación.

El modelo fenológico también incorpora al panel as-of el acumulado real del lote, la última
cosecha, los kilos de las últimas cuatro semanas, el número de semanas cosechadas y la última
pasada. Se agregan snapshots de campañas históricas cerradas para no entrenar solo con la
campaña vigente. Estas mejoras aún deben volver a ejecutar el backtest antes de afirmar que
el nuevo modelo supera al forecast operativo.

## Resultado y decisión

Se implementó `FenologicoComponentes_v1` como un modelo nuevo e independiente de R09. El
modelo estima por separado:

1. probabilidad de que ocurra cosecha en el lote-semana;
2. frutos por planta, condicionados a cosecha;
3. peso medio de baya;
4. plantas productivas;
5. volumen semanal directo entrenado con `real_kg` anterior a la emisión;
6. factor de reconciliación visible entre el volumen directo y la descomposición.

```text
kg esperados = volumen directo as-of
factor de reconciliación = kg esperados /
  (P(cosecha) × plantas × frutos/planta × peso_baya_g / 1000)
```

La implementación usa una rejilla lote-semana independiente. R09 no entra como predictor ni
como calendario oculto: se une después de predecir y solo sirve como forecast operativo de
comparación. El volumen directo compite entre familias con validación temporal y solo usa
`real_kg` anterior; el factor no se interpreta como probabilidad ni como efecto agronómico.

En un replay ciego de emisión 2026-06-15, el challenger directo produjo 148.813 kg frente a
165.635 kg reales en la semana 2026-06-22 (sesgo -10,2 %) y 148.813 kg frente a 152.164 kg en
2026-06-29 (sesgo -2,2 %). Es una prueba de desarrollo sobre dos semanas, no todavía un
criterio de promoción; la decisión requiere el backtest rolling-origin completo y sus cortes
externos.

La tabla siguiente pertenece a la corrida 32, anterior a la incorporación del volumen directo
`direct_volume_v2`; se conserva como referencia histórica y no describe la emisión actual.
El backtest completo de la nueva versión debe ejecutarse offline antes de usar sus métricas
para promoción.

| Horizonte | Modelo | n común | WAPE | MASE | Sesgo | Cobertura P10–P90 |
|---|---|---:|---:|---:|---:|---:|
| 1–2 semanas | Fenológico v1 | 3.418 | 92,1 % | 0,649 | -55,7 % | 75,7 % |
| 1–2 semanas | R09 publicado | 3.418 | 127,4 % | 0,898 | +108,3 % | 63,8 % |
| 3–6 semanas | Fenológico v1 | 2.721 | 99,8 % | 0,559 | -58,3 % | 57,8 % |
| 3–6 semanas | R09 publicado | 2.721 | 300,5 % | 1,685 | +289,9 % | 59,2 % |

El challenger de esa corrida reducía WAPE y MASE en el universo común, pero subestimaba el
volumen y no era publicable. La decisión vigente sigue siendo conservar R09 como oficial. No
se reutilizan esos números para declarar ganador al volumen directo v2.

La emisión experimental actual es la corrida 38: 8.080 filas para 808 lotes, semanas
operativas del 24/08/2026 al 26/10/2026 y 4.530.513 kg P50. Todas las fechas objetivo son
lunes. La reconciliación jerárquica cerró sin filas afectadas y con diferencias máximas solo
de precisión numérica (`5,82e-11 kg`). El artefacto auditable es
`data/salida/analytics/project-20260820T185354Z-d37d94c8.zip`.

Estas métricas no significan que R09 sea un buen modelo: revelan que ambos enfoques tienen
problemas opuestos de calibración. El valor actual del modelo nuevo está en haber construido
una base biológica y auditable que ya puede calibrarse por componentes.

## Fuentes y semántica temporal

La arquitectura es Access-first:

```text
Access → extracción de solo lectura → PostgreSQL raw/core/stg
       → panel as-of → modelo → analytics/reporting → dashboard
```

El dashboard no consulta `.accdb` ni Excel directamente. La fuente preferida y el respaldo de
cada familia están declarados en `docs/modelo/08_fuentes_predictivas.json`. Los Excel quedan
limitados a pruebas legacy, conciliación o backfill explícito. Riego solo entra cuando supera
controles de cobertura; nutrición continúa bloqueada por falta de contrato e historia.

Cada objetivo semanal se alinea al lunes operativo aun cuando la emisión ocurra otro día. Una
prueba metamórfica y los contratos as-of impiden que datos posteriores a la emisión modifiquen
una predicción pasada.

## Cómo usa Relaciones y Descubrimientos

Las relaciones no se presentan como causalidad. Dentro de cada fold temporal se evalúan las
features candidatas, rezagos y transformaciones; la evidencia de cada feature se persiste en
`analytics.model_feature_evidence`. Una relación puede permanecer como descubrimiento sin ser
admitida por el modelo si falla muestra, estabilidad, placebo o desempeño fuera de muestra.

En la emisión experimental anterior (corrida 31), los procesos de selección evaluaron y
admitieron:

- frutos/planta: 55 evaluadas, 41 admitidas;
- ocurrencia: 54 evaluadas, 45 admitidas;
- peso: 42 evaluadas, 28 admitidas.

SHAP, ALE, correlaciones y precedencia temporal explican asociaciones predictivas; no se
etiquetan como evidencia causal.

## Rediseño de la Mesa de Cosecha

La página se reorganizó para el trabajo diario del agrónomo:

- abre con la decisión: cuál es oficial, cuál es challenger y si puede publicarse;
- compara R09 y Fenológico v1 en paralelo, sobre universo común;
- deja filtros, semanas y escenario en una franja compacta;
- prioriza el plan semanal y el detalle por lote;
- mueve el simulador a un panel lateral para no obligar a atravesarlo antes de ver el plan;
- separa Plan semanal, Detalle por lote, Poda y campaña y Cómo se calculó;
- conserva trazabilidad, explicación y limitaciones en paneles desplegables;
- incorpora navegación móvil y elimina la barra lateral fija que ocupaba gran parte de la
  pantalla en campo;
- mantiene el flujo borrador → revisión → aprobación, sin permitir publicar el challenger por
  accidente.

Los controles del simulador vuelven a ejecutar sensibilidades guardadas del challenger. No son
factores cosméticos. Los parámetros legacy se mantienen apartados en modo experto.

## Persistencia y rendimiento

La comparación pareada se calcula una vez al terminar el backtest y se guarda en
`analytics.model_comparison_metric`. La vista
`reporting.comparacion_r09_fenologico_pareada` carga el resultado materializado. Su tiempo de
ejecución verificado fue de 0,281 ms; se eliminó el self-join que recalculaba cientos de miles
de predicciones cada vez que se abría la página.

## Validación realizada

- 54 pruebas focalizadas aprobadas, incluidas composición, semana operativa, comparación
  pareada, layouts y operación del dashboard;
- lint de los archivos modificados aprobado;
- reconciliación lote → módulo → fundo → empresa cerrada en la ejecución experimental;
- el dashboard fue revisado a 1440 px y 390 px sin desbordamiento horizontal;
- la comparación persiste igual `n` y volumen real para ambos modelos dentro de cada horizonte.

## Limitaciones abiertas y siguiente trabajo

1. Calibrar ocurrencia y volumen: el challenger subestima 56–58 %.
2. Revisar intervalos: en parte de la emisión P10 queda pegado a P50 por la distribución de
   residuos; no debe comunicarse como intervalo plenamente calibrado hasta corregirlo.
3. Incorporar pronóstico meteorológico histórico en replay, no solo el adaptador futuro.
4. Completar riego por módulo y contrato de nutrición.
5. Resolver el mapeo emisión/versión de R08 para Poda y campaña.
6. Registrar el manifiesto físico del Access autorizado; la interfaz debe seguir mostrando la
   advertencia mientras falte.
7. Reentrenar y revalidar con nuevas campañas antes de cualquier promoción.

No se debe afirmar que `FenologicoComponentes_v1` está listo para uso oficial. Sí está listo
para comparación diaria controlada, diagnóstico de componentes y mejora iterativa.
