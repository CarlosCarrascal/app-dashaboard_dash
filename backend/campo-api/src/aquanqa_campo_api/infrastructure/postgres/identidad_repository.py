"""Lectura PostgreSQL del maestro de evaluadores."""

from __future__ import annotations

from typing import Any

import psycopg

from ...modules.identidad.repository import IdentityRepositoryError
from .connection import PostgresConnectionFactory


class PostgresIdentityRepository:
    def __init__(self, connections: PostgresConnectionFactory):
        self._connections = connections

    def list_evaluadores(self) -> list[dict[str, Any]]:
        return self._select_all(
            """
            SELECT evaluador_id,
                   dni,
                   nullif(btrim(codigo), '') AS codigo,
                   nullif(btrim(zona), '') AS zona,
                   concat_ws(' ', nullif(btrim(nombres), ''), nullif(btrim(apellidos), ''))
                       AS nombre,
                   activo
            FROM core.m_evaluador
            WHERE activo AND en_maestro
            ORDER BY nombre, evaluador_id
            """
        )

    def find_evaluador_by_dni(self, dni: str) -> dict[str, Any] | None:
        rows = self._select_all(
            """
            SELECT evaluador_id,
                   dni,
                   nullif(btrim(codigo), '') AS codigo,
                   nullif(btrim(zona), '') AS zona,
                   concat_ws(' ', nullif(btrim(nombres), ''), nullif(btrim(apellidos), ''))
                       AS nombre,
                   activo
            FROM core.m_evaluador
            WHERE dni = %s AND activo AND en_maestro
            """,
            (dni.strip(),),
        )
        return rows[0] if rows else None

    def _select_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall())
        except psycopg.Error as exc:
            raise IdentityRepositoryError("No se pudo consultar el maestro de evaluadores") from exc


__all__ = ["PostgresIdentityRepository"]
