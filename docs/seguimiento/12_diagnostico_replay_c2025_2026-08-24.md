# Diagnóstico del replay C2025

## Conclusión

La lectura anterior de C2025 no era una evaluación completa de la campaña. El dashboard estaba mostrando una ventana parcial de enero–febrero de 2026 y el replay disponible para esa comparación tenía solo 8 semanas objetivo. Esa ventana concentra el tramo final de la campaña, donde el modelo sobreestima el volumen; por eso aparecían WAPE de 78,5 % mensual y 96,9 % semanal.

Se generó y persistió el replay completo en la corrida `78`.

## Evidencia de la corrida completa

| Elemento | Resultado |
|---|---:|
| Campaña | C2025 |
| Semanas objetivo | 51 |
| Primer objetivo | 10/03/2025 |
| Último objetivo | 23/02/2026 |
| Meses evaluados | 12 |
| Cobertura de volumen del híbrido | 100 % |
| Real evaluado | 15.643.519 kg |
| Híbrido ocurrencia v2 | 15.739.499 kg |
| Error total de campaña | 0,6 % |
| WAPE semanal de campaña completa | 20,9 % |
| WAPE mensual | 14,9 % |
| Sesgo de volumen | +0,6 % |

La vista semanal del dashboard permite seleccionar `Todo el histórico`; con esa opción muestra las 51 semanas. Si se deja `Últimas 12 semanas`, el indicador describe únicamente la cola de C2025 y no debe presentarse como precisión de campaña completa.

## Qué ocurrió con R09

La fuente histórica de R09 se corrigió para leer `stg.v_r09_forecast` y excluir variantes (`v2`, `v3`, `EDI`, `oli` y copias). La fuente no está corrupta, pero tampoco cubre toda la campaña C2025: contiene 9 semanas objetivo evaluables, del 05/01/2026 al 02/03/2026, mientras la cosecha real disponible va del 10/03/2025 al 02/03/2026 (48 semanas).

Por eso ahora se separan dos lecturas:

- **WAPE operacional de campaña:** incluye las semanas reales sin emisión como ausencia de cobertura. Para C2025, R09 queda en aproximadamente **93,3 %**, con solo **6,0 % del volumen real cubierto**.
- **WAPE condicionado:** usa únicamente las semanas/lotes donde R09 sí publicó una predicción. Para C2025 es aproximadamente **52,0 %**.

No se rellenan las semanas ausentes con una predicción inventada ni se presenta R09 como si tuviera una campaña completa. La captura antigua con 8 semanas era una lectura parcial; la cifra anterior de ~40,8 % no representa el histórico completo de R09.

La misma revisión muestra que el problema no es uniforme:

| Campaña | Semanas reales | Cobertura R09 | WAPE operacional | Lectura |
|---|---:|---:|---:|---|
| C2024 | 70 | 7,0 % | 92,0 % | R09 incompleto |
| C2025 | 48 | 6,0 % | 93,3 % | R09 incompleto |
| C2026 | 23 | 98,1 % | 7,2 % | R09 comparable en volumen |

Así no se “arregla” R09 de forma indiscriminada: se corrige la reconstrucción histórica y cada campaña conserva su estado real de cobertura.

## Lectura objetiva

- La corrida completa corrige el problema de cobertura y muestra que el híbrido reproduce muy bien el volumen total de C2025.
- El objetivo semanal de 15 % todavía no se cumple: el WAPE semanal completo es 20,9 %.
- El modelo no debe declararse ganador únicamente por el 14,9 % mensual ni por el 0,6 % de error total; la distribución semana a semana y el error lote-semana siguen siendo limitaciones.
- La persistencia y el dashboard ahora distinguen campaña completa, ventana semanal y tramo final.
