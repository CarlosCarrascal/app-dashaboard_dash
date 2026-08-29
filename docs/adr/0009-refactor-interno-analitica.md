# ADR-0009: Refactor interno de analítica

## Estado

Aceptado para el checkout actual y verificado localmente. El cierre de producción queda
pendiente de las compuertas externas indicadas más abajo.

**Fecha:** 2026-08-29

## Relación con la documentación existente

Este es el nombre canónico solicitado por la especificación. El archivo
[`0009-refactor-interno-compatible.md`](0009-refactor-interno-compatible.md) se conserva como
antecedente: describe la misma estrategia inicial, pero no se elimina ni se sustituye para no
perder decisiones previas.

## Contexto

`packages/analitica` reunía en módulos grandes los cálculos, contratos de datos, persistencia,
tracking, comandos, scripts y flujos consumidos por el dashboard. Una modificación transversal
podía romper imports históricos, columnas, fórmulas, reglas temporales, exportaciones o
consultas SQL aunque el cambio pareciera solamente organizativo.

La especificación exige que el interior sea más entendible sin cambiar el comportamiento
observable. Por eso la unidad de migración es una responsabilidad, no un simple archivo: cada
extracción conserva una fachada en la ruta anterior y se valida antes de retirar duplicaciones.

## Decisión

Se adopta una refactorización gradual y compatible. Las rutas históricas siguen siendo la
frontera pública; las implementaciones nuevas viven en módulos internos cohesivos. Los scripts
son lanzadores de servicios, las dependencias opcionales se activan solo en las funciones que
las necesitan y el empaquetado declara explícitamente las nuevas subcarpetas.

No se cambian fórmulas, modelos, versiones, escenarios, reglas `as-of`, nombres de columnas,
unidades, valores nulos, tablas SQL ni contratos de exportación. Los módulos legacy permanecen
como fachadas o antecedentes mientras existan consumidores que dependan de ellos.

## Qué se movió

El estado actual del checkout contiene estas extracciones principales:

| Fachada o área histórica | Implementación organizada |
|---|---|
| `packages/analitica/config.py` | `catalogos.py`, para catálogos, etiquetas, glosario y parámetros declarativos |
| `packages/analitica/cli.py` | `commands/`, conservando `main()` y los ocho comandos |
| `proyeccion/fenologico_v1.py` | `proyeccion/fenologico/`, con contratos, panel, evidencia, modelos, ajuste, métricas, incertidumbre y servicio |
| `proyeccion/hibrido_legacy.py` | `proyeccion/hibrido/`, con macro, priors, residuales, proyecciones, replay y servicio |
| `proyeccion/relaciones.py` | `relaciones_partes/` y `ensamblaje.py`, para panel, estadística, packing y evidencia |
| `proyeccion/gobernanza.py` | `infraestructura/`, `persistencia/` y `tracking.py`, manteniendo la fachada histórica |
| `proyeccion/hibrido_parametros_asof.py` | `proyeccion/parametros/`, con contratos, selección, normalización, desplazamientos, mezcla, snapshots y ejecución |
| Flujos de aplicación repetidos | `servicios/`, incluyendo nowcast, cross-campaign, fenología honesta, turno/reingreso, replay, persistencia, pequeños datos, horizontes y lectura de parámetros Excel |
| Scripts | `analitica.scripts`, sin imports entre scripts; cada módulo conserva ejecución mediante `python -m` |

También se ajustaron el empaquetado de setuptools y la compuerta analítica de
[`.github/workflows/python.yml`](../../.github/workflows/python.yml). La organización no implica
que cada módulo grande deba fragmentarse: `nucleo/clima.py` y `nucleo/bhattacharya.py` siguen
cohesivos porque no se demostró una frontera segura adicional.

## API y contratos conservados

Se mantienen las rutas y símbolos públicos siguientes:

- `analitica.proyeccion` y sus fachadas históricas `fenologico_v1`, `hibrido_legacy`,
  `relaciones`, `gobernanza` y `pronostico_horizonte`;
- `analitica.nucleo`, `analitica.visualizaciones.graficos` y
  `analitica.servicios.servicio_bhattacharya`;
- `analitica.cli:main` y el entry point `aquanqa-analytics`;
- los scripts invocados como `python -m analitica.scripts.<modulo>`;
- nombres, orden y tipos de columnas, unidades, nulos, escenarios, versiones de modelo,
  semántica `as-of`, rutas de exportación, SQL, tablas y contratos del dashboard.

