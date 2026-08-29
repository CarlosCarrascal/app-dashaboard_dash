"""Conexión PostgreSQL para servicios analíticos.

La lógica analítica no debe conocer cómo se construyen las conexiones. Este módulo
concentra la configuración de entorno y mantiene la dependencia ``psycopg`` en la
frontera de infraestructura.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def obtener_conexion_pg() -> Any:
    """Abre una conexión PostgreSQL con la configuración estándar del proyecto."""
    import psycopg
    from dotenv import load_dotenv

    ruta_env_proyecto = Path(__file__).resolve().parents[4] / ".env"
    if ruta_env_proyecto.is_file():
        load_dotenv(ruta_env_proyecto)
    else:
        # En una instalación wheel la raíz del repositorio no existe; python-dotenv
        # buscará entonces un .env desde el directorio de ejecución del consumidor.
        load_dotenv()
    conn_dict = {
        "dbname": os.getenv("PGDATABASE", "aquanqa"),
        "user": os.getenv("PGUSER", "postgres"),
        "password": os.getenv("PGPASSWORD", ""),
        "host": os.getenv("PGHOST", "localhost"),
        "port": os.getenv("PGPORT", "5432"),
    }
    return psycopg.connect(**conn_dict)


@contextmanager
def conexion_postgres(dsn: str, connect_timeout: int = 8) -> Iterator[Any]:
    """Abre un DSN para lecturas/persistencia y cierra la conexión al salir."""
    import psycopg

    with psycopg.connect(dsn, connect_timeout=connect_timeout) as conexion:
        yield conexion


__all__ = ["conexion_postgres", "obtener_conexion_pg"]
