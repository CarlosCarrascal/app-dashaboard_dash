# Matriz de fachadas y ventana de compatibilidad

Fecha: 2026-08-29
Alcance: `packages/analitica`, dashboard, comandos, servicios y tests del monorepo.

## Qué es una fachada

Una fachada es un archivo antiguo que conserva un nombre de importación conocido y redirige al
módulo nuevo. No contiene necesariamente una segunda fórmula. Se mantiene para que un script,
un notebook o una integración externa no se rompa mientras los consumidores migran.

## Estado comprobado

| Fachada histórica | Consumidores encontrados | Decisión actual |
|---|---|---|
| `proyeccion/fenologico_v1.py` | `commands/torneo.py`, dashboard histórico, servicios de replay y tests | Mantener |
| `proyeccion/hibrido_legacy.py` | comando de torneo, servicios de replay/evaluación y tests | Mantener |
| `proyeccion/operativo_excel.py` | comando operativo, `excel_assisted` y tests | Mantener |
| `proyeccion/validacion_operativa.py` | comandos, servicios de parámetros y tests | Mantener |
| `proyeccion/parametros_excel.py` | servicios de parámetros y tests | Mantener |
| `proyeccion/relaciones.py` | exportación, comandos y tests | Mantener mientras termina la extracción física |
| `proyeccion/candidate_preflight.py` | scripts y servicios de screening/replay | Mantener; todavía es API de uso activo |
| `proyeccion/candidate_param_delta.py` | servicios de replay y tests | Mantener |
| `proyeccion/candidate_residual_asof.py` | servicio residual y tests | Mantener |
| `proyeccion/candidate_turno_temporal.py` | servicios de turno/reingreso y tests | Mantener |
| `proyeccion/temporal.py` | tests y posibles consumidores externos; ya redirige a `compartido.fechas` | Mantener como compatibilidad |
| `proyeccion/tracking.py` | sin consumidor productivo interno detectado; API externa posible | Mantener hasta la siguiente revisión de uso |
| `proyeccion/infraestructura/serializacion.py` | alias interno sin consumidores productivos | Retirada; serialización canónica en `compartido` |
| `proyeccion/persistencia/serializacion.py` | alias interno sin implementación propia | Retirada; serialización canónica en `compartido` |
| `proyeccion/macro_legacy.py` | tests y API histórica | Mantener |

La búsqueda se hizo sobre los imports de `packages/analitica`, `apps/dashboard`, `etl` y
`domain`. Que una fachada no tenga consumidores internos no demuestra que no exista un notebook,
job o integración externa que la use.

## Ventana de compatibilidad

Las fachadas se conservan durante la versión actual y la siguiente versión menor. Durante ese
periodo:

1. Los consumidores internos nuevos deben importar la implementación agrupada, no la fachada.
2. Los imports históricos se registran en esta matriz y se cubren con pruebas de identidad/API.
3. No se cambia la firma, el nombre ni la identidad de los objetos reexportados.
4. Antes de retirar una fachada se exige cero consumidores runtime internos, aviso de deprecación,
   dos regresiones completas verdes y confirmación de que no hay consumidores externos conocidos.
5. El retiro debe ocurrir en un cambio separado, con rollback versionado.

Las rutas de horizonte y `pronostico_horizonte.py` quedan fuera de esta matriz porque pertenecen
a otro trabajo paralelo y no deben ser modificadas por esta limpieza.

## Actualización de consolidación productiva (2026-08-29)

La migración interna ya fue ejecutada. Los comandos, servicios, scripts y dashboard importan
desde las implementaciones canónicas (`candidatos`, `fenologico`, `hibrido`, `horizonte`,
`operativo`, `parametros`, `persistencia` y `relaciones_partes`). La búsqueda sobre código
productivo devuelve cero imports hacia las fachadas raíz históricas; los imports que permanecen
están confinados a pruebas de compatibilidad o a la propia fachada.

Se retiraron cinco aliases internos sin lógica:

- `proyeccion/candidatos/baselines.py`
- `proyeccion/candidatos/evaluacion.py`
- `proyeccion/candidatos/snapshots.py`
- `proyeccion/infraestructura/serializacion.py`
- `proyeccion/persistencia/serializacion.py`

También se centralizaron en `relaciones_partes/estadistica.py` los helpers estadísticos que
estaban duplicados en `relaciones_partes/packing.py`. La primera limpieza pasó de `120` a `115`
módulos Python. Después se compactaron los micro-módulos internos sin cambiar las rutas de
importación: `compartido` concentra sus utilidades en `utilidades.py`, `operativo` en
`excel.py`, `infraestructura` contiene su función Git directamente y la selección de pesos
vive junto a la mezcla de parámetros. El inventario físico final de `proyeccion` queda en
`104` archivos Python; los aliases de compatibilidad se resuelven en memoria desde los
`__init__.py` y no duplican implementación.

Las fachadas raíz se conservan deliberadamente hasta completar la ventana de compatibilidad:
eliminarlas ahora sí cambiaría imports externos, pickles y notebooks.
