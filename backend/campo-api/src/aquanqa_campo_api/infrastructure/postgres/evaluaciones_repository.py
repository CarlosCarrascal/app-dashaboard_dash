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

    def save_many(
        self, normalized: Sequence[NormalizedEvaluation]
    ) -> list[StoredEvaluation]:
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
            raise IdempotencyConflictError(
                "client_id ya fue utilizado con otro módulo o contenido"
            )
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
        expected_table = {
            "estadios": "ev_estados",
            "flores": "ev_flores",
            "brotes": "ev_brotes",
            "ramas": "ev_evaluacion_ramas",
            "baya": "ev_evaluacion_baya",
            "pesos": "ev_evaluacion_baya",
        }[source.module_key]
        if ingest["module_key"] != source.module_key or resource_table != expected_table:
            raise EvaluationConflictError(
                "el client_id pertenece a otro módulo de evaluación"
            )

        resource_meta = {
            "ev_estados": ("estados_id", True),
            "ev_flores": ("flores_id", True),
            "ev_brotes": ("brotes_id", True),
            "ev_evaluacion_ramas": ("evaluacion_ramas_id", False),
            "ev_evaluacion_baya": ("evaluacion_baya_id", False),
        }.get(resource_table)
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
        history_payload["evaluador_dni"] = (
            ingest["evaluador_dni"] or source.evaluador_dni or ""
        )
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
        source = normalized.source
        data = normalized.data
        location = (lote_id, original_date, source.cortina, source.hilera, source.planta)

        if resource_table == "ev_estados":
            cursor.execute(
                """
                UPDATE core.ev_estados
                SET lote_id = %s, fecha = %s, cortina = %s, hilera = %s, planta = %s,
                    evaluador_id = %s, e1 = %s, e2 = %s, e3 = %s, e4 = %s, e5 = %s,
                    total_origen = %s, hora = %s, item = %s
                WHERE estados_id = %s
                """,
                (
                    *location,
                    evaluator_id,
                    data["e1"],
                    data["e2"],
                    data["e3"],
                    data["e4"],
                    data["e5"],
                    data["total_origen"],
                    original_hour,
                    data["item"],
                    resource_id,
                ),
            )
            return

        if resource_table == "ev_flores":
            cursor.execute(
                """
                UPDATE core.ev_flores
                SET lote_id = %s, fecha = %s, cortina = %s, hilera = %s, planta = %s,
                    evaluador_id = %s, n_flores = %s, cuajo = %s, yemas_abiertas = %s,
                    yemas_por_abrir = %s, yemas_muertas = %s, brotes_tiernos = %s,
                    hora = %s, item = %s
                WHERE flores_id = %s
                """,
                (
                    *location,
                    evaluator_id,
                    data["n_flores"],
                    data["cuajo"],
                    data["yemas_abiertas"],
                    data["yemas_por_abrir"],
                    data["yemas_muertas"],
                    data["brotes_tiernos"],
                    original_hour,
                    data["item"],
                    resource_id,
                ),
            )
            return

        if resource_table == "ev_brotes":
            cursor.execute(
                """
                UPDATE core.ev_brotes
                SET lote_id = %s, fecha = %s, piso = %s, cortina = %s, hilera = %s,
                    planta = %s, evaluador_id = %s, brotes = %s, des1 = %s, des2 = %s,
                    des3 = %s, hora = %s
                WHERE brotes_id = %s
                """,
                (
                    lote_id,
                    original_date,
                    data["piso"],
                    source.cortina,
                    source.hilera,
                    source.planta,
                    evaluator_id,
                    data["brotes"],
                    data["des1"],
                    data["des2"],
                    data["des3"],
                    original_hour,
                    resource_id,
                ),
            )
            return

        if resource_table == "ev_evaluacion_ramas":
            cursor.execute(
                """
                UPDATE core.ev_evaluacion_ramas
                SET lote_id = %s, fecha = %s, cortina = %s, hilera = %s, planta = %s,
                    evaluador_id = %s, ramas_menor5 = %s, ramas_mayor5 = %s
                WHERE evaluacion_ramas_id = %s
                """,
                (
                    *location,
                    evaluator_id,
                    data["ramas_menor5"],
                    data["ramas_mayor5"],
                    resource_id,
                ),
            )
            cursor.execute(
                "DELETE FROM core.ev_rama_medicion WHERE evaluacion_ramas_id = %s",
                (resource_id,),
            )
            for measurement in data["mediciones"]:
                cursor.execute(
                    """
                    INSERT INTO core.ev_rama_medicion
                        (evaluacion_ramas_id, nro_rama, diametro, id_origen)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        resource_id,
                        measurement["nro_rama"],
                        measurement["diametro"],
                        str(source.client_id),
                    ),
                )
            return

        cursor.execute(
            """
            UPDATE core.ev_evaluacion_baya
            SET lote_id = %s, fecha = %s, cortina = %s, hilera = %s, planta = %s,
                evaluador_id = %s, tipo = %s, source_row_hash = %s
            WHERE evaluacion_baya_id = %s
            """,
            (*location, evaluator_id, data["tipo"], digest, resource_id),
        )
        cursor.execute(
            "DELETE FROM core.ev_baya_observacion WHERE evaluacion_baya_id = %s",
            (resource_id,),
        )
        for observation in data["observaciones"]:
            cursor.execute(
                """
                INSERT INTO core.ev_baya_observacion
                    (evaluacion_baya_id, numero_muestra, numero_medicion,
                     estado_codigo, diametro_mm, peso_g)
                VALUES (%s, %s, 1, %s, %s, %s)
                """,
                (
                    resource_id,
                    observation["numero_muestra"],
                    observation.get("estado_codigo"),
                    observation.get("diametro_mm"),
                    observation.get("peso_g"),
                ),
            )
        return

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
                    """
                    WITH facts AS (
                        SELECT 'ev_estados'::text AS source_table,
                               x.estados_id::bigint AS source_id,
                               'estadios'::text AS module_key,
                               x.lote_id, x.fecha,
                               timezone(
                                   'America/Lima',
                                   x.fecha::timestamp + COALESCE(x.hora, time '00:00')
                               ) AS captured_at,
                               x.evaluador_id, x.cortina, x.hilera, x.planta,
                               jsonb_build_object(
                                   'm1_e1', x.e1, 'm1_e2', x.e2, 'm1_e3', x.e3,
                                   'm1_e4', x.e4, 'm1_e5', x.e5,
                                   'm1_total', COALESCE(x.total_origen, x.total)
                               ) AS valores
                        FROM core.ev_estados AS x
                        WHERE x.evaluador_id = %s

                        UNION ALL

                        SELECT 'ev_flores', x.flores_id::bigint, 'flores',
                               x.lote_id, x.fecha,
                               timezone(
                                   'America/Lima',
                                   x.fecha::timestamp + COALESCE(x.hora, time '00:00')
                               ),
                               x.evaluador_id, x.cortina, x.hilera, x.planta,
                               jsonb_build_object(
                                   'm2_flores', x.n_flores, 'm2_cuajos', x.cuajo,
                                   'm2_yp', x.yemas_por_abrir,
                                   'm2_ya', x.yemas_abiertas,
                                   'm2_ymuerta', x.yemas_muertas,
                                   'm2_brotes_tiernos', x.brotes_tiernos
                               )
                        FROM core.ev_flores AS x
                        WHERE x.evaluador_id = %s

                        UNION ALL

                        SELECT 'ev_brotes', x.brotes_id::bigint, 'brotes',
                               x.lote_id, x.fecha,
                               timezone(
                                   'America/Lima',
                                   x.fecha::timestamp + COALESCE(x.hora, time '00:00')
                               ),
                               x.evaluador_id, x.cortina, x.hilera, x.planta,
                               jsonb_build_object(
                                   'm6_piso', x.piso, 'm6_brotes', x.brotes,
                                   'm6_des1', x.des1, 'm6_des2', x.des2,
                                   'm6_des3', x.des3
                               )
                        FROM core.ev_brotes AS x
                        WHERE x.evaluador_id = %s

                        UNION ALL

                        SELECT 'ev_evaluacion_baya', x.evaluacion_baya_id,
                               CASE WHEN x.tipo = 'peso' THEN 'pesos' ELSE 'baya' END,
                               x.lote_id, x.fecha,
                               timezone('America/Lima', x.fecha::timestamp),
                               x.evaluador_id, x.cortina, x.hilera, x.planta,
                               COALESCE(
                                   (
                                       SELECT jsonb_object_agg(metric.key, metric.value)
                                       FROM (
                                           SELECT 'm4_est'
                                                  || lpad(o.numero_muestra::text, 2, '0') AS key,
                                                  to_jsonb(o.estado_codigo) AS value
                                           FROM core.ev_baya_observacion AS o
                                           WHERE o.evaluacion_baya_id = x.evaluacion_baya_id
                                             AND x.tipo <> 'peso'
                                             AND o.estado_codigo IS NOT NULL
                                           UNION ALL
                                           SELECT CASE
                                                      WHEN x.tipo = 'peso' THEN 'm5_diam'
                                                      ELSE 'm4_diam'
                                                  END
                                                  || lpad(o.numero_muestra::text, 2, '0'),
                                                  to_jsonb(o.diametro_mm)
                                           FROM core.ev_baya_observacion AS o
                                           WHERE o.evaluacion_baya_id = x.evaluacion_baya_id
                                             AND o.diametro_mm IS NOT NULL
                                           UNION ALL
                                           SELECT 'm5_peso' || lpad(o.numero_muestra::text, 2, '0'),
                                                  to_jsonb(o.peso_g)
                                           FROM core.ev_baya_observacion AS o
                                           WHERE o.evaluacion_baya_id = x.evaluacion_baya_id
                                             AND x.tipo = 'peso'
                                             AND o.peso_g IS NOT NULL
                                       ) AS metric
                                   ),
                                   '{}'::jsonb
                               )
                        FROM core.ev_evaluacion_baya AS x
                        WHERE x.evaluador_id = %s

                        UNION ALL

                        SELECT 'ev_evaluacion_ramas', x.evaluacion_ramas_id::bigint,
                               'ramas', x.lote_id, x.fecha,
                               timezone('America/Lima', x.fecha::timestamp),
                               x.evaluador_id, x.cortina, x.hilera, x.planta,
                               jsonb_build_object(
                                   'm7_ram_lt5', x.ramas_menor5,
                                   'm7_ram_gt5', x.ramas_mayor5
                               ) || COALESCE(
                                   (
                                       SELECT jsonb_object_agg(
                                           'm7_diam' || lpad(r.nro_rama::text, 2, '0'),
                                           to_jsonb(r.diametro)
                                       )
                                       FROM core.ev_rama_medicion AS r
                                       WHERE r.evaluacion_ramas_id = x.evaluacion_ramas_id
                                   ),
                                   '{}'::jsonb
                               )
                        FROM core.ev_evaluacion_ramas AS x
                        WHERE x.evaluador_id = %s
                    )
                    SELECT facts.source_table, facts.source_id, i.client_id,
                           facts.module_key, facts.fecha,
                           COALESCE(i.captured_at, facts.captured_at) AS captured_at,
                           facts.evaluador_id, ev.dni AS evaluador_dni,
                           btrim(concat_ws(' ', ev.nombres, ev.apellidos)) AS evaluador,
                           l.lote_id,
                           COALESCE(f.codigo, '') AS fundo,
                           COALESCE(m.codigo, '') AS modulo,
                           COALESCE(l.codigo, '') AS lote,
                           facts.cortina, facts.hilera, facts.planta,
                           COALESCE(i.payload -> 'valores', facts.valores, '{}'::jsonb) AS valores
                    FROM facts
                    JOIN core.m_evaluador AS ev ON ev.evaluador_id = facts.evaluador_id
                    JOIN core.m_lote AS l ON l.lote_id = facts.lote_id
                    LEFT JOIN core.m_modulo AS m ON m.modulo_id = l.modulo_id
                    LEFT JOIN core.m_fundo AS f ON f.fundo_id = m.fundo_id
                    LEFT JOIN core.api_evaluacion_ingesta AS i
                      ON i.resource_table = facts.source_table
                     AND i.resource_id = facts.source_id
                     AND i.status = 'accepted'
                    WHERE (%s::text IS NULL OR facts.module_key = %s)
                    ORDER BY captured_at DESC, facts.source_table, facts.source_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (
                        resolved_evaluator_id,
                        resolved_evaluator_id,
                        resolved_evaluator_id,
                        resolved_evaluator_id,
                        resolved_evaluator_id,
                        module_key,
                        module_key,
                        limit + 1,
                        offset,
                    ),
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
        source = normalized.source
        data = normalized.data
        location = (lote_id, source.fecha, source.cortina, source.hilera, source.planta)

        if source.module_key == "estadios":
            cursor.execute(
                """
                INSERT INTO core.ev_estados
                    (lote_id, fecha, cortina, hilera, planta, evaluador_id,
                     e1, e2, e3, e4, e5, total_origen, hora, item)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (item, lote_id, fecha, cortina, hilera, planta)
                DO UPDATE SET evaluador_id = EXCLUDED.evaluador_id,
                              e1 = EXCLUDED.e1, e2 = EXCLUDED.e2, e3 = EXCLUDED.e3,
                              e4 = EXCLUDED.e4, e5 = EXCLUDED.e5,
                              total_origen = EXCLUDED.total_origen,
                              hora = EXCLUDED.hora
                RETURNING estados_id
                """,
                (
                    *location,
                    evaluador_id,
                    data["e1"], data["e2"], data["e3"], data["e4"], data["e5"],
                    data["total_origen"], data["hora"], data["item"],
                ),
            )
            return "ev_estados", int(cursor.fetchone()["estados_id"]), False

        if source.module_key == "flores":
            cursor.execute(
                """
                INSERT INTO core.ev_flores
                    (lote_id, fecha, cortina, hilera, planta, evaluador_id,
                     n_flores, cuajo, yemas_abiertas, yemas_por_abrir, yemas_muertas,
                     brotes_tiernos,
                     hora, item)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING flores_id
                """,
                (
                    *location,
                    evaluador_id,
                    data["n_flores"], data["cuajo"], data["yemas_abiertas"],
                    data["yemas_por_abrir"], data["yemas_muertas"],
                    data["brotes_tiernos"],
                    data["hora"], data["item"],
                ),
            )
            return "ev_flores", int(cursor.fetchone()["flores_id"]), False

        if source.module_key == "brotes":
            cursor.execute(
                """
                INSERT INTO core.ev_brotes
                    (lote_id, fecha, piso, cortina, hilera, planta, evaluador_id,
                     brotes, des1, des2, des3, hora)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (lote_id, fecha, piso, cortina, hilera, planta)
                DO UPDATE SET evaluador_id = EXCLUDED.evaluador_id,
                              brotes = EXCLUDED.brotes, des1 = EXCLUDED.des1,
                              des2 = EXCLUDED.des2, des3 = EXCLUDED.des3,
                              hora = EXCLUDED.hora
                RETURNING brotes_id
                """,
                (
                    lote_id, source.fecha, data["piso"], source.cortina,
                    source.hilera, source.planta, evaluador_id, data["brotes"],
                    data["des1"], data["des2"], data["des3"], data["hora"],
                ),
            )
            return "ev_brotes", int(cursor.fetchone()["brotes_id"]), False

        if source.module_key == "ramas":
            cursor.execute(
                """
                INSERT INTO core.ev_evaluacion_ramas
                    (lote_id, fecha, cortina, hilera, planta, evaluador_id,
                     ramas_menor5, ramas_mayor5)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (lote_id, fecha, cortina, hilera, planta)
                DO UPDATE SET evaluador_id = EXCLUDED.evaluador_id,
                              ramas_menor5 = EXCLUDED.ramas_menor5,
                              ramas_mayor5 = EXCLUDED.ramas_mayor5
                RETURNING evaluacion_ramas_id
                """,
                (*location, evaluador_id, data["ramas_menor5"], data["ramas_mayor5"]),
            )
            header_id = int(cursor.fetchone()["evaluacion_ramas_id"])
            cursor.execute(
                "DELETE FROM core.ev_rama_medicion WHERE evaluacion_ramas_id = %s",
                (header_id,),
            )
            for measurement in data["mediciones"]:
                cursor.execute(
                    """
                    INSERT INTO core.ev_rama_medicion
                        (evaluacion_ramas_id, nro_rama, diametro, id_origen)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        header_id, measurement["nro_rama"], measurement["diametro"],
                        str(source.client_id),
                    ),
                )
            return "ev_evaluacion_ramas", header_id, False

        cursor.execute(
            """
            SELECT evaluacion_baya_id, source_row_hash
            FROM core.ev_evaluacion_baya
            WHERE origen = 'mobile' AND idempotency_key = %s
            FOR UPDATE
            """,
            (str(source.client_id),),
        )
        existing = cursor.fetchone()
        if existing is not None:
            if existing["source_row_hash"] not in (None, digest):
                raise IdempotencyConflictError(
                    "client_id ya existe en evaluaciones de baya con otro contenido"
                )
            return "ev_evaluacion_baya", int(existing["evaluacion_baya_id"]), True

        cursor.execute(
            """
            INSERT INTO core.ev_evaluacion_baya
                (lote_id, fecha, cortina, hilera, planta, evaluador_id,
                 tipo, origen, idempotency_key, source_row_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'mobile', %s, %s)
            RETURNING evaluacion_baya_id
            """,
            (*location, evaluador_id, data["tipo"], str(source.client_id), digest),
        )
        header_id = int(cursor.fetchone()["evaluacion_baya_id"])
        for observation in data["observaciones"]:
            cursor.execute(
                """
                INSERT INTO core.ev_baya_observacion
                    (evaluacion_baya_id, numero_muestra, numero_medicion,
                     estado_codigo, diametro_mm, peso_g)
                VALUES (%s, %s, 1, %s, %s, %s)
                """,
                (
                    header_id, observation["numero_muestra"],
                    observation.get("estado_codigo"), observation.get("diametro_mm"),
                    observation.get("peso_g"),
                ),
            )
        return "ev_evaluacion_baya", header_id, False


__all__ = ["PostgresEvaluationRepository"]
