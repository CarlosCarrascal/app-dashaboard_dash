"""Persistencia transaccional PostgreSQL de evaluaciones."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.types.json import Jsonb

from ...modules.evaluaciones.repository import (
    EvaluationConflictError,
    EvaluationNotFoundError,
    EvaluationRepositoryError,
    EvaluatorNotFoundError,
    IdempotencyConflictError,
    LocationNotFoundError,
    StoredEvaluation,
    StoredHistoryPage,
)
from ...modules.evaluaciones.rules import NormalizedEvaluation
from ...modules.evaluaciones.schemas import (
    EvaluationCreate,
    EvaluationHistoryItem,
    EvaluationReceipt,
    ModuleKey,
)
from .connection import PostgresConnectionFactory
from .evaluaciones_core import persist, update_resource
from .evaluaciones_history_sql import HISTORY_SQL
from .evaluaciones_payload import _history_payload, _payload_hash


class PostgresEvaluationRepository:
    """Adaptador síncrono; FastAPI ejecuta sus endpoints def en el thread pool."""

    def __init__(self, connections: PostgresConnectionFactory):
        self._connections = connections

    def save(self, normalized: NormalizedEvaluation) -> StoredEvaluation:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                return self._save_with_cursor(cursor, normalized)
        except (
            EvaluationRepositoryError,
            LocationNotFoundError,
            EvaluatorNotFoundError,
            IdempotencyConflictError,
        ):
            raise
        except psycopg.Error as exc:
            raise EvaluationRepositoryError(
                "No se pudo guardar la evaluación en PostgreSQL"
            ) from exc

    def save_many(self, normalized: Sequence[NormalizedEvaluation]) -> list[StoredEvaluation]:
        """Guarda un lote completo en una sola transacción PostgreSQL."""
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                return [self._save_with_cursor(cursor, item) for item in normalized]
        except (
            EvaluationRepositoryError,
            LocationNotFoundError,
            EvaluatorNotFoundError,
            IdempotencyConflictError,
        ):
            raise
        except psycopg.Error as exc:
            raise EvaluationRepositoryError(
                "No se pudo guardar la carga masiva en PostgreSQL"
            ) from exc

    def _save_with_cursor(self, cursor: Any, normalized: NormalizedEvaluation) -> StoredEvaluation:
        source = normalized.source
        digest = _payload_hash(normalized)
        history_payload = _history_payload(normalized)
        client_id = str(source.client_id)
        cursor.execute(
            """
            INSERT INTO core.api_evaluacion_ingesta
                (client_id, module_key, payload_hash, payload,
                 evaluador_id, evaluador_dni, fecha, captured_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_id) DO NOTHING
            """,
            (
                client_id,
                source.module_key,
                digest,
                Jsonb(history_payload),
                source.evaluador_id,
                source.evaluador_dni,
                source.fecha,
                source.captured_at,
            ),
        )
        cursor.execute(
            """
            SELECT client_id, module_key, payload_hash, resource_table,
                   resource_id, status
            FROM core.api_evaluacion_ingesta
            WHERE client_id = %s
            FOR UPDATE
            """,
            (client_id,),
        )
        ingest = cursor.fetchone()
        if ingest is None:
            raise EvaluationRepositoryError("No se pudo registrar la idempotencia")
        if ingest["module_key"] != source.module_key or ingest["payload_hash"] != digest:
            raise IdempotencyConflictError("client_id ya fue utilizado con otro módulo o contenido")
        lote_id = self._resolve_lote(cursor, source)
        evaluador_id = self._resolve_evaluador(cursor, source)
        history_payload["lote_id"] = lote_id
        history_payload["evaluador_id"] = evaluador_id
        cursor.execute(
            """
            UPDATE core.api_evaluacion_ingesta
            SET payload = %s,
                evaluador_id = %s,
                evaluador_dni = COALESCE(%s, evaluador_dni),
                fecha = %s,
                captured_at = %s,
                actualizado_en = now()
            WHERE client_id = %s
            """,
            (
                Jsonb(history_payload),
                evaluador_id,
                source.evaluador_dni,
                source.fecha,
                source.captured_at,
                client_id,
            ),
        )
        if ingest["status"] == "accepted" and ingest["resource_id"] is not None:
            return StoredEvaluation(
                EvaluationReceipt(
                    client_id=source.client_id,
                    evaluation_id=int(ingest["resource_id"]),
                    module_key=source.module_key,
                    status="duplicate",
                    received_at=datetime.now(UTC),
                )
            )
        resource_table, resource_id, duplicate = self._persist(
            cursor, normalized, lote_id, evaluador_id, digest
        )
        cursor.execute(
            """
            UPDATE core.api_evaluacion_ingesta
            SET resource_table = %s,
                resource_id = %s,
                status = 'accepted',
                actualizado_en = now()
            WHERE client_id = %s
            """,
            (resource_table, resource_id, client_id),
        )
        return StoredEvaluation(
            EvaluationReceipt(
                client_id=source.client_id,
                evaluation_id=resource_id,
                module_key=source.module_key,
                status="duplicate" if duplicate else "accepted",
                received_at=datetime.now(UTC),
            )
        )

    def update(self, normalized: NormalizedEvaluation) -> StoredEvaluation:
        """Actualiza una captura móvil sin cambiar su identidad ni su instante original."""
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                return self._update_with_cursor(cursor, normalized)
        except (
            EvaluationConflictError,
            EvaluationNotFoundError,
            EvaluationRepositoryError,
            LocationNotFoundError,
            EvaluatorNotFoundError,
        ):
            raise
        except psycopg.errors.UniqueViolation as exc:
            raise EvaluationConflictError(
                "la edición entra en conflicto con una evaluación existente"
            ) from exc
        except psycopg.Error as exc:
            raise EvaluationRepositoryError(
                "No se pudo actualizar la evaluación en PostgreSQL"
            ) from exc

    def _update_with_cursor(
        self, cursor: Any, normalized: NormalizedEvaluation
    ) -> StoredEvaluation:
        source = normalized.source
        client_id = str(source.client_id)
        digest = _payload_hash(normalized)
        cursor.execute(
            """
            SELECT client_id, module_key, resource_table, resource_id,
                   status, evaluador_id, evaluador_dni, fecha, captured_at
            FROM core.api_evaluacion_ingesta
            WHERE client_id = %s
            FOR UPDATE
            """,
            (client_id,),
        )
        ingest = cursor.fetchone()
        if (
            ingest is None
            or ingest["status"] != "accepted"
            or ingest["resource_id"] is None
            or ingest["resource_table"] is None
        ):
            raise EvaluationNotFoundError(
                "No existe una evaluación móvil editable con ese client_id"
            )

        resource_table = str(ingest["resource_table"])
        expected_table = "ev_evaluacion"
        if ingest["module_key"] != source.module_key or resource_table != expected_table:
            raise EvaluationConflictError("el client_id pertenece a otro módulo de evaluación")

        resource_meta = {"ev_evaluacion": ("evaluacion_id", True)}.get(resource_table)
        if resource_meta is None:
            raise EvaluationRepositoryError("el recurso asociado no es editable por la API")

        resource_id_column, has_hour = resource_meta
        columns = "fecha, hora" if has_hour else "fecha"
        cursor.execute(
            f"""
            SELECT {columns}
            FROM core.{resource_table}
            WHERE {resource_id_column} = %s
            FOR UPDATE
            """,
            (int(ingest["resource_id"]),),
        )
        original = cursor.fetchone()
        if original is None:
            raise EvaluationNotFoundError(
                "el recurso asociado a la captura ya no existe en PostgreSQL"
            )

        lote_id = self._resolve_lote(cursor, source)
        evaluator_id = self._resolve_evaluador(cursor, source)
        stored_evaluator_id = ingest["evaluador_id"]
        if stored_evaluator_id is not None and evaluator_id != int(stored_evaluator_id):
            raise EvaluationConflictError("no se puede cambiar el evaluador de una captura")
        evaluator_id = int(stored_evaluator_id) if stored_evaluator_id is not None else evaluator_id
        if evaluator_id is None:
            raise EvaluatorNotFoundError("la captura no tiene un evaluador válido")

        original_date = original["fecha"]
        original_hour = original.get("hora") if has_hour else None
        self._update_resource(
            cursor,
            normalized,
            lote_id=lote_id,
            evaluator_id=evaluator_id,
            resource_table=resource_table,
            resource_id=int(ingest["resource_id"]),
            original_date=original_date,
            original_hour=original_hour,
            digest=digest,
        )

        history_payload = _history_payload(normalized)
        history_payload["fecha"] = original_date.isoformat()
        history_payload["lote_id"] = lote_id
        history_payload["evaluador_id"] = evaluator_id
        history_payload["evaluador_dni"] = ingest["evaluador_dni"] or source.evaluador_dni or ""
        if ingest["captured_at"] is not None:
            history_payload["captured_at"] = ingest["captured_at"].isoformat()
        cursor.execute(
            """
            UPDATE core.api_evaluacion_ingesta
            SET payload_hash = %s,
                payload = %s,
                evaluador_id = %s,
                evaluador_dni = %s,
                fecha = %s,
                captured_at = %s,
                actualizado_en = now()
            WHERE client_id = %s
            """,
            (
                digest,
                Jsonb(history_payload),
                evaluator_id,
                history_payload["evaluador_dni"],
                original_date,
                ingest["captured_at"],
                client_id,
            ),
        )
        return StoredEvaluation(
            EvaluationReceipt(
                client_id=source.client_id,
                evaluation_id=int(ingest["resource_id"]),
                module_key=source.module_key,
                status="accepted",
                received_at=datetime.now(UTC),
            )
        )

    def _update_resource(
        self,
        cursor: Any,
        normalized: NormalizedEvaluation,
        *,
        lote_id: int,
        evaluator_id: int,
        resource_table: str,
        resource_id: int,
        original_date: Any,
        original_hour: Any,
        digest: str,
    ) -> None:
        update_resource(
            cursor, normalized, lote_id=lote_id, evaluator_id=evaluator_id, resource_id=resource_id
        )

    def get_by_client_id(self, client_id: UUID) -> StoredEvaluation | None:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT client_id, module_key, resource_id, status, actualizado_en
                    FROM core.api_evaluacion_ingesta
                    WHERE client_id = %s
                    """,
                    (str(client_id),),
                )
                row = cursor.fetchone()
                if row is None or row["resource_id"] is None:
                    return None
                return StoredEvaluation(
                    EvaluationReceipt(
                        client_id=client_id,
                        evaluation_id=int(row["resource_id"]),
                        module_key=row["module_key"],
                        status="accepted" if row["status"] == "accepted" else "duplicate",
                        received_at=row["actualizado_en"],
                    )
                )
        except psycopg.Error as exc:
            raise EvaluationRepositoryError("No se pudo consultar la evaluación") from exc

    def list_history(
        self,
        *,
        evaluador_id: int | None,
        evaluador_dni: str | None,
        module_key: ModuleKey | None,
        limit: int,
        offset: int,
    ) -> StoredHistoryPage:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT evaluador_id
                    FROM core.m_evaluador
                    WHERE activo AND en_maestro
                      AND (%s::bigint IS NULL OR evaluador_id = %s)
                      AND (%s::text IS NULL OR dni = %s)
                    """,
                    (evaluador_id, evaluador_id, evaluador_dni, evaluador_dni),
                )
                evaluator = cursor.fetchone()
                if evaluator is None:
                    raise EvaluatorNotFoundError("el evaluador no existe o está inactivo")
                resolved_evaluator_id = int(evaluator["evaluador_id"])

                cursor.execute(
                    HISTORY_SQL,
                    (resolved_evaluator_id, module_key, module_key, limit + 1, offset),
                )
                rows = cursor.fetchall()
                has_more = len(rows) > limit
                items: list[EvaluationHistoryItem] = []
                for row in rows[:limit]:
                    history_id = row["client_id"] or str(
                        uuid5(
                            NAMESPACE_URL,
                            f"aquanqa:{row['source_table']}:{row['source_id']}",
                        )
                    )
                    items.append(
                        EvaluationHistoryItem(
                            id=history_id,
                            module_key=row["module_key"],
                            fecha=row["fecha"],
                            captured_at=row["captured_at"],
                            evaluador=row["evaluador"],
                            evaluador_id=row["evaluador_id"],
                            evaluador_dni=row["evaluador_dni"],
                            lote_id=row["lote_id"],
                            fundo=row["fundo"],
                            modulo=row["modulo"],
                            lote=row["lote"],
                            cortina=row["cortina"],
                            hilera=row["hilera"],
                            planta=row["planta"],
                            valores=dict(row["valores"]),
                        )
                    )
                return StoredHistoryPage(items=items, has_more=has_more)
        except EvaluatorNotFoundError:
            raise
        except (psycopg.Error, ValueError, TypeError) as exc:
            raise EvaluationRepositoryError("No se pudo consultar el historial") from exc

    def _resolve_lote(self, cursor: Any, source: EvaluationCreate) -> int:
        if source.lote_id is not None:
            lote_id = source.lote_id
        else:
            cursor.execute(
                "SELECT stg.fn_resolver_lote(%s, %s, %s) AS lote_id",
                (source.fundo, source.modulo, source.lote),
            )
            row = cursor.fetchone()
            lote_id = None if row is None else row["lote_id"]
        if lote_id is None:
            raise LocationNotFoundError("lote_id no existe o no pudo resolverse sin ambigüedad")

        if source.fundo and source.modulo and source.lote:
            cursor.execute(
                """
                SELECT l.lote_id
                FROM core.m_lote AS l
                JOIN core.m_modulo AS m ON m.modulo_id = l.modulo_id
                JOIN core.m_fundo AS f ON f.fundo_id = m.fundo_id
                WHERE l.lote_id = %s
                  AND btrim(f.codigo) = btrim(%s)
                  AND btrim(m.codigo) = btrim(%s)
                  AND btrim(l.codigo) = btrim(%s)
                """,
                (lote_id, source.fundo, source.modulo, source.lote),
            )
            if cursor.fetchone() is None:
                raise LocationNotFoundError(
                    "la combinación de fundo, módulo y lote no coincide con lote_id"
                )

        cursor.execute(
            """
            SELECT l.lote_id
            FROM core.m_lote AS l
            JOIN core.m_modulo AS m ON m.modulo_id = l.modulo_id
            JOIN core.m_fundo AS f ON f.fundo_id = m.fundo_id
            JOIN core.m_empresa AS e ON e.empresa_id = f.empresa_id
            WHERE l.lote_id = %s
              AND e.activo AND f.activo AND m.activo
              AND NOT e.es_sentinel AND NOT f.es_sentinel AND NOT m.es_sentinel
              AND NOT l.es_sentinel AND NOT l.es_ficticio
            """,
            (lote_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise LocationNotFoundError("lote_id no existe o no es elegible para captura")
        return int(row["lote_id"])

    def _resolve_evaluador(self, cursor: Any, source: EvaluationCreate) -> int | None:
        if source.evaluador_id is not None:
            if source.evaluador_dni:
                cursor.execute(
                    """
                    SELECT evaluador_id
                    FROM core.m_evaluador
                    WHERE evaluador_id = %s AND dni = %s AND activo AND en_maestro
                    """,
                    (source.evaluador_id, source.evaluador_dni),
                )
            else:
                cursor.execute(
                    """
                    SELECT evaluador_id
                    FROM core.m_evaluador
                    WHERE evaluador_id = %s AND activo AND en_maestro
                    """,
                    (source.evaluador_id,),
                )
        elif source.evaluador_dni:
            cursor.execute(
                """
                SELECT evaluador_id
                FROM core.m_evaluador
                WHERE dni = %s AND activo AND en_maestro
                """,
                (source.evaluador_dni,),
            )
        else:
            return None
        row = cursor.fetchone()
        if row is None:
            raise EvaluatorNotFoundError("el evaluador no existe o está inactivo")
        return int(row["evaluador_id"])

    def _persist(
        self,
        cursor: Any,
        normalized: NormalizedEvaluation,
        lote_id: int,
        evaluador_id: int | None,
        digest: str,
    ) -> tuple[str, int, bool]:
        return persist(cursor, normalized, lote_id, evaluador_id)


__all__ = ["PostgresEvaluationRepository"]
