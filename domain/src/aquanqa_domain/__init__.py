"""Reglas de negocio de Aqu Anqa y acceso tipado al esquema `core`.

Esta es la única capa que ambos consumidores comparten:

    etl/  ────┐
              ├──▶  domain/  ──▶  PostgreSQL (core)
    backend/ ─┘

Qué vive aquí y qué no (ADR-0006):

- **Sí**: qué es una medición válida, cómo se resuelve la identidad de un lote, la matemática
  de una proyección, y cómo se lee y escribe `core` con tipos.
- **No**: nada de HTTP (`fastapi` es cosa de `backend/`), nada de `pyodbc` (la extracción del
  Access histórico es cosa de `etl/`, y solo corre en Windows).

La razón de la asimetría: `domain` se despliega dentro del contenedor Linux del backend en AWS,
donde el driver ODBC de Access no existe. Mantener `pyodbc` fuera de aquí no es una preferencia
de estilo, es lo que permite que el mismo paquete corra en los dos sitios.

Y una frontera que el esquema ya defiende por su cuenta: las invariantes de integridad
(`NOT NULL`, `UNIQUE`, claves foráneas, filas centinela de ADR-0005) viven en `db/sql`, no aquí.
Las validaciones de este paquete son la primera línea —dan un error legible antes de tocar la
base—, no la garantía. La garantía la da el motor, para que valga también frente a un `UPDATE`
manual o un consumidor futuro que no pase por este código.

Todavía sin implementar. Lo que llevará, en orden:

- `schemas.py`      · modelos Pydantic de lo que se captura en campo y de las proyecciones
- `db.py`           · acceso tipado a `core` (sustituye el rol que se le había asignado a
                      Drizzle antes de ADR-0006)
- `rules/`          · calibración de proyecciones, rendimiento kg/ha, identidad de lote
"""

__all__: list[str] = []