Los aliases privados que consumidores históricos ya utilizaban se conservan temporalmente como
reexports. No se consideran una API nueva y no se retirarán sin pruebas de consumidores y una
deprecación explícita.

## Pruebas y evidencia

La siguiente evidencia corresponde al checkout actual. Las cifras de las suites completas son
la última regresión local registrada el 2026-08-29; las pruebas focalizadas se repitieron durante
esta actualización documental:

```text
python -m pytest packages/analitica/tests -q       677 passed, 3 skipped
python -m pytest apps/dashboard/tests -q            197 passed
python -m pytest domain etl -q                      64 passed
python -m pytest -q                                 944 passed, 3 skipped
python -m ruff check --no-cache ...                 All checks passed
python -m compileall -q ...                         exit 0
python -m pip check                                 No broken requirements found
python -m analitica.cli --help                      correcto
ayuda de 46 scripts mediante python -m              correcta
wheel analítico                                    304 módulos presentes, 0 bytecode
```

Las pruebas focalizadas repetidas ahora fueron:

```text
python -m pytest packages/analitica/tests/test_nucleo_contratos.py packages/analitica/tests/test_nucleo_ventanas.py packages/analitica/tests/test_fronteras_arquitectura.py -q
30 passed

python -m pytest packages/analitica/tests/test_fenologico_v1.py packages/analitica/tests/test_hibrido_legacy.py packages/analitica/tests/test_hibrido_parametros_asof_refactor.py packages/analitica/tests/test_pronostico_horizonte.py packages/analitica/tests/test_repositorio_refactor.py -q
53 passed

python -m pytest packages/analitica/tests/test_matriz_relaciones.py packages/analitica/tests/test_nowcast_refactor.py packages/analitica/tests/test_cross_campaign_refactor.py packages/analitica/tests/test_fenologia_honest_refactor.py packages/analitica/tests/test_turno_reingreso_refactor.py packages/analitica/tests/test_small_data_loop_refactor.py packages/analitica/tests/test_replay_persistencia_refactor.py -q
27 passed
```

El volumen de warnings sigue visible: la última suite raíz registró 54.545. No se ocultó ni se
convirtió artificialmente en éxito. No se ejecutaron en este entorno PostgreSQL real, libros
oficiales Access/Excel con `pyodbc`, un servidor/registry MLflow, Docker con daemon disponible ni
un lockfile transitivo; por tanto este ADR no afirma esos gates.

## Riesgos

- Las fachadas y aliases pueden conservar acoplamientos históricos y hacer que una dependencia
  inversa reaparezca en una extracción futura.
- Las 54.545 advertencias pueden ocultar una regresión si no se clasifican y se controla un
  presupuesto incremental.
- `constraints-analitica.txt` fija dependencias directas, pero no demuestra resolución transitiva
  con hashes ni una política única entre Python local, CI y Docker.
- Las rutas opcionales de PostgreSQL, Access/Excel, MLflow y Docker no tienen evidencia de
  integración real en este checkout.
- Más archivos facilitan la revisión, pero aumentan el número de superficies que deben incluirse
  en el empaquetado y en las pruebas de imports.

## Método de rollback

La fachada no es por sí sola un rollback. Antes de publicar se debe conservar un commit, tag o
wheel aprobado del estado anterior. Si se detecta una regresión:

1. detener la publicación del checkout refactorizado;
2. desplegar el commit/tag o wheel anterior, sin eliminar los cambios locales del usuario;
3. ejecutar `python -m pytest packages/analitica/tests -q`, las pruebas de dashboard y los smoke
   tests de imports/CLI;
4. comparar el fallo con el diff de la extracción y corregirlo en una nueva etapa aislada.

Este checkout no contiene un commit/tag de rollback dedicado identificable. No se usa
`git reset --hard` ni se borra el árbol de trabajo para simular rollback; mientras no exista un
baseline versionado, el equipo debe crear ese baseline antes de publicar.

## Alternativas descartadas

- Reescribir todo el paquete en una sola operación: mezcla causas de regresión y dificulta el
  rollback.
- Cambiar nombres públicos al mismo tiempo que se reorganiza: fuerza migraciones externas que no
  son necesarias.
- Eliminar inmediatamente los módulos legacy: rompería imports y pickles de consumidores
  existentes.
