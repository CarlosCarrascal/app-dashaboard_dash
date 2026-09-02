"""Pool centralizado de conexiones PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ...modules.health.repository import HealthRepositoryError


class PostgresConnectionFactory:
    """Entrega conexiones reutilizables y limita la presión sobre PostgreSQL."""

    def __init__(
        self,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        timeout: float = 5.0,
    ):
        self._pool = ConnectionPool(
            conninfo=dsn,
            kwargs={"row_factory": dict_row},
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            open=False,
            name="aquanqa-campo-api",
        )
        self._lock = Lock()
        self._opened = False

    def open(self) -> None:
        """Inicializa el pool una vez por proceso y espera su conexión base."""
        with self._lock:
            if self._opened:
                return
            self._pool.open(wait=True)
            self._opened = True

    def close(self) -> None:
        """Devuelve recursos de red al apagar el proceso de la API."""
        with self._lock:
            if not self._opened:
                return
            self._pool.close()
            self._opened = False

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection[Any]]:
        """Obtiene una conexión transaccional y la devuelve al pool al salir."""
        self.open()
        with self._pool.connection() as connection:
            yield connection


class PostgresHealthRepository:
    def __init__(self, connections: PostgresConnectionFactory):
        self._connections = connections

    def ping(self) -> None:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except psycopg.Error as exc:
            raise HealthRepositoryError("No se pudo comprobar PostgreSQL") from exc


__all__ = ["PostgresConnectionFactory", "PostgresHealthRepository"]
