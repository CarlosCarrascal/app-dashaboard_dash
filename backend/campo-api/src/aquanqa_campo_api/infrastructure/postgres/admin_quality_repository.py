"""Persistencia de cuarentena y revisiones de calidad."""

from __future__ import annotations

from typing import Any

import psycopg

from ...modules.admin.repository import (
    AdminMutationError,
    AdminMutationForbiddenError,
    AdminRepositoryError,
    QARejectNotFoundError,
)
from ...modules.admin.schemas import (
    AdminQABulkResolution,
    AdminQAPage,
    AdminQAQuery,
    AdminQAReview,
    AdminQASummary,
    AdminQASummaryItem,
    QABulkDuplicateRequest,
    QAReviewRequest,
)
from .admin_mappers import page_info, qa_item


class AdminQualityRepositoryMixin:
    """Métodos para leer rechazos y registrar revisiones append-only."""

    def qa_summary(self) -> AdminQASummary:
        try:
            with self._connections.read() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT count(*) AS total FROM qua.rechazos")
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    """
                    SELECT motivo, hallazgo, filas, tope, excede_umbral, tablas, explicacion
                    FROM qua.v_resumen
                    ORDER BY filas DESC, motivo
                    """
                )
                motivos = [
                    AdminQASummaryItem(
                        motivo=row["motivo"],
                        hallazgo=row["hallazgo"],
                        filas=int(row["filas"]),
                        tope=int(row["tope"]) if row["tope"] is not None else None,
                        excede_umbral=bool(row["excede_umbral"]),
                        tablas=row["tablas"] or "",
                        explicacion=row["explicacion"],
                    )
                    for row in cursor.fetchall()
                ]
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo leer el resumen de calidad") from exc
        return AdminQASummary(
            total_rechazos=total,
            motivos=motivos,
            alertas=sum(item.excede_umbral for item in motivos),
        )

    def list_qa(self, query: AdminQAQuery) -> AdminQAPage:
        conditions = ["TRUE"]
        params: list[Any] = []
        if query.search:
            conditions.append(
                "concat_ws(' ', r.tabla_origen, r.tabla_destino, r.motivo, "
                "r.hallazgo, r.detalle, r.fila::text) ILIKE %s"
            )
            params.append(f"%{query.search}%")
        for field in ("motivo", "tabla_origen", "hallazgo"):
            value = getattr(query, field)
            if value:
                conditions.append(f"r.{field} ILIKE %s")
                params.append(f"%{value}%")
        if query.excede_umbral is not None:
            conditions.append("COALESCE(s.excede_umbral, false) = %s")
            params.append(query.excede_umbral)
        if query.estado_revision is not None:
            conditions.append("COALESCE(revision.estado, 'pendiente') = %s")
            params.append(query.estado_revision)
        where = " AND ".join(conditions)
        source = (
            "qua.rechazos r LEFT JOIN qua.v_resumen s ON s.motivo = r.motivo "
            "LEFT JOIN LATERAL ("
            "SELECT e.estado, e.comentario, e.revisado_en, e.usuario_id "
            "FROM qua.rechazo_revision_evento e "
            "WHERE e.rechazo_id = r.rechazo_id "
            "ORDER BY e.revisado_en DESC, e.revision_evento_id DESC LIMIT 1"
            ") revision ON TRUE"
        )
        select = (
            "r.rechazo_id, r.tabla_origen, r.tabla_destino, r.motivo, r.hallazgo, "
            "r.detalle, r.fila, r.cargado_en, r.source_snapshot_id, r.migracion_run_id, "
            "r.bloque_ejecucion_id, COALESCE(s.excede_umbral, false) AS excede_umbral, "
            "COALESCE(revision.estado, 'pendiente') AS estado_revision, "
            "revision.comentario AS comentario_revision, revision.revisado_en, "
            "revision.usuario_id AS revisado_por"
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
                    ORDER BY r.cargado_en DESC, r.rechazo_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, query.page_size, query.offset],
                )
                items = [qa_item(row) for row in cursor.fetchall()]
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo leer la cuarentena") from exc
        return AdminQAPage(items=items, meta=page_info(query.page, query.page_size, total))

    def review_qa(
        self, rechazo_id: int, request: QAReviewRequest, usuario_id: int
    ) -> AdminQAReview:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT rechazo_id, estado, comentario, revisado_en,
                           usuario_id, idempotency_key
                    FROM core.fn_admin_revisar_rechazo(%s, %s, %s, %s, %s)
                    """,
                    (
                        rechazo_id,
                        request.estado,
                        request.comentario,
                        usuario_id,
                        request.idempotency_key,
                    ),
                )
                row = cursor.fetchone()
        except psycopg.Error as exc:
            sqlstate = getattr(exc, "sqlstate", None)
            message = str(getattr(exc.diag, "message_primary", None) or exc).strip()
            if sqlstate == "P0002":
                raise QARejectNotFoundError(message) from exc
            if sqlstate == "42501":
                raise AdminMutationForbiddenError(message) from exc
            if sqlstate in {"22023", "23503", "23514"}:
                raise AdminMutationError(message) from exc
            raise AdminRepositoryError("No se pudo registrar la revisión de calidad") from exc
        if row is None:
            raise AdminRepositoryError("La revisión no devolvió un resultado")
        return AdminQAReview(
            rechazo_id=int(row["rechazo_id"]),
            estado_revision=row["estado"],
            idempotency_key=row["idempotency_key"],
            comentario_revision=row["comentario"],
            revisado_en=row["revisado_en"],
            revisado_por=int(row["usuario_id"]),
        )

    def confirm_qa_duplicates(
        self, request: QABulkDuplicateRequest, usuario_id: int
    ) -> AdminQABulkResolution:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT procesados, idempotency_key
                    FROM core.fn_admin_confirmar_duplicados_qa(%s, %s, %s, %s)
                    """,
                    (
                        request.rechazo_ids,
                        request.comentario,
                        usuario_id,
                        request.idempotency_key,
                    ),
                )
                row = cursor.fetchone()
        except psycopg.Error as exc:
            sqlstate = getattr(exc, "sqlstate", None)
            message = str(getattr(exc.diag, "message_primary", None) or exc).strip()
            if sqlstate == "42501":
                raise AdminMutationForbiddenError(message) from exc
            if sqlstate in {"22023", "23503", "23514"}:
                raise AdminMutationError(message) from exc
            raise AdminRepositoryError("No se pudieron confirmar los duplicados") from exc
        if row is None:
            raise AdminRepositoryError("La resolución masiva no devolvió un resultado")
        return AdminQABulkResolution(
            procesados=int(row["procesados"]),
            idempotency_key=row["idempotency_key"],
        )


__all__ = ["AdminQualityRepositoryMixin"]
