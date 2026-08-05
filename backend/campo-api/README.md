# backend/campo-api · la puerta de entrada de los datos nuevos

Servicio FastAPI. Dos clientes, un solo destino:

```
App Flutter (evaluadores)  ──▶┐
                              ├──▶  domain/  ──▶  PostgreSQL (core)
Excel de proyecciones      ──▶┘
   (ingenieros de oficina)
```

Es lo que sustituye al flujo actual —capturar en Excel o AppSheet y que alguien consolide a
mano en Access—: el dato entra validado y queda en `core` casi en tiempo real.

## La app Flutter no vive aquí

Vive en **su propio repositorio** y consume este servicio solo por contrato: el OpenAPI que
FastAPI publica en `/docs`. El ciclo de release de una app móvil —revisión de tiendas, firmas,
versionado de builds— no comparte ritmo con el de un backend de datos (ADR-0006).

"Fácil de identificar" no exige que el código esté en este repo; exige que el contrato esté
publicado.

## Regla del paquete

**Aquí no se decide nada de negocio.** Una ruta recibe, llama a `aquanqa_domain`, devuelve.

El día que aparezca un segundo consumidor —un panel de administración, un socio— no reescribe la
validación de un diámetro imposible: importa la misma de `domain/`. Si una regla acaba viviendo
en un archivo de rutas, está en el sitio equivocado.

Tampoco importa nada de `etl/`. Si esta API necesitara algo de la extracción del Access
histórico, es señal de que esa lógica pertenecía a `domain/` desde el principio.

## Por qué no lleva `pyodbc`

Este paquete se empaqueta en un contenedor **Linux** para AWS, y el driver ODBC de Access solo
existe en Windows. La extracción del histórico se queda en `etl/`, que corre en local. Mismo
lenguaje no significa mismo desplegable — es la razón por la que `etl/` y `backend/` son dos
paquetes y no dos carpetas del mismo.

## Estado

Andamiaje. Sin implementar todavía; es la etapa E9 del plan.

| Archivo | Qué llevará |
|---|---|
| `main.py` | La aplicación FastAPI y su configuración |
| `routes_mediciones.py` | Captura de campo desde Flutter: conteo de flores, calibres, bayas |
| `routes_proyecciones.py` | Subida del Excel de proyecciones ya calibrado |

## Sobre las proyecciones y el Excel

El objetivo **no** es quitarle el Excel al ingeniero. Ese archivo es un simulador: ajusta
parámetros a mano —factor de clima, cuaje, semanas de descarte— hasta que la curva calza con lo
que ve en el campo, y esa flexibilidad es real y necesaria.

Lo que se automatiza primero es solo la **extracción del resultado final**, para que nadie copie
y pegue cifras entre archivos. Llevar la matemática de las macros a `domain/rules/` es una etapa
posterior, y empieza por levantar la fórmula con el ingeniero: eso es descubrimiento de negocio,
no trabajo de código, y suele tardar más que programarlo.

## Levantarlo en local

Cuando exista `main.py`:

```bash
npm run setup                                    # instala domain, etl y este paquete en editable
uvicorn aquanqa_campo_api.main:app --reload      # y el OpenAPI queda en /docs
```
