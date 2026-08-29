# Nowcast de cierre semanal adaptativo — 2026-08-26

## Decisión

Se incorpora `NowcastCierreSemanal_v1` como producto histórico aprobado para estimar el cierre de la semana **el miércoles**, después de conocer los kilos reales de lunes y martes.

No sustituye al plan operativo emitido antes de comenzar la semana ni al horizonte de seis semanas. La pantalla Proyección conserva ambas funciones separadas:

- `Plan semanal`: planeamiento previo basado en `ModeloOperativoActual_v1`.
- `Cierre semanal`: actualización intra-semanal basada en `NowcastCierreSemanal_v1`.

R09 continúa siendo una emisión operativa publicada y nunca se utiliza como predictor.

## Motivación

La auditoría mostró que el proceso manual acierta parte de sus ajustes porque incorpora información que la curva biológica congelada no conoce:

- programación y reingreso de lotes;
- cambios de cuadrillas y calendario;
- kilos reales observados al inicio de la semana;
- ajuste del volumen restante durante la semana.

Los ensayos honestos con turnos, días de reingreso, GDD, fenología, parámetros Excel y modelos ML para pocos datos no mejoraron consistentemente el pronóstico previo fuera de muestra. Se rechazaron y no se publicaron.

El único incremento de información que produjo una mejora robusta fue el avance real de lunes y martes. Por eso se modeló como un producto distinto: un **nowcast de cierre**, no un forecast pre-semana.

## Fórmula y entradas

Para cada semana cerrada y cada fundo se utiliza únicamente información disponible hasta el martes:

```text
avance_real_lun_mar
+ volumen_restante_estimado_desde_la_curva_macro_congelada
+ calibración_adaptativa_aprendida_solo_con_semanas_anteriores
= estimación_de_cierre_del_miércoles
```

La calibración se realiza con un estimador robusto y shrinkage jerárquico. Las correcciones están acotadas con el histórico anterior al corte. No se utilizan kilos posteriores al martes, R09, clima futuro observado ni ajustes Excel posteriores.

## Fuente y contrato temporal

- Cosecha real congelada: `.cache/analitica/source-snapshots/BD_AQUANQA_26_snapshot_2026-08-25.accdb`.
- SHA-256 de la copia congelada: `520dadeb...23e58`.
- Último real incluido en esa copia: 21/08/2026.
- R09 de referencia: `C:\Users\CCARRASCAL\Downloads\BD_AQUANQA_26_v2.accdb`.
- SHA-256 de la copia R09: `269E...D1E4`.
- Solo se evaluaron semanas cerradas.
- La semana objetivo utiliza una emisión R09 previa a su inicio para `R09 presemana` y una emisión realizada durante la semana para `R09 ajustado`.

## Resultado del replay

### C2026, 22 semanas cerradas

| Serie | WAPE | Sesgo |
|---|---:|---:|
| `NowcastCierreSemanal_v1` | 10,32 % | +0,17 % |
| Macro congelada | 24,64 % | -12,11 % |
| R09 previo a la semana | 19,47 % | +1,29 % |
| R09 ajustado dentro de la semana | 7,92 % | +2,96 % |

La comparación pareada contra R09 ajustado produjo una diferencia media de 1,93 puntos porcentuales, con intervalo bootstrap 95 % de -2,47 a 6,30. El candidato ganó 8 de 20 semanas comparables. La lectura correcta es **equivalencia estadística**, no superioridad.

En la semana 34:

| Serie | kg |
|---|---:|
| Real cerrado | 849.671 |
| Nowcast miércoles | 924.676 |
| Macro congelada | 674.688 |
| R09 previo a la semana | 704.969 |
| R09 ajustado durante la semana | 873.062 |

## Persistencia y publicación

- `forecast_run.run_id`: 84.
- `dataset_snapshot.snapshot_id`: 74.
- `evaluation_contract_id`: 86.
- `model_series_release.release_id`: 109.
- Producto: `nowcast_cierre_semanal`.
- Uso: `historico`.
- Estado: aprobado para visualización histórica, no promovido como forecast operativo.
- 110 filas persistidas: 22 semanas por cuatro fundos más el total Empresa.
- Los hashes de los baselines permanecieron sin cambios.

La persistencia se realiza en `analytics.weekly_nowcast`; el dashboard consume exclusivamente `reporting.nowcast_cierre_semanal`.

## Controles superados

- Entrenamiento estrictamente anterior a cada semana evaluada.
- Sin R09 como predictor.
- Sin datos reales posteriores al martes.
- Sin semana parcial en métricas.
- Conciliación de cuatro fundos con el total Empresa.
- Sin modificación de las releases de Macro, Ocurrencia ni R09.
- Comparación pareada sobre el mismo calendario semanal.
- Pruebas de repetibilidad, adaptación y guardas por fundo.

## Limitaciones

- Es una estimación de cierre disponible el miércoles, no una decisión tomada antes de iniciar la semana.
- No prueba que el modelo automático de seis semanas haya superado a R09.
- El resultado C2026 todavía necesita validación externa en campañas comparables antes de promoverse.
- La base operativa PostgreSQL no contiene aún kilos de lunes y martes de la semana 35; por tanto no se emite un nowcast actual sin inventar datos.
- El clima y la fenología permanecen como hipótesis analíticas: no se incorporaron porque no mejoraron el replay externo.

## Interpretación operativa

El avance conseguido es concreto pero acotado:

> La plataforma ya puede estimar automáticamente el cierre semanal con información de lunes y martes, mejorar claramente la Macro congelada y quedar estadísticamente al nivel del ajuste intra-semanal R09. La proyección previa de una a seis semanas continúa siendo un problema separado y R09 permanece como referencia operativa.
