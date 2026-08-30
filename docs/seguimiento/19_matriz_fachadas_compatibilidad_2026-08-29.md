# Matriz de fachadas y ventana de compatibilidad

Fecha: 2026-08-29
Alcance: `packages/analitica`, dashboard, comandos, servicios y tests del monorepo.

## Qué es una fachada

Una fachada es un archivo antiguo que conserva un nombre de importación conocido y redirige al
módulo nuevo. No contiene necesariamente una segunda fórmula. En este repositorio no se
encontraron notebooks ni jobs programados; la confirmación del propietario tampoco identificó
integraciones externas que dependan de estas rutas.

## Estado comprobado

| Fachada histórica | Consumidores encontrados | Decisión actual |
|---|---|---|
| `proyeccion/fenologico_v1.py` | usos internos migrados a `fenologico/` | Retirada el 2026-08-29 |
| `proyeccion/hibrido_legacy.py` | usos internos migrados a `hibrido/` | Retirada el 2026-08-29 |
| `proyeccion/operativo_excel.py` | usos internos migrados a `operativo/` | Retirada el 2026-08-29 |
| `proyeccion/validacion_operativa.py` | usos internos migrados a `operativo/` | Retirada el 2026-08-29 |
| `proyeccion/parametros_excel.py` | servicios de parámetros y tests | Mantener |
| `proyeccion/relaciones.py` | usos internos migrados a `relaciones_partes/` | Retirada el 2026-08-29 |
| `proyeccion/candidate_preflight.py` | usos internos migrados a `candidatos/` | Retirada el 2026-08-29 |
| `proyeccion/candidate_param_delta.py` | usos internos migrados a `parametros/` | Retirada el 2026-08-29 |
| `proyeccion/candidate_residual_asof.py` | servicio residual y tests | Mantener |
| `proyeccion/candidate_turno_temporal.py` | usos internos migrados a `candidatos/` | Retirada el 2026-08-29 |
| `proyeccion/temporal.py` | usos internos migrados a `compartido/` | Retirada el 2026-08-29 |
| `proyeccion/tracking.py` | usos internos migrados a `persistencia/mlflow.py` | Retirada el 2026-08-29 |
| `proyeccion/infraestructura/serializacion.py` | alias interno sin consumidores productivos | Retirada; serialización canónica en `compartido` |
| `proyeccion/persistencia/serializacion.py` | alias interno sin implementación propia | Retirada; serialización canónica en `compartido` |
| `proyeccion/macro_legacy.py` | usos internos migrados a `hibrido/macro.py` | Retirada el 2026-08-29 |

La búsqueda se hizo sobre los imports de `packages/analitica`, `apps/dashboard`, `etl` y
`domain`, incluyendo imports absolutos, relativos y dinámicos. El resultado final fue cero
consumidores internos de las fachadas retiradas.

## Ventana de compatibilidad (cerrada)

La ventana se cerró en este cambio porque el propietario confirmó que no usa notebooks, jobs ni
integraciones externas para estas rutas, y la auditoría encontró cero consumidores internos.
Las reglas aplicadas fueron:

1. Los consumidores internos nuevos deben importar la implementación agrupada, no la fachada.
2. Los imports históricos se registran en esta matriz y se cubren con pruebas de identidad/API.
3. No se cambia la firma, el nombre ni la identidad de los objetos reexportados.
4. Antes de retirar una fachada se exige cero consumidores runtime internos, aviso de deprecación,
   dos regresiones completas verdes y confirmación de que no hay consumidores externos conocidos.
5. El retiro ocurre en un cambio separado y queda respaldado por un checkpoint versionado.

Las rutas de horizonte y `pronostico_horizonte.py` quedan fuera de esta matriz porque pertenecen
a otro trabajo paralelo y no deben ser modificadas por esta limpieza.

## Actualización de consolidación productiva (2026-08-29)

La migración interna ya fue ejecutada. Los comandos, servicios, scripts y dashboard importan
desde las implementaciones canónicas (`candidatos`, `fenologico`, `hibrido`, `horizonte`,
`operativo`, `parametros`, `persistencia` y `relaciones_partes`). La búsqueda sobre código
productivo devuelve cero imports hacia las fachadas raíz históricas.

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
vive junto a la mezcla de parámetros. El inventario físico previo de `proyeccion` era de `104`
archivos Python. Tras retirar 13 fachadas raíz, el inventario actual es de `91` archivos Python
(`32` en la raíz y `59` dentro de paquetes); las implementaciones reales permanecen dentro de
sus paquetes canónicos.

## Resultado del retiro (2026-08-29)

Se eliminaron las 13 fachadas raíz enumeradas arriba. `candidate_residual_asof.py` permanece
porque es implementación real, y `pronostico_horizonte.py` más `horizonte/` permanecen fuera de
este cambio por la validación paralela indicada al inicio del documento.

Regresión completa posterior al retiro:

```text
python -m pytest -q    943 passed, 3 skipped
```
