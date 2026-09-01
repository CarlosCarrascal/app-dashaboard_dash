"""Lectura PostgreSQL de catálogos de ubicación."""

from __future__ import annotations

from typing import Any

import psycopg

from ...modules.catalogos.repository import CatalogRepositoryError
from .connection import PostgresConnectionFactory


class PostgresCatalogRepository:
    def __init__(self, connections: PostgresConnectionFactory):
        self._connections = connections

    def list_fundos(self) -> list[dict[str, Any]]:
        return self._select_all(
            """
            SELECT e.empresa_id, e.nombre AS empresa,
                   f.fundo_id, f.codigo, f.alias_operativo
            FROM core.m_fundo AS f
            JOIN core.m_empresa AS e ON e.empresa_id = f.empresa_id
            WHERE e.activo AND f.activo
              AND NOT e.es_sentinel AND NOT f.es_sentinel
            ORDER BY e.nombre, f.codigo
            """
        )

    def list_modulos(self, fundo_id: int | None = None) -> list[dict[str, Any]]:
        return self._select_all(
            """
            SELECT e.empresa_id, e.nombre AS empresa,
                   f.fundo_id, f.codigo AS fundo_codigo,
                   m.modulo_id, m.codigo
            FROM core.m_modulo AS m
            JOIN core.m_fundo AS f ON f.fundo_id = m.fundo_id
            JOIN core.m_empresa AS e ON e.empresa_id = f.empresa_id
            WHERE e.activo AND f.activo AND m.activo
              AND NOT e.es_sentinel AND NOT f.es_sentinel AND NOT m.es_sentinel
              AND (%s::integer IS NULL OR m.fundo_id = %s::integer)
            ORDER BY e.nombre, f.codigo, m.codigo
            """,
            (fundo_id, fundo_id),
        )

    def list_lotes(self, modulo_id: int | None = None) -> list[dict[str, Any]]:
        return self._select_all(
            """
            SELECT e.empresa_id, e.nombre AS empresa,
                   f.fundo_id, f.codigo AS fundo_codigo,
                   m.modulo_id, m.codigo AS modulo_codigo,
                   l.lote_id, l.codigo,
                   l.turno_id, t.codigo AS turno,
                   l.variedad_id, v.nombre AS variedad,
                   l.n_plantas
            FROM core.m_lote AS l
            JOIN core.m_modulo AS m ON m.modulo_id = l.modulo_id
            JOIN core.m_fundo AS f ON f.fundo_id = m.fundo_id
            JOIN core.m_empresa AS e ON e.empresa_id = f.empresa_id
            JOIN core.m_turno AS t ON t.turno_id = l.turno_id
            JOIN core.m_variedad AS v ON v.variedad_id = l.variedad_id
            WHERE e.activo AND f.activo AND m.activo
              AND NOT e.es_sentinel AND NOT f.es_sentinel AND NOT m.es_sentinel
              AND NOT l.es_sentinel AND NOT l.es_ficticio
              AND (%s::integer IS NULL OR l.modulo_id = %s::integer)
            ORDER BY e.nombre, f.codigo, m.codigo, l.codigo
            """,
            (modulo_id, modulo_id),
        )

    def _select_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall())
        except psycopg.Error as exc:
            raise CatalogRepositoryError("No se pudo leer el catálogo de PostgreSQL") from exc


__all__ = ["PostgresCatalogRepository"]
