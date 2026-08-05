"""API de campo: la puerta por la que entran los datos nuevos a la plataforma.

Dos clientes, un solo destino:

    App Flutter (evaluadores) ──▶┐
                                 ├──▶ domain/ ──▶ PostgreSQL (core)
    Excel de proyecciones     ──▶┘
       (ingenieros de oficina)

La app Flutter vive en **su propio repositorio** y consume este servicio solo por contrato
(el OpenAPI que FastAPI publica). El ciclo de release de una app móvil —revisión de tiendas,
firmas, versionado de builds— no comparte ritmo con el de un backend de datos, y mezclarlos en
el mismo repo frena a los dos (ADR-0006).

Regla de este paquete: **aquí no se decide nada de negocio.** Un archivo de rutas recibe la
petición, llama a `aquanqa_domain` y devuelve la respuesta. Cuando aparezca un segundo
consumidor —un panel de administración, un socio— no reescribe la validación de un diámetro
imposible: importa la misma. Si una regla vive en estas rutas, está en el sitio equivocado.

Tampoco se importa nada de `etl/`: si esta API necesitara algo de la extracción del Access
histórico, es señal de que esa lógica pertenecía a `domain/` desde el principio.

Todavía sin implementar. Lo que llevará, en orden:

- `main.py`                · la aplicación FastAPI y su configuración
- `routes_mediciones.py`   · captura de campo desde Flutter (conteo de flores, calibres, bayas)
- `routes_proyecciones.py` · subida del Excel de proyecciones ya calibrado por el ingeniero

Sobre las proyecciones: el objetivo **no** es quitarle el Excel al ingeniero. Ese archivo es un
simulador donde ajusta parámetros a mano hasta que la curva calza con el campo, y esa
flexibilidad es real. Lo que se automatiza es la extracción del resultado final, para que nadie
copie y pegue cifras. Mudar la matemática de las macros a `domain/rules/` es una etapa
posterior, y requiere primero levantar la fórmula con el ingeniero — no es trabajo de código.
"""

__all__: list[str] = []
