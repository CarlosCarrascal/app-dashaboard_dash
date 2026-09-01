"""Creación centralizada de conexiones PostgreSQL."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from ...modules.health.repository import HealthRepositoryError


class PostgresConnectionFactory:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self._dsn, row_factory=dict_row)


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
