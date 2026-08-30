# ADR-0015: Arquitectura actual del paquete analítico

## Estado

Aceptado para el checkout `codex/refactor-analitica`.

**Fecha:** 2026-08-30

## Decisión

`packages/analitica` se organiza por la responsabilidad que cumple cada pieza, no por
el nombre de una técnica ni por el tamaño de un archivo:

```text
analitica/
├── dominio/                 Qué significa el dato y cómo calcula el modelo
│   ├── modelos/             Familias que producen una predicción
│   │   ├── fenologico/      Modelo basado en desarrollo fenológico
│   │   ├── hibrido/         Macro + corrección residual
│   │   ├── ocurrencia.py    Probabilidad de que haya cosecha
│   │   ├── componentes.py   Frutos, peso e identidad del rendimiento
│   │   └── challengers.py   Modelos retadores comparables
│   ├── evaluacion/          Métricas, calidad, evidencia y reconciliación
│   └── nucleo/              Análisis agronómico reutilizable y contratos históricos
├── aplicacion/              Qué proceso se ejecuta y en qué orden
│   ├── procesos/            Nowcast, backtest, torneo y búsqueda de candidatos
│   ├── parametros/           Lectura, normalización y aplicación de parámetros
│   ├── operativo/           Flujo de lectura y construcción desde Excel
│   └── servicios/            Flujos reutilizables y orquestaciones existentes
├── infraestructura/         Base de datos, fuentes, persistencia y MLflow
├── interfaces/               CLI, scripts, exportación y visualizaciones
└── proyeccion/               Entrada pública pequeña y estable
    └── horizonte/            Corrección y evaluación por plazo de pronóstico
```

## Por qué `nowcast` no está dentro de `modelos`

Un modelo transforma variables de entrada en una estimación. El nowcast actualiza una
estimación cuando todavía solo hay una parte de la semana observada —por ejemplo, lunes
y martes—, reconcilia el total de la empresa y lo reparte entre fundos. Puede usar un
modelo, pero no es una familia de modelo por sí mismo. Por eso vive en
`aplicacion/procesos/nowcast.py`.

La misma regla se aplica a `horizonte`: 1–2, 3–6 y 7–10 semanas describen el uso y la
validación temporal del pronóstico; no describen una familia estadística. Vive bajo
`proyeccion/horizonte`, como frontera estable, mientras termina su validación específica.

## Regla para decidir si se crea otro archivo

Se crea un archivo solo cuando existe una responsabilidad que se puede nombrar y probar
de forma independiente. Se conserva unido cuando separar produciría dos fragmentos que
siempre deben cambiarse juntos. Por esa razón:

- `dominio/modelos/hibrido/` sí tiene varios módulos: macro, priors, residual, composición
  y replay son responsabilidades distintas de una misma familia.
- `dominio/modelos/fenologico/` sí tiene varios módulos: contrato, panel, ajuste, evidencia,
  métricas e incertidumbre tienen pruebas y cambios independientes.
- `catalogos.py` permanece como un catálogo declarativo único. Partir etiquetas, glosarios,
  valores y formatos en varios archivos aumentaría el desorden visual sin crear una nueva
  regla de negocio.
- `dominio/nucleo/clima.py`, `bhattacharya.py` y `aplicacion/parametros/candidate_param_delta.py`
  se mantienen como unidades algorítmicas cohesivas. Su tamaño se revisa con una tabla de
  responsabilidades antes de cualquier extracción; no se dividen mecánicamente.

## Fachadas y compatibilidad

Una fachada es un archivo pequeño que conserva una ruta de importación antigua y reexporta
la implementación canónica. No contiene una segunda implementación. Se mantiene solo si
hay un consumidor dentro del repositorio o si la ruta forma parte de una API pública
documentada. En el checkout actual se comprobaron consumidores internos para `config`,
`nucleo`, `visualizaciones`, `servicios` y las entradas de `proyeccion`.

La refactorización interna está terminada aunque algunas fachadas sigan presentes: eso no
significa que haya que esperar para usar la nueva arquitectura. Su eliminación es una
decisión posterior y explícita porque un consumidor externo no puede descubrirse buscando
solo en este repositorio. Antes de eliminarlas se debe migrar el dashboard, publicar una
deprecación durante una versión y comprobar imports públicos, scripts y pickles. Hasta
entonces, la fachada es una capa de compatibilidad deliberada, no código temporal.

## Residuos que no forman parte del paquete

`__pycache__`, `.pytest_cache`, `.ruff_cache`, `build`, `dist*`, `*.egg-info`, `node_modules`
y `.pyc` son salidas regenerables y se eliminan del checkout. Se conservan de manera
explícita los wheels, `mlflow.db` y las evidencias de auditoría acordadas. `mlruns` también
se considera estado de tracking, no caché de Python.

## Verificación

La estructura de `proyeccion` queda protegida por
`packages/analitica/tests/test_fronteras_arquitectura.py`: la raíz contiene exactamente
`__init__.py` y `pronostico_horizonte.py`, y las familias de modelos no se confunden con
los procesos. Las pruebas, Ruff, `compileall` y el contenido del wheel se ejecutan con el
Python del usuario mediante `python -m`.
