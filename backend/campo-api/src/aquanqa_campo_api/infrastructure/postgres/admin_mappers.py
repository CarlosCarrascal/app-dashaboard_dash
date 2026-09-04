"""Conversión de filas PostgreSQL a contratos administrativos."""

from __future__ import annotations

from math import ceil
from typing import Any
from uuid import UUID

from ...modules.admin.schemas import (
    AdminEvaluationDetail,
    AdminEvaluationItem,
    AdminLoadItem,
    AdminMutation,
    AdminQARejectItem,
    ImportManifest,
    ImportResult,
    PageInfo,
)
from ...modules.evaluaciones.schemas import EvaluationCreate


def evaluation_item(row: dict[str, Any]) -> AdminEvaluationItem:
    return AdminEvaluationItem(
        id=row["id"],
        source_table=row["source_table"],
        source_id=int(row["source_id"]),
        module_key=row["module_key"],
        tipo=row["tipo"],
        origen=row["origen"],
        fecha=row["fecha"],
        captured_at=row["captured_at"],
        lote_id=row["lote_id"],
        empresa=row["empresa"] or "",
        fundo=row["fundo"] or "",
        modulo=row["modulo"] or "",
        lote=row["lote"] or "",
        variedad=row["variedad"] or "",
        evaluador_id=row["evaluador_id"],
        evaluador=row["evaluador"] or "",
        evaluador_dni=row["evaluador_dni"] or "",
        detalle=row["detalle"] or {},
    )


def evaluation_detail(row: dict[str, Any]) -> AdminEvaluationDetail:
    return AdminEvaluationDetail.model_validate(evaluation_item(row).model_dump())


def mutation(row: dict[str, Any], idempotency_key: UUID, message: str) -> AdminMutation:
    return AdminMutation(
        cambio_id=int(row["cambio_id"]),
        recurso=row["recurso"],
        recurso_id=int(row["recurso_id"]),
        accion=row["accion"],
        antes=row["antes"],
        despues=row["despues"] or {},
        idempotency_key=idempotency_key,
        mensaje=message,
    )


def qa_item(row: dict[str, Any]) -> AdminQARejectItem:
    return AdminQARejectItem(
        rechazo_id=int(row["rechazo_id"]),
        tabla_origen=row["tabla_origen"],
        tabla_destino=row["tabla_destino"],
        motivo=row["motivo"],
        hallazgo=row["hallazgo"],
        detalle=row["detalle"],
        fila=row["fila"] or {},
        cargado_en=row["cargado_en"],
        source_snapshot_id=row["source_snapshot_id"],
        migracion_run_id=row["migracion_run_id"],
        bloque_ejecucion_id=row["bloque_ejecucion_id"],
        excede_umbral=bool(row["excede_umbral"]),
        estado_revision=row["estado_revision"] or "pendiente",
        comentario_revision=row["comentario_revision"],
        revisado_en=row["revisado_en"],
        revisado_por=row["revisado_por"],
    )


def import_manifest(row: dict[str, Any]) -> ImportManifest:
    payloads = [EvaluationCreate.model_validate(item) for item in (row["payloads"] or [])]
    result = ImportResult.model_validate(row["resultado"]) if row["resultado"] else None
    return ImportManifest(
        carga_id=row["carga_id"],
        filename=row["archivo_nombre"],
        file_sha256=row["archivo_sha256"],
        estado=row["estado"],
        payloads=payloads,
        total_rows=int(row["filas_total"]),
        valid_rows=int(row["filas_validas"]),
        invalid_rows=int(row["filas_invalidas"]),
        result=result,
        error=row["error"],
    )


def load_item(row: dict[str, Any]) -> AdminLoadItem:
    return AdminLoadItem(
        carga_id=row["carga_id"],
        archivo_nombre=row["archivo_nombre"],
        archivo_sha256=row["archivo_sha256"],
        usuario_id=int(row["usuario_id"]),
        usuario=row["usuario"],
        estado=row["estado"],
        filas_total=int(row["filas_total"]),
        filas_validas=int(row["filas_validas"]),
        filas_invalidas=int(row["filas_invalidas"]),
        filas_aceptadas=int(row["filas_aceptadas"]),
        filas_duplicadas=int(row["filas_duplicadas"]),
        error=row["error"],
        creado_en=row["creado_en"],
        iniciado_en=row["iniciado_en"],
        finalizado_en=row["finalizado_en"],
    )


def page_info(page: int, page_size: int, total: int) -> PageInfo:
    return PageInfo(
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )


__all__ = [
    "evaluation_detail",
    "evaluation_item",
    "import_manifest",
    "load_item",
    "mutation",
    "page_info",
    "qa_item",
]
