# ADR-0011: Descomposición de proyección

## Estado

Aceptado para el refactor local y la compatibilidad de fachadas. No se declara equivalencia
histórica total ni cierre de producción hasta ejecutar los datos y servicios externos oficiales.

**Fecha:** 2026-08-29

## Relación con la documentación existente

Este es el nombre canónico solicitado por la especificación. El archivo
[`0011-descomposicion-proyeccion-y-api-lazy.md`](0011-descomposicion-proyeccion-y-api-lazy.md)
se conserva como antecedente de la API lazy y de las primeras extracciones. No se borra ni se
renombra para preservar la historia del proyecto.

## Contexto

La proyección concentraba en pocos módulos paneles, evidencia, ajuste, modelos, priors,
residuales, replay, relaciones, candidatos, parámetros, horizontes y persistencia. Mover
funciones sin separar responsabilidades podía crear ciclos, imports pesados o cambios silenciosos
en el horizonte, el corte `as-of`, el grano de las filas y los escenarios.

## Decisión

Se descompone por responsabilidad y se mantienen fachadas compatibles en las rutas históricas.
Los módulos internos reciben contratos y datos explícitos; la fachada conserva reexports y
aliases temporales. La API de `analitica.proyeccion` utiliza carga lazy para no activar modelos,
estadística, persistencia o tracking cuando el consumidor solo necesita contratos o funciones
ligeras.

La extracción no activa calibraciones nuevas ni cambia fórmulas. La equivalencia afirmada es la
del estado actual probado con sus contratos actuales; no se afirma equivalencia con cualquier
blob histórico si cambian snapshot, corte, datos o versiones.

## Qué se movió

| Área histórica | Organización actual |
|---|---|
| `proyeccion/fenologico_v1.py` | `proyeccion/fenologico/`: `contratos`, `especificacion`, `panel`, `evidencia`, `ajuste`, `modelos`, `métricas`, `incertidumbre` y `servicio` |
| `proyeccion/hibrido_legacy.py` | `proyeccion/hibrido/`: `macro`, `priors`, `residual`, `proyecciones`, `replay` y `servicio` |
| `proyeccion/relaciones.py` | `relaciones_partes/`: `panel`, `estadistica`, `packing` y `evidencia`, con `ensamblaje.py` para merges auditados |
| `proyeccion/hibrido_parametros_asof.py` | `proyeccion/parametros/`: contratos, normalización, selección, desplazamientos, mezcla, snapshots y ejecución |
| `proyeccion/pronostico_horizonte.py` | Fachada hacia `proyeccion/horizonte/`, con `contratos.py`, `correccion.py`, `evaluacion.py` y la implementación de pronóstico |
| `proyeccion/candidate_preflight.py` y candidatos | `proyeccion/candidatos/`, con fuentes, contratos, snapshots, baselines, cache, evaluación y preflight |
| `proyeccion/gobernanza.py` | `proyeccion/persistencia/`, `infraestructura/` y `tracking.py`; la fachada histórica sigue disponible |
| Flujos reutilizables | `servicios/`, incluyendo routers de horizonte/parámetros, nowcast, replay, turnos, small-data y persistencia |

No se fragmentaron `nucleo/bhattacharya.py` ni `nucleo/clima.py` solo por tamaño. Tampoco se
eliminaron los módulos históricos: su retiro requiere pruebas de consumidores, deprecación y un
baseline versionado.

## API y contratos conservados

Siguen disponibles:

- `analitica.proyeccion` y sus exportaciones lazy;
- `analitica.proyeccion.fenologico_v1`, `hibrido_legacy`, `relaciones`, `gobernanza`,
  `hibrido_parametros_asof` y `pronostico_horizonte`;
- `analitica.proyeccion.macro_legacy`, `componentes`, `ocurrencia`, `motor_proyeccion_semanal`,
  `exportacion` y las demás rutas públicas históricas;
- `analitica.servicios.servicio_bhattacharya`, `analitica.cli:main` y
  `aquanqa-analytics`;
- columnas y orden, fechas, grano campaña/lote/módulo/semana, escenarios, versiones de modelos,
  semántica `as-of`, reglas de fugas temporales, resultados de exportación y contratos SQL.

