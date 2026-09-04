"""Persistencia PostgreSQL de usuarios, roles y permisos."""

from __future__ import annotations

from typing import Any

import psycopg

from ...modules.seguridad.repository import AuthRepositoryError
from .connection import PostgresConnectionFactory


class PostgresAuthRepository:
    def __init__(self, connections: PostgresConnectionFactory):
        self._connections = connections

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        return self._find("lower(u.email) = lower(%s)", (email,))

    def find_by_id(self, usuario_id: int) -> dict[str, Any] | None:
        return self._find("u.usuario_id = %s", (usuario_id,))

    def touch_login(self, usuario_id: int) -> None:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE core.m_usuario SET ultimo_acceso = now() WHERE usuario_id = %s",
                    (usuario_id,),
                )
        except psycopg.Error as exc:
            raise AuthRepositoryError("No se pudo actualizar el acceso del usuario") from exc

    def _find(self, predicate: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT u.usuario_id, u.email, u.nombre, u.hash_password, u.activo,
                           r.codigo AS rol,
                           COALESCE(array_agg(p.codigo) FILTER (WHERE p.codigo IS NOT NULL), '{{}}')
                               AS permisos,
                           COALESCE((
                               SELECT jsonb_agg(jsonb_build_object(
                                   'empresa_id', a.empresa_id,
                                   'fundo_id', a.fundo_id,
                                   'modulo_id', a.modulo_id,
                                   'lote_id', a.lote_id
                               ) ORDER BY a.alcance_id)
                               FROM core.m_usuario_alcance a
                               WHERE a.usuario_id = u.usuario_id
                           ), '[]'::jsonb) AS alcances
                    FROM core.m_usuario u
                    JOIN core.m_rol r ON r.rol_id = u.rol_id
                    LEFT JOIN core.m_rol_permiso rp ON rp.rol_id = r.rol_id
                    LEFT JOIN core.m_permiso p ON p.permiso_id = rp.permiso_id
                    WHERE {predicate}
                    GROUP BY u.usuario_id, u.email, u.nombre, u.hash_password, u.activo, r.codigo
                    """,
                    params,
                )
                return cursor.fetchone()
        except psycopg.Error as exc:
            raise AuthRepositoryError("No se pudo consultar usuarios") from exc


__all__ = ["PostgresAuthRepository"]
