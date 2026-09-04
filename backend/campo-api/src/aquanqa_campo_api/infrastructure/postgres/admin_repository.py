"""Adaptador PostgreSQL de lectura para la superficie administrativa."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...modules.admin.repository import (
    AdminMutationConflictError,
    AdminMutationError,
    AdminMutationForbiddenError,
    AdminRepositoryError,
)
from ...modules.admin.schemas import (
    AdminEvaluationDetail,
    AdminEvaluationPage,
    AdminEvaluationQuery,
    AdminEvaluationSummary,
    AdminMasterPage,
    AdminMasterQuery,
    AdminMutation,
    EvaluationCorrectionRequest,
    MasterMutationRequest,
    MasterResource,
    UserMutationRequest,
)
from ...modules.evaluaciones.schemas import ModuleKey
from .admin_load_repository import AdminLoadRepositoryMixin
from .admin_mappers import evaluation_detail, evaluation_item, mutation, page_info
from .admin_quality_repository import AdminQualityRepositoryMixin
from .admin_queries import EVALUATION_ORDER, EVALUATIONS_CTE, MASTER_DEFINITIONS
from .connection import PostgresConnectionFactory


class PostgresAdminRepository(AdminLoadRepositoryMixin, AdminQualityRepositoryMixin):
    """Consultas acotadas y parametrizadas para el panel administrativo."""

    def __init__(
        self,
        connections: PostgresConnectionFactory,
        *,
        usuario_id: int | None = None,
        unrestricted: bool = True,
    ):
        self._connections = connections
        self._usuario_id = usuario_id
        self._unrestricted = unrestricted

    def _append_scope(
        self,
        conditions: list[str],
        params: list[Any],
        columns: dict[str, str],
    ) -> None:
        scope_sql, scope_params = self._scope_filter(columns)
        if scope_sql:
            conditions.append(scope_sql)
            params.extend(scope_params)

    def _scope_filter(self, columns: dict[str, str]) -> tuple[str | None, list[Any]]:
        if self._unrestricted or self._usuario_id is None or not columns:
            return None, []
        predicates = [
            f"(ua.{scope_name} IS NULL OR ua.{scope_name} = {column})"
            for scope_name, column in columns.items()
        ]
        return (
            "EXISTS ("
            "SELECT 1 FROM core.m_usuario_alcance ua "
            "WHERE ua.usuario_id = %s AND "
            + " AND ".join(predicates)
            + ")",
            [self._usuario_id],
        )

    def list_evaluations(self, query: AdminEvaluationQuery) -> AdminEvaluationPage:
        conditions, params = _evaluation_filters(query)
        self._append_scope(
            conditions,
            params,
            {
                "empresa_id": "empresa_id",
                "fundo_id": "fundo_id",
                "modulo_id": "modulo_id",
                "lote_id": "lote_id",
            },
        )
        where = " AND ".join(conditions) or "TRUE"
        order = EVALUATION_ORDER[query.sort_by]
        direction = "ASC" if query.sort_dir == "asc" else "DESC"
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"{EVALUATIONS_CTE}\nSELECT count(*) AS total "
                    f"FROM evaluaciones WHERE {where}",
                    params,
                )
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    f"""
                    {EVALUATIONS_CTE}
                    SELECT source_table || ':' || source_id::text AS id,
                           source_table, source_id, module_key, tipo, origen, fecha,
                           captured_at, lote_id, empresa, fundo, modulo, lote, variedad,
                           evaluador_id, evaluador, evaluador_dni, detalle
                    FROM evaluaciones
                    WHERE {where}
                    ORDER BY {order} {direction}, source_table, source_id
                    LIMIT %s OFFSET %s
                    """,
                    [*params, query.page_size, query.offset],
                )
                items = [evaluation_item(row) for row in cursor.fetchall()]
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudieron leer las evaluaciones") from exc
        return AdminEvaluationPage(
            items=items,
            meta=page_info(query.page, query.page_size, total),
        )

    def evaluation_summary(self, query: AdminEvaluationQuery) -> AdminEvaluationSummary:
        conditions, params = _evaluation_filters(query)
        self._append_scope(
            conditions,
            params,
            {
                "empresa_id": "empresa_id",
                "fundo_id": "fundo_id",
                "modulo_id": "modulo_id",
                "lote_id": "lote_id",
            },
        )
        where = " AND ".join(conditions) or "TRUE"
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    {EVALUATIONS_CTE}
                    SELECT count(*) AS total,
                           count(DISTINCT evaluador_id) FILTER (WHERE evaluador_id IS NOT NULL)
                               AS evaluadores,
                           count(DISTINCT lote_id) FILTER (WHERE lote_id IS NOT NULL) AS lotes,
                           min(fecha) AS desde,
                           max(fecha) AS hasta,
                           max(captured_at) AS ultima_captura
                    FROM evaluaciones
                    WHERE {where}
                    """,
                    params,
                )
                totals = cursor.fetchone()
                cursor.execute(
                    f"""
                    {EVALUATIONS_CTE}
                    SELECT module_key,
                           count(*) AS total,
                           sum(CASE
                               WHEN module_key IN ('baya', 'pesos')
                                   THEN jsonb_array_length(COALESCE(detalle->'observaciones', '[]'))
                               WHEN module_key = 'ramas'
                                   THEN jsonb_array_length(COALESCE(detalle->'mediciones', '[]'))
                               ELSE 1
                           END)::bigint AS muestras,
                           count(DISTINCT lote_id) AS lotes,
                           count(DISTINCT evaluador_id)
                               FILTER (WHERE evaluador_id IS NOT NULL) AS evaluadores,
                           min(fecha) AS desde,
                           max(fecha) AS hasta,
                           max(captured_at) AS ultima_captura,
                           jsonb_strip_nulls(jsonb_build_object(
                               'e1', sum((detalle->>'e1')::integer)
                                   FILTER (WHERE module_key = 'estadios'),
                               'e2', sum((detalle->>'e2')::integer)
                                   FILTER (WHERE module_key = 'estadios'),
                               'e3', sum((detalle->>'e3')::integer)
                                   FILTER (WHERE module_key = 'estadios'),
                               'e4', sum((detalle->>'e4')::integer)
                                   FILTER (WHERE module_key = 'estadios'),
                               'e5', sum((detalle->>'e5')::integer)
                                   FILTER (WHERE module_key = 'estadios'),
                               'flores', sum((detalle->>'n_flores')::integer)
                                   FILTER (WHERE module_key = 'flores'),
                               'cuajos', sum((detalle->>'cuajo')::integer)
                                   FILTER (WHERE module_key = 'flores'),
                               'yemas_abiertas', sum((detalle->>'yemas_abiertas')::integer)
                                   FILTER (WHERE module_key = 'flores'),
                               'yemas_por_abrir', sum((detalle->>'yemas_por_abrir')::integer)
                                   FILTER (WHERE module_key = 'flores'),
                               'yemas_muertas', sum((detalle->>'yemas_muertas')::integer)
                                   FILTER (WHERE module_key = 'flores'),
                               'brotes_tiernos', sum((detalle->>'brotes_tiernos')::integer)
                                   FILTER (WHERE module_key = 'flores'),
                               'brotes', sum((detalle->>'brotes')::integer)
                                   FILTER (WHERE module_key = 'brotes'),
                               'piso_1', sum((detalle->>'des1')::integer)
                                   FILTER (WHERE module_key = 'brotes'),
                               'piso_2', sum((detalle->>'des2')::integer)
                                   FILTER (WHERE module_key = 'brotes'),
                               'piso_3', sum((detalle->>'des3')::integer)
                                   FILTER (WHERE module_key = 'brotes'),
                               'ramas_menor_5mm', sum((detalle->>'ramas_menor5')::integer)
                                   FILTER (WHERE module_key = 'ramas'),
                               'ramas_mayor_5mm', sum((detalle->>'ramas_mayor5')::integer)
                                   FILTER (WHERE module_key = 'ramas'),
                               'diametro_promedio_mm', round(avg(
                                   CASE WHEN detalle ? 'diametro_promedio'
                                       THEN (detalle->>'diametro_promedio')::numeric END
                               ), 2),
                               'sospechosas', sum(
                                   COALESCE((detalle->>'mediciones_sospechosas')::integer, 0)
                               ) FILTER (WHERE module_key IN ('baya', 'ramas'))
                           )) AS indicadores
                    FROM evaluaciones
                    WHERE {where}
                    GROUP BY module_key
                    ORDER BY module_key
                    """,
                    params,
                )
                by_module = [dict(row) for row in cursor.fetchall()]
                present_modules = {row["module_key"] for row in by_module}
                by_module.extend(
                    {
                        "module_key": module_key,
                        "total": 0,
                        "muestras": 0,
                        "lotes": 0,
                        "evaluadores": 0,
                        "indicadores": {},
                    }
                    for module_key in (
                        "estadios",
                        "flores",
                        "baya",
                        "pesos",
                        "brotes",
                        "ramas",
                    )
                    if module_key not in present_modules
                )
                by_module.sort(
                    key=lambda row: (
                        "estadios",
                        "flores",
                        "baya",
                        "pesos",
                        "brotes",
                        "ramas",
                    ).index(row["module_key"])
                )
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo calcular el resumen de evaluaciones") from exc
        return AdminEvaluationSummary(
            total=int(totals["total"]),
            por_modulo=by_module,
            evaluadores=int(totals["evaluadores"]),
            lotes=int(totals["lotes"]),
            desde=totals["desde"],
            hasta=totals["hasta"],
            ultima_captura=totals["ultima_captura"],
        )

    def get_evaluation(
        self, module_key: ModuleKey, source_id: int, source_table: str | None = None
    ) -> AdminEvaluationDetail | None:
        scope_sql, scope_params = self._scope_filter(
            {
                "empresa_id": "empresa_id",
                "fundo_id": "fundo_id",
                "modulo_id": "modulo_id",
                "lote_id": "lote_id",
            }
        )
        scope_clause = f" AND {scope_sql}" if scope_sql else ""
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                source_clause = " AND source_table = %s" if source_table else ""
                cursor.execute(
                    f"""
                    {EVALUATIONS_CTE}
                    SELECT source_table || ':' || source_id::text AS id,
                           source_table, source_id, module_key, tipo, origen, fecha,
                           captured_at, lote_id, empresa, fundo, modulo, lote, variedad,
                           evaluador_id, evaluador, evaluador_dni, detalle
                    FROM evaluaciones
                    WHERE module_key = %s AND source_id = %s{source_clause}{scope_clause}
                    ORDER BY source_table
                    LIMIT 1
                    """,
                    [
                        module_key,
                        source_id,
                        *([source_table] if source_table else []),
                        *scope_params,
                    ],
                )
                row = cursor.fetchone()
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo leer el detalle de la evaluación") from exc
        return evaluation_detail(row) if row else None

    def correct_evaluation(
        self,
        module_key: ModuleKey,
        source_id: int,
        request: EvaluationCorrectionRequest,
        values: dict[str, object],
        usuario_id: int,
    ) -> AdminMutation:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT cambio_id, recurso, recurso_id, accion, antes, despues
                    FROM core.fn_admin_corregir_evaluacion(
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        usuario_id,
                        module_key,
                        source_id,
                        Jsonb(values),
                        request.source_table,
                        request.idempotency_key,
                        request.comentario,
                    ),
                )
                row = cursor.fetchone()
        except psycopg.Error as exc:
            if getattr(exc, "sqlstate", None) == "42501":
                raise AdminMutationForbiddenError(_database_message(exc)) from exc
            if (
                getattr(exc, "sqlstate", None) == "23505"
                or "idempotency_key" in _database_message(exc)
            ):
                raise AdminMutationConflictError(_database_message(exc)) from exc
            if _is_mutation_error(exc):
                raise AdminMutationError(_database_message(exc)) from exc
            raise AdminRepositoryError("No se pudo corregir la evaluación") from exc
        if row is None:
            raise AdminRepositoryError("La corrección no devolvió un resultado")
        return mutation(row, request.idempotency_key, "Evaluación corregida y auditada.")

    def mutate_master(
        self,
        resource: MasterResource,
        resource_id: int | None,
        request: MasterMutationRequest,
        usuario_id: int,
    ) -> AdminMutation:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT cambio_id, recurso, recurso_id, accion, antes, despues
                    FROM core.fn_admin_mutar_maestro(%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        usuario_id,
                        resource,
                        resource_id,
                        Jsonb(request.valores),
                        request.idempotency_key,
                        request.comentario,
                    ),
                )
                row = cursor.fetchone()
        except psycopg.Error as exc:
            if getattr(exc, "sqlstate", None) == "42501":
                raise AdminMutationForbiddenError(_database_message(exc)) from exc
            if (
                getattr(exc, "sqlstate", None) == "23505"
                or "idempotency_key" in _database_message(exc)
            ):
                raise AdminMutationConflictError(_database_message(exc)) from exc
            if _is_mutation_error(exc):
                raise AdminMutationError(_database_message(exc)) from exc
            raise AdminRepositoryError(f"No se pudo modificar el maestro {resource}") from exc
        if row is None:
            raise AdminRepositoryError("La mutación del maestro no devolvió un resultado")
        return mutation(row, request.idempotency_key, "Maestro actualizado y auditado.")

    def list_master(self, resource: MasterResource, query: AdminMasterQuery) -> AdminMasterPage:
        definition = MASTER_DEFINITIONS[resource]
        conditions = [definition["where"]]
        params: list[Any] = []
        if query.search:
            conditions.append(f"{definition['search']} ILIKE %s")
            params.append(f"%{query.search}%")
        _master_parent_filters(resource, query, conditions, params)
        self._append_scope(conditions, params, _master_scope_columns(resource))
        if query.activo is not None and resource in {
            "empresas",
            "fundos",
            "modulos",
            "evaluadores",
        }:
            active_column = {
                "empresas": "activo",
                "fundos": "f.activo",
                "modulos": "m.activo",
                "evaluadores": "activo",
            }[resource]
            conditions.append(f"{active_column} = %s")
            params.append(query.activo)
        where = " AND ".join(conditions)
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT count(*) AS total FROM {definition['from']} WHERE {where}",
                    params,
                )
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    f"""
                    SELECT {definition['select']}
                    FROM {definition['from']}
                    WHERE {where}
                    ORDER BY {definition['order']}
                    LIMIT %s OFFSET %s
                    """,
                    [*params, query.page_size, query.offset],
                )
                items = [dict(row) for row in cursor.fetchall()]
        except psycopg.Error as exc:
            raise AdminRepositoryError(f"No se pudo leer el maestro {resource}") from exc
        return AdminMasterPage(
            items=items,
            meta=page_info(query.page, query.page_size, total),
        )

    def mutate_user(
        self,
        usuario_id: int | None,
        request: UserMutationRequest,
        actor_id: int,
        values: dict[str, object],
    ) -> AdminMutation:
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT cambio_id, recurso, recurso_id, accion, antes, despues
                    FROM core.fn_admin_mutar_usuario(%s, %s, %s, %s, %s)
                    """,
                    (
                        actor_id,
                        usuario_id,
                        Jsonb(values),
                        request.idempotency_key,
                        request.comentario,
                    ),
                )
                row = cursor.fetchone()
        except psycopg.Error as exc:
            if getattr(exc, "sqlstate", None) == "42501":
                raise AdminMutationForbiddenError(_database_message(exc)) from exc
            if (
                getattr(exc, "sqlstate", None) == "23505"
                or "idempotency_key" in _database_message(exc)
            ):
                raise AdminMutationConflictError(_database_message(exc)) from exc
            if _is_mutation_error(exc):
                raise AdminMutationError(_database_message(exc)) from exc
            raise AdminRepositoryError("No se pudo modificar el usuario") from exc
        if row is None:
            raise AdminRepositoryError("La mutación del usuario no devolvió un resultado")
        return mutation(row, request.idempotency_key, "Usuario actualizado y auditado.")

    def list_roles(self, query: AdminMasterQuery) -> AdminMasterPage:
        conditions = ["TRUE"]
        params: list[Any] = []
        if query.search:
            conditions.append("concat_ws(' ', r.codigo, r.descripcion) ILIKE %s")
            params.append(f"%{query.search}%")
        where = " AND ".join(conditions)
        source = (
            "core.m_rol r LEFT JOIN core.m_rol_permiso rp ON rp.rol_id = r.rol_id "
            "LEFT JOIN core.m_permiso p ON p.permiso_id = rp.permiso_id"
        )
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT count(DISTINCT r.rol_id) AS total FROM {source} WHERE {where}",
                    params,
                )
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    f"""
                    SELECT r.rol_id, r.codigo, r.descripcion,
                           COALESCE(
                               jsonb_agg(
                                   jsonb_build_object(
                                       'codigo', p.codigo, 'descripcion', p.descripcion
                                   )
                                   ORDER BY p.codigo
                               ) FILTER (WHERE p.permiso_id IS NOT NULL),
                               '[]'::jsonb
                           ) AS permisos
                    FROM {source}
                    WHERE {where}
                    GROUP BY r.rol_id, r.codigo, r.descripcion
                    ORDER BY r.codigo, r.rol_id
                    LIMIT %s OFFSET %s
                    """,
                    [*params, query.page_size, query.offset],
                )
                items = [dict(row) for row in cursor.fetchall()]
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo leer el maestro de roles") from exc
        return AdminMasterPage(items=items, meta=page_info(query.page, query.page_size, total))

    def list_users(self, query: AdminMasterQuery) -> AdminMasterPage:
        conditions = ["TRUE"]
        params: list[Any] = []
        if query.search:
            conditions.append(
                "concat_ws(' ', u.email, u.nombre, r.codigo, ev.dni, "
                "ev.nombres, ev.apellidos) ILIKE %s"
            )
            params.append(f"%{query.search}%")
        if query.activo is not None:
            conditions.append("u.activo = %s")
            params.append(query.activo)
        where = " AND ".join(conditions)
        source = (
            "core.m_usuario u JOIN core.m_rol r ON r.rol_id = u.rol_id "
            "LEFT JOIN core.m_evaluador ev ON ev.evaluador_id = u.evaluador_id"
        )
        select = (
            "u.usuario_id, u.email, u.nombre, u.rol_id, r.codigo AS rol, "
            "r.descripcion AS rol_descripcion, u.evaluador_id, "
            "btrim(concat_ws(' ', ev.nombres, ev.apellidos)) AS evaluador, "
            "u.activo, u.ultimo_acceso, u.creado_en, "
            "COALESCE((SELECT jsonb_agg(jsonb_build_object("
            "'empresa_id', a.empresa_id, 'fundo_id', a.fundo_id, "
            "'modulo_id', a.modulo_id, 'lote_id', a.lote_id) "
            "ORDER BY a.alcance_id) FROM core.m_usuario_alcance a "
            "WHERE a.usuario_id = u.usuario_id), '[]'::jsonb) AS alcances"
        )
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT count(*) AS total FROM {source} WHERE {where}", params
                )
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    f"""
                    SELECT {select}
                    FROM {source}
                    WHERE {where}
                    ORDER BY u.nombre, u.usuario_id
                    LIMIT %s OFFSET %s
                    """,
                    [*params, query.page_size, query.offset],
                )
                items = [dict(row) for row in cursor.fetchall()]
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo leer el maestro de usuarios") from exc
        return AdminMasterPage(items=items, meta=page_info(query.page, query.page_size, total))

    def _list_simple_master(
        self,
        query: AdminMasterQuery,
        *,
        select: str,
        source: str,
        search: str,
        order: str,
    ) -> AdminMasterPage:
        conditions = ["TRUE"]
        params: list[Any] = []
        if query.search:
            conditions.append(f"{search} ILIKE %s")
            params.append(f"%{query.search}%")
        where = " AND ".join(conditions)
        try:
            with self._connections.connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT count(*) AS total FROM {source} WHERE {where}", params
                )
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    f"""
                    SELECT {select}
                    FROM {source}
                    WHERE {where}
                    ORDER BY {order}
                    LIMIT %s OFFSET %s
                    """,
                    [*params, query.page_size, query.offset],
                )
                items = [dict(row) for row in cursor.fetchall()]
        except psycopg.Error as exc:
            raise AdminRepositoryError("No se pudo leer el catálogo solicitado") from exc
        return AdminMasterPage(items=items, meta=page_info(query.page, query.page_size, total))


def _evaluation_filters(query: AdminEvaluationQuery) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    for field in ("module_key", "empresa_id", "fundo_id", "modulo_id", "lote_id", "evaluador_id"):
        value = getattr(query, field)
        if value is not None:
            conditions.append(f"{field} = %s")
            params.append(value)
    if query.search:
        conditions.append(
            "concat_ws(' ', source_table, source_id, module_key, tipo, origen, empresa, "
            "fundo, modulo, lote, variedad, evaluador, evaluador_dni, detalle::text) ILIKE %s"
        )
        params.append(f"%{query.search}%")
    if query.desde:
        conditions.append("fecha >= %s")
        params.append(query.desde)
    if query.hasta:
        conditions.append("fecha <= %s")
        params.append(query.hasta)
    return conditions, params


def _master_parent_filters(
    resource: MasterResource,
    query: AdminMasterQuery,
    conditions: list[str],
    params: list[Any],
) -> None:
    prefixes = {
        "empresas": {"empresa_id": "empresa_id"},
        "fundos": {"empresa_id": "f.empresa_id"},
        "modulos": {"empresa_id": "f.empresa_id", "fundo_id": "m.fundo_id"},
        "lotes": {
            "empresa_id": "f.empresa_id",
            "fundo_id": "f.fundo_id",
            "modulo_id": "l.modulo_id",
        },
        "muestreo": {
            "empresa_id": "e.empresa_id",
            "fundo_id": "f.fundo_id",
            "modulo_id": "m.modulo_id",
        },
    }.get(resource, {})
    for field, column in prefixes.items():
        value = getattr(query, field)
        if value is not None:
            conditions.append(f"{column} = %s")
            params.append(value)


def _master_scope_columns(resource: MasterResource) -> dict[str, str]:
    return {
        "empresas": {"empresa_id": "empresa_id"},
        "fundos": {"empresa_id": "f.empresa_id", "fundo_id": "f.fundo_id"},
        "modulos": {
            "empresa_id": "f.empresa_id",
            "fundo_id": "m.fundo_id",
            "modulo_id": "m.modulo_id",
        },
        "lotes": {
            "empresa_id": "f.empresa_id",
            "fundo_id": "f.fundo_id",
            "modulo_id": "m.modulo_id",
            "lote_id": "l.lote_id",
        },
        "muestreo": {
            "empresa_id": "e.empresa_id",
            "fundo_id": "f.fundo_id",
            "modulo_id": "m.modulo_id",
            "lote_id": "s.lote_id",
        },
    }.get(resource, {})


__all__ = ["PostgresAdminRepository"]


def _database_message(error: psycopg.Error) -> str:
    return str(getattr(error.diag, "message_primary", None) or error).strip()


def _is_mutation_error(error: psycopg.Error) -> bool:
    sqlstate = getattr(error, "sqlstate", None)
    return sqlstate in {"P0001", "22007", "22023", "22P02", "23503", "23505", "23514"}