Los nombres privados que las pruebas o consumidores existentes necesitan se mantienen como
reexports de transición. Las fachadas no deben convertirse en un nuevo lugar para implementar
lógica.

## Pruebas y evidencia

Las pruebas focalizadas ejecutadas durante esta actualización fueron:

```text
python -m pytest packages/analitica/tests/test_fenologico_v1.py packages/analitica/tests/test_hibrido_legacy.py packages/analitica/tests/test_hibrido_parametros_asof_refactor.py packages/analitica/tests/test_pronostico_horizonte.py packages/analitica/tests/test_repositorio_refactor.py -q
52 passed in 55.43s

python -m pytest packages/analitica/tests/test_matriz_relaciones.py packages/analitica/tests/test_nowcast_refactor.py packages/analitica/tests/test_cross_campaign_refactor.py packages/analitica/tests/test_fenologia_honest_refactor.py packages/analitica/tests/test_turno_reingreso_refactor.py packages/analitica/tests/test_small_data_loop_refactor.py packages/analitica/tests/test_replay_persistencia_refactor.py -q
27 passed in 151.53s
```

La regresión local registrada para el checkout fue:

```text
python -m pytest packages/analitica/tests -q       677 passed, 3 skipped
python -m pytest apps/dashboard/tests -q            197 passed
python -m pytest -q                                 944 passed, 3 skipped
python -m ruff check --no-cache ...                 All checks passed
python -m compileall -q packages/analitica apps/dashboard  exit 0
python -m pip check                                 No broken requirements found
wheel analítico                                    304 módulos presentes, 0 bytecode
```

La prueba de horizonte incluye ausencia de lectura de resultados futuros y normalización de
horizontes. No se ejecutaron con recursos reales PostgreSQL, Access/Excel oficial, MLflow remoto
ni Docker. La biblioteca MLflow local no sustituye un servidor o registry, y la prueba
PostgreSQL se omite sin `AQUANQA_TEST_POSTGRES_DSN`.

Además, el estado actual mantiene una diferencia histórica documentada: para el objetivo
`real_kg` no se activa XGBoost en la ruta actual, mientras un blob histórico lo agregaba siempre.
Por eso este ADR no afirma equivalencia histórica total; cualquier cambio de modelo requiere su
propio snapshot, corte, versiones, métricas y aprobación.

## Riesgos

- Un import interno puede volver a depender de una fachada histórica y reintroducir un ciclo.
- Los cambios de horizonte, `as-of` o orden de columnas pueden producir resultados plausibles
  pero incorrectos; las pruebas de contrato deben acompañar cada extracción.
- Los aliases privados alargan la transición y pueden dificultar saber cuál es la implementación
  canónica.
- La descomposición aumenta la superficie de empaquetado; una carpeta nueva omitida del wheel
  rompería solo instalaciones limpias.
- Las advertencias existentes y la falta de integraciones externas limitan lo que puede afirmarse
  sobre producción.

## Método de rollback

Las fachadas permiten mantener consumidores en la versión anterior mientras se investiga una
regresión, pero no reemplazan un artefacto anterior. El procedimiento es:

1. detener la publicación y conservar el checkout para diagnóstico;
2. desplegar el commit/tag o wheel aprobado anterior de la proyección;
3. ejecutar `python -m pytest packages/analitica/tests -q`, los smoke tests de imports públicos y
   las pruebas del dashboard;
4. comparar columnas, fechas, decisiones, excepciones y métricas en el mismo snapshot;
5. corregir o revertir únicamente el bloque extraído antes de reintentar la integración.

No existe en este checkout un commit/tag de rollback dedicado identificable. No se deben borrar
fachadas, usar `git reset --hard` ni limpiar cambios locales para simular la reversión. El equipo
debe versionar el baseline o conservar el wheel anterior antes del despliegue.

## Alternativas descartadas

- Mantener cada modelo en un único módulo monolítico: dificulta probar y razonar sobre cada
  responsabilidad.
- Cambiar la API pública al reorganizar: mezcla migración externa con refactor interno.
- Eliminar las fachadas inmediatamente: rompe imports, pickles y scripts históricos.
- Dividir todos los módulos grandes sin fronteras de dominio: aumenta riesgo sin mejorar la
  comprensión.
