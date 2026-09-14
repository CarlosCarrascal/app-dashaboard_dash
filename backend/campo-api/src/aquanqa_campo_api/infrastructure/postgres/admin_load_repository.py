"""Persistencia y trazabilidad de cargas administrativas."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...modules.admin.repository import (
    AdminRepositoryError,
    ImportPreviewNotFoundError,
    ImportStateError,
)
from ...modules.admin.schemas import (
    AdminLoadPage,
    AdminLoadQuery,
    ImportManifest,
    ImportPreview,
    ImportResult,
)
from .admin_mappers import import_manifest, load_item, page_info


class AdminLoadRepositoryMixin:
    """Métodos que mantienen el manifiesto de preview/carga idempotente."""

    def list_imports(self, query: AdminLoadQuery) -> AdminLoadPage:
        conditions = ["TRUE"]
        params: list[Any] = []
        if not self._unrestricted and self._usuario_id is not None:
            conditions.append("c.usuario_id = %s")
            params.append(self._usuario_id)
        if query.search:
            conditions.append("concat_ws(' ', c.archivo_nombre, u.nombre, u.email) ILIKE %s")
            params.append(f"%{query.search}%")
        if query.estado:
            conditions.append("c.estado = %s")
            params.append(query.estado)
        where = " AND ".join(conditions)
        source = "core.admin_carga c JOIN core.m_usuario u ON u.usuario_id = c.usuario_id"
        select = (
            "c.carga_id, c.archivo_nombre, c.archivo_sha256, c.usuario_id, "
            "u.nombre AS usuario, c.estado, c.filas_total, c.filas_validas, "
            "c.filas_invalidas, c.filas_aceptadas, c.filas_duplicadas, c.error, "
            "c.creado_en, c.iniciado_en, c.finalizado_en"
        )
        try:
            with self._connections.read() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT count(*) AS total FROM {source} WHERE {where}", params
                )
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    f"""
                    SELECT {select}
                    FROM {source}
                    WHERE {where}
                    ORDER BY c.creado_en DESC, c.carga_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, query.page_size, query.offset],
                )
                items = [load_item(row) for row in cursor.fetchall()]
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo leer el historial de cargas") from exc
        return AdminLoadPage(items=items, meta=page_info(query.page, query.page_size, total))

    def create_import_preview(self, preview: ImportPreview, usuario_id: int) -> ImportPreview:
        payloads = [
            row.payload
            for row in preview.rows
            if row.valid and row.payload is not None
        ]
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO core.admin_carga
                        (carga_id, archivo_nombre, archivo_sha256, usuario_id, estado,
                         payloads, filas_total, filas_validas, filas_invalidas)
                    VALUES (%s, %s, %s, %s, 'pending_confirmation', %s, %s, %s, %s)
                    """,
                    (
                        preview.preview_id,
                        preview.filename,
                        preview.file_sha256,
                        usuario_id,
                        Jsonb(payloads),
                        preview.total_rows,
                        preview.valid_rows,
                        preview.invalid_rows,
                    ),
                )
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo guardar el preview de la carga") from exc
        return preview

    def claim_import(
        self, preview_id: str, file_sha256: str, usuario_id: int
    ) -> ImportManifest:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT carga_id, archivo_nombre, archivo_sha256, estado, payloads,
                           filas_total, filas_validas, filas_invalidas, resultado, error
                    FROM core.admin_carga
                    WHERE carga_id = %s AND usuario_id = %s AND archivo_sha256 = %s
                    FOR UPDATE
                    """,
                    (preview_id, usuario_id, file_sha256),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ImportPreviewNotFoundError(
                        "El preview no existe, no pertenece al usuario o el hash no coincide"
                    )
                if row["estado"] == "accepted":
                    return import_manifest(row)
                if row["filas_invalidas"]:
                    raise ImportStateError(
                        "No se puede confirmar un preview que contiene filas inválidas"
                    )
                if not row["filas_validas"]:
                    raise ImportStateError("No se puede confirmar un preview sin filas")
                if row["estado"] == "processing":
                    raise ImportStateError("La carga ya está siendo procesada")
                cursor.execute(
                    """
                    UPDATE core.admin_carga
                    SET estado = 'processing', iniciado_en = now(), error = NULL
                    WHERE carga_id = %s AND usuario_id = %s
                    """,
                    (preview_id, usuario_id),
                )
                row["estado"] = "processing"
        except (ImportPreviewNotFoundError, ImportStateError):
            raise
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo reclamar el preview de la carga") from exc
        return import_manifest(row)

    def complete_import(self, preview_id: str, usuario_id: int, result: ImportResult) -> None:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE core.admin_carga
                    SET estado = 'accepted', filas_aceptadas = %s, filas_duplicadas = %s,
                        resultado = %s, finalizado_en = now(), error = NULL
                    WHERE carga_id = %s AND usuario_id = %s AND estado = 'processing'
                    """,
                    (
                        result.accepted_rows,
                        result.duplicate_rows,
                        Jsonb(result.model_dump(mode="json")),
                        str(preview_id),
                        usuario_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ImportStateError("La carga no está en procesamiento")
        except ImportStateError:
            raise
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo cerrar el manifiesto de carga") from exc

    def fail_import(self, preview_id: str, usuario_id: int, error: str) -> None:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE core.admin_carga
                    SET estado = 'failed', error = %s, finalizado_en = now()
                    WHERE carga_id = %s AND usuario_id = %s AND estado = 'processing'
                    """,
                    (error[:2000], str(preview_id), usuario_id),
                )
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo registrar el fallo de la carga") from exc


__all__ = ["AdminLoadRepositoryMixin"]
