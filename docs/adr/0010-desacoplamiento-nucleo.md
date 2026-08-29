# ADR-0010: Desacoplamiento del núcleo analítico

## Estado

Aceptado para la carga e importación local del checkout. La integración con infraestructura
externa continúa pendiente de sus pruebas reales.

**Fecha:** 2026-08-29

## Relación con la documentación existente

Este es el nombre canónico solicitado por la especificación. El archivo
[`0010-separacion-nucleo-persistencia-tracking.md`](0010-separacion-nucleo-persistencia-tracking.md)
se conserva como antecedente relacionado con el aislamiento del cálculo, la persistencia y el
tracking. Ambos documentos permanecen disponibles; este registra el desacoplamiento real de
`nucleo` en el checkout actual.

## Contexto

El núcleo debía poder cargar y transformar datos en memoria sin importar durante la inicialización
la integración de floración, poda o librerías pesadas de modelado. La organización histórica
permitía un ciclo conceptual `datos → floracion → poda → datos`, y además mezclaba tipos de datos
con transformaciones. Eso hacía frágil el import inicial y dificultaba probar un contrato pequeño
sin activar todo el pipeline.

## Decisión

Se introdujo `packages/analitica/nucleo/contratos.py` como nivel inferior para los tipos
compartidos `Panel` y `Hallazgo`. Las transformaciones consumen esos tipos, pero el módulo de
contratos no importa `datos`, `floracion` ni `poda` durante su inicialización.

`nucleo/__init__.py` funciona como fachada lazy. `datos.py` importa de forma normal solo las
ventanas y los contratos; sus adaptadores `integrar_floracion` e `integrar_poda` hacen el import
local cuando se invoca la operación, no al importar el módulo. Esto elimina el ciclo de carga sin
prometer que una ejecución que realmente integra floración o poda pueda prescindir de esas
transformaciones.

## Qué se movió

- `Panel` y `Hallazgo` se movieron a `nucleo/contratos.py`.
- Las operaciones de ventanas/rolling se organizaron en `nucleo/ventanas.py`; `datos.py`
  conserva aliases históricos para sus helpers privados.
- La resolución de símbolos públicos se centralizó en el mapa lazy de `nucleo/__init__.py`.
- `datos.py` conserva wrappers de integración bajo demanda para `floracion.py` y `poda.py`.
- `clima.py`, `evaluacion.py`, `informe.py`, `exportar.py`, `modelo.py` y
  `bhattacharya.py` permanecen cohesivos donde no había una frontera segura demostrada. No se
  dividieron por tamaño ni se alteraron sus fórmulas.

## API y contratos conservados

Se preservan:

- `analitica.nucleo.Panel` y `analitica.nucleo.Hallazgo`;
- `analitica.nucleo.datos.Panel`, `analitica.nucleo.datos.Hallazgo`, `cargar_panel`,
  `integrar_floracion` e `integrar_poda`;
- `analitica.nucleo.floracion`, `analitica.nucleo.poda`, `analitica.nucleo.clima` y los
  nombres lazy de evaluación, informe y modelo;
- la identidad histórica `Panel.__module__ == "analitica.nucleo.datos"`, necesaria para
  pickles e introspección de consumidores existentes;
- columnas, grano módulo-semana, reglas de agregación, nulos y unidades del panel.

El módulo de contratos solo usa `pandas` bajo `TYPE_CHECKING`; por ello el contrato no carga
transformaciones al importarse.

## Pruebas y evidencia

Las pruebas focalizadas ejecutadas durante esta actualización fueron:

```text
python -m pytest packages/analitica/tests/test_nucleo_contratos.py packages/analitica/tests/test_nucleo_ventanas.py packages/analitica/tests/test_fronteras_arquitectura.py -q
30 passed in 5.20s
```

La regresión local registrada para el mismo checkout fue:

```text
python -m pytest packages/analitica/tests -q       677 passed, 3 skipped
python -m pytest apps/dashboard/tests -q            197 passed
python -m pytest -q                                 944 passed, 3 skipped
python -m compileall -q packages/analitica apps/dashboard  exit 0
python -m ruff check --no-cache ...                 All checks passed
```

Estas pruebas demuestran el desacoplamiento de inicialización y la compatibilidad local; no
demuestran una integración con PostgreSQL, Access/Excel oficial, MLflow remoto o Docker. La
prueba focalizada de PostgreSQL permanece omitida cuando no existe `AQUANQA_TEST_POSTGRES_DSN`.

## Riesgos

- Un wrapper lazy puede ocultar un error hasta la primera llamada; por eso se prueban tanto el
  import limpio como la integración concreta.
- Cambiar el módulo de una dataclass puede romper pickles, por lo que se conserva explícitamente
  la ruta histórica de `Panel`.
- Un import nuevo desde `datos` hacia `floracion` o `poda` durante la inicialización podría
  reintroducir el ciclo.
- El desacoplamiento del import no elimina las dependencias de ejecución de las funciones que
  realmente usan modelos, estadísticas o archivos externos.

## Método de rollback

Se conserva la fachada histórica mientras se compara cada etapa. Si una extracción rompe un
consumidor:

1. detener el despliegue;
2. restaurar el commit/tag o wheel aprobado anterior para `nucleo`;
3. ejecutar los imports históricos y
   `python -m pytest packages/analitica/tests/test_nucleo_contratos.py packages/analitica/tests/test_nucleo_ventanas.py -q`;
4. aislar la corrección en `contratos.py`, `ventanas.py` o la fachada, sin cambiar las
   transformaciones científicas.

El checkout actual no tiene un commit/tag de rollback dedicado identificado. No se debe usar
`git reset --hard` ni borrar cambios no versionados; el rollback operativo exige primero un
baseline versionado o un wheel anterior verificable.

## Alternativas descartadas

- Mantener `Panel` y `Hallazgo` dentro de `datos.py`: conserva la dependencia que originó el
  ciclo.
- Importar `floracion` y `poda` al cargar `datos`: hace frágil cualquier uso del panel.
- Dividir todos los módulos por número de líneas: aumenta el acoplamiento sin una frontera de
  dominio demostrada.
