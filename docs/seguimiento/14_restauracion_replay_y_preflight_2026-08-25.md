# Restauración del replay certificado y ciclo acelerado

Fecha: 2026-08-25
Estado: implementado y verificado.

## Problema corregido

Las corridas 81–83 terminaron técnicamente, pero recalcularon series baseline con la
parametrización experimental de `HibridoParametrosAsOf_v1`. El dashboard escogía la última
corrida exitosa por campaña y, por ello, podía reemplazar resultados previamente validados.
Además, una semana parcial podía entrar en precisión y R09 podía usar una emisión realizada
dentro de la misma semana objetivo.

No se borraron las corridas. Quedaron inactivas y rechazadas para auditoría.

## Contrato y releases

Se añadieron:

- `analytics.evaluation_contract`: congela semanas cerradas, universo, emisiones elegibles,
  denominador real y hashes;
- `analytics.model_series_release`: autoriza qué `run_id` exacto puede verse como histórico o
  referencia;
- vistas `reporting` que solo exponen releases aprobadas;
- estados separados para finalización técnica, aprobación y publicación.

El dashboard ya no busca “la última corrida exitosa”. Si no existe una release aprobada se
detiene sin consultar ni sustituir datos mutables.

Releases certificadas:

| Campaña | Run | Series aprobadas | Contrato |
|---|---:|---|---|
| C2026 | 76 | MacroLegacy, Híbrido ocurrencia v2, R09 | 21 semanas comparables, 23/03–16/08/2026 |
| C2025 | 78 | MacroLegacy, Híbrido ocurrencia v2 | 51 semanas comparables, 10/03/2025–01/03/2026 |
| C2024 | — | ninguna | cobertura aún no certificada |

R09 C2025 no se certificó como campaña completa porque solo tiene ocho semanas comparables.

Los contratos son ventanas comparables, no una declaración de cobertura biológica absoluta:
C2026 deja fuera 19.666 kg reales anteriores al inicio común y C2025 deja fuera 11.306 kg del
tramo final posterior a su última semana común. El dashboard usa ahora el rótulo `ventana
comparable` y muestra el rango exacto; no denomina esos totales “campaña completa”.

## Métricas independientes

Sobre releases aprobadas y un único contrato por campaña:

| Campaña | Serie | WAPE semanal | MASE | Sesgo | Cobertura volumen |
|---|---|---:|---:|---:|---:|
| C2026 | Híbrido ocurrencia v2 | 20,00 % | 0,735 | −3,28 % | 100 % |
| C2026 | R09 publicado | 21,23 % | 0,780 | +5,57 % | 80,92 % |
| C2026 | MacroLegacy | 25,60 % | 0,941 | −10,11 % | 100 % |
| C2025 | Híbrido ocurrencia v2 | 20,93 % | 0,995 | +0,61 % | 100 % |
| C2025 | MacroLegacy | 36,36 % | 1,729 | −9,98 % | 100 % |

El híbrido v2 mejora el volumen semanal agregado, pero no reemplaza R09: en C2026 gana 8 de
21 semanas, R09 gana 13; R09 también tiene menor RMSSE y menor WAPE lote-semana. No existe una
segunda campaña con R09 completo sobre el mismo contrato.

## Reglas temporales

- Solo es evaluable una semana cuyo domingo esté dentro del watermark validado.
- Con H01 disponible hasta 18/08, la semana 17–23/08 se muestra como parcial y no entra en KPI.
- Toda emisión debe cumplir `fecha_emision < lunes_objetivo`.
- La semana 34 de R09 usa S33; S34 es nowcast, no forecast previo.
- Todos los lotes de una semana usan una sola emisión coherente.

## Preflight candidate-only

`candidate_preflight.py` y `persistir_hibrido_parametros_asof.py` separan candidato de
baselines. Un challenger no recalcula ni copia Macro, Ocurrencia o R09. Se usa caché local para
evitar reconstruir el panel y no se persiste antes de superar contrato y calidad.

