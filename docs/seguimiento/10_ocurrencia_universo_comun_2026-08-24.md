# Persistencia de OcurrenciaOnline sobre universo común

## Corrida

- `run_id`: 75
- `snapshot_id`: 40
- Estado: `succeeded`
- Modelo híbrido: `HibridoOcurrenciaOnline_v1`
- Versión: `hurdle_histgb_online_fund_equal_blend_v1`
- Campañas: C2024, C2025 y C2026
- Horizonte: operativo corto, 1 semana; banda persistida: `operativo`

## Universo

La corrida toma únicamente la intersección evaluable de:

```text
campaña × lote_id × semana objetivo
```

Debe existir simultáneamente en R09 publicado y MacroLegacy, con cosecha real
disponible. Se reutilizan las corridas MacroLegacy validadas 71, 72 y 73 para
no recalibrar la macro ni cambiar el snapshot.

Resultado:

- 5.365 lote-semana en el universo R09–Macro.
- 5.005 lote-semana evaluables por OcurrenciaOnline después de 5 semanas de
  calentamiento.
- 42 semanas en el universo común.
- 37 semanas evaluadas por OcurrenciaOnline.
- Cero duplicados por modelo–campaña–lote–semana.

El calentamiento no se rellena con ceros: esas primeras cinco semanas quedan
como no evaluables para el modelo online.

## Métricas persistidas

En el universo pareado de 5.005 lote-semana:

| Modelo | WAPE | MASE | MAE kg | Sesgo |
|---|---:|---:|---:|---:|
| R09 publicado | 46,15 % | 0,710 | 373,80 | +9,47 % |
| HibridoOcurrenciaOnline_v1 | 53,31 % | 0,821 | 431,85 | −23,69 % |

Estas cifras son la comparación estricta lote-semana sobre el mismo universo;
no deben mezclarse con el 14,8 % de la prueba anterior, que usó únicamente
ocho cortes C2026 y un resumen semanal de otro run.

## Dashboard

La serie histórica inicial se cambió a `HibridoOcurrenciaOnline_v1`. El servicio
lee la última corrida exitosa y ahora debe ofrecer C2024, C2025 y C2026, además
de “Campaña más reciente” y “Todas las campañas”.

R09 continúa etiquetado como referencia publicada. OcurrenciaOnline continúa
como experimental; la corrida no autoriza promoción a modelo oficial.
