# domain · reglas de negocio y acceso a `core`

Librería Python que comparten el ETL y la API de campo. **No es un servicio**: no escucha en
ningún puerto, no se despliega sola.

```
etl/  ────┐
          ├──▶  domain/  ──▶  PostgreSQL (core)
backend/ ─┘
```

## Qué entra y qué no

| | |
|---|---|
| **Sí** | Qué es una medición válida · cómo se resuelve la identidad de un lote · la matemática de una proyección · lectura y escritura tipada de `core` |
| **No** | `fastapi` — eso es `backend/campo-api` · `pyodbc` — eso es `etl/`, y solo corre en Windows |

La regla no es estética. `domain` viaja dentro del contenedor Linux del backend en AWS, donde el
driver ODBC de Access **no existe**. Si este paquete deja de importar sin `pyodbc`, el backend
deja de arrancar en producción. Mismo lenguaje no significa mismo desplegable.

**Prueba rápida de que la frontera sigue en pie:** `python -c "import aquanqa_domain"` en un
entorno sin `fastapi` ni `pyodbc` instalados tiene que funcionar.

## Su relación con las restricciones de la base

Las invariantes de integridad —`NOT NULL`, `UNIQUE`, claves foráneas, las filas centinela de
ADR-0005— viven en `db/sql`, no aquí. Lo que valida este paquete es la **primera línea**: da un
error legible antes de tocar la base. No es la garantía.

Esa distinción es el hallazgo central de la auditoría del Access original: *el motor nunca tuvo
permiso para rechazar un dato inválido*. Mover esas reglas del esquema al código de aplicación
reabriría el mismo agujero para cualquier otra vía de escritura —un script de soporte, un
`UPDATE` manual, un consumidor que aparezca en tres años—. Por eso están en los dos sitios, y
por eso el orden importa: el motor manda.

## Estado

Andamiaje. Sin implementar todavía; es la etapa E4 del plan.

| Archivo | Qué llevará |
|---|---|
| `schemas.py` | Modelos Pydantic de la captura de campo y de las proyecciones |
| `db.py` | Acceso tipado a `core` (sustituye a Drizzle, ver ADR-0006) |
| `rules/` | Calibración de proyecciones, rendimiento kg/ha, identidad de lote |

## Instalación

Se instala en editable junto al resto del monorepo con `npm run setup`, que hace el equivalente a:

```bash
pip install -e domain      # primero: los otros dos lo importan
pip install -e etl
pip install -e backend/campo-api
```