Las referencias del CLI ya no son libres: deben corresponder exactamente a releases activas,
aprobadas, certificadas y pertenecientes a un mismo `evaluation_contract_id`. El cierre del
contrato prevalece sobre el máximo mutable de H01, por lo que la llegada de una semana parcial
no amplía silenciosamente el denominador del preflight.

El preflight actual de `HibridoParametrosAsOf_v1` fue rechazado sin persistencia:

- WAPE: 60,24 %;
- sesgo: +59,29 %;
- Macro congelada comparable: WAPE 17,36 %;
- deterioro en horizontes 1, 2, 4 y 6;
- cobertura: 100 %.

Run 73 se usa únicamente como benchmark congelado full-horizon para screening; no es una
release del dashboard. Su contrato separado es el 67, cerrado al 16/08/2026 y restringido a
los horizontes 1, 2, 4 y 6. Run 76 es la release histórica aprobada, pero solo contiene
horizonte 1 y por eso no se reutiliza artificialmente para evaluar horizontes que no emitió.

La preparación inicial del snapshot Parquet tardó 45,7 segundos y se ejecuta una sola vez por
contrato. Con el snapshot de fuente y el candidato en caché, repetir el preflight tarda 6,5
segundos. El baseline se consulta solo para las emisiones y horizontes del micro-replay, no se
recargan sus aproximadamente 180 mil predicciones completas.

## Loop acelerado

Se añadió `rapid_candidate_loop.py` y el comando `buscar_candidatos_replay`. Ejecuta hasta 26
configuraciones, successive halving en tres rondas, selecciona con C2025 y valida externamente
en C2026. Es de solo lectura y siempre devuelve `publicable=false`; cualquier finalista debe
pasar después el replay completo y la revisión por fundo.

Primera ejecución:

- duración: 11 segundos;
- mejor en C2025: mezcla fija con peso Macro 0,40;
- WAPE C2025: 18,75 %;
- WAPE C2026 externo: 20,71 %;
- mejora C2026 frente a Macro: 19,10 %;
- deterioro C2026 frente a Híbrido ocurrencia v2: 3,53 %.

Resultado: rechazado, no persistido y no publicado. El loop confirmó que una ganancia de
desarrollo no constituye una mejora nueva si no supera al mejor challenger congelado.

## Dashboard

- El selector contiene campañas concretas; no existen `Todas las campañas`, `Campaña más
  reciente`, `__todas__` ni `__ultima__`.
- Se selecciona por defecto la campaña comparable con el cierre real más reciente.
- Los modelos rechazados quedan ocultos.
- Las series se resuelven dentro de la campaña seleccionada: C2025 no ofrece R09 porque no
  existe una release R09 aprobada bajo su contrato comparable; C2026 sí lo conserva.
- El replay se carga de forma diferida; la primera lectura queda en caché por cinco minutos.
- El real histórico se deriva del contrato congelado y no de la tabla H01 mutable.
- La operación está anclada explícitamente a C2026/run 65; una corrida exitosa más reciente no
  puede desplazarla sin una release operativa aprobada.
- Las filas de una serie aprobada y la identidad/hashes de su release quedan protegidos por
  triggers. Solo se admite retirar una release antes de promover otra.

## Archivos principales

- `db/sql/80_analytics/010_modelo.sql`
- `db/sql/80_analytics/020_reporting.sql`
- `db/sql/90_checks/030_analytics.sql`
- `packages/analitica/scripts/certificar_releases_replay.py`
- `packages/analitica/proyeccion/candidate_preflight.py`
- `packages/analitica/proyeccion/rapid_candidate_loop.py`
- `packages/analitica/scripts/buscar_candidatos_replay.py`
- `apps/dashboard/servicios/proyeccion.py`
- `apps/dashboard/pages/analitica/proyeccion_domain.py`
- `apps/dashboard/pages/analitica/proyeccion_callbacks.py`
- `apps/dashboard/pages/analitica/proyeccion_views.py`

## Interpretación final

La infraestructura ya impide que una corrida experimental cambie los KPI publicados. El mejor
challenger certificado sigue siendo `HibridoOcurrenciaOnline_v2` para horizonte 1. No se
encontró una mejora sustancial nueva y `HibridoParametrosAsOf_v1` continúa rechazado.
