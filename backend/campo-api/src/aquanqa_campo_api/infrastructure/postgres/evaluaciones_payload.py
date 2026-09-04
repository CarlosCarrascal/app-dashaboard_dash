"""Serialización estable de payloads de evaluaciones para PostgreSQL."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from ...modules.evaluaciones.rules import NormalizedEvaluation


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, UUID)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _payload_hash(normalized: NormalizedEvaluation) -> str:
    source = normalized.source
    payload = {
        "client_id": str(source.client_id),
        "module_key": source.module_key,
        "fecha": source.fecha.isoformat(),
        "captured_at": source.captured_at.isoformat() if source.captured_at else None,
        "lote_id": source.lote_id,
        "fundo": source.fundo,
        "modulo": source.modulo,
        "lote": source.lote,
        "cortina": source.cortina,
        "hilera": source.hilera,
        "planta": source.planta,
        "evaluador_id": source.evaluador_id,
        "evaluador_dni": source.evaluador_dni,
        "item": source.item,
        "piso": source.piso,
        "hora": source.hora.isoformat() if source.hora else None,
        "data": normalized.data,
    }
    serialized = json.dumps(
        _json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _history_payload(normalized: NormalizedEvaluation) -> dict[str, Any]:
    source = normalized.source
    return _json_safe(
        {
            "id": source.client_id,
            "module_key": source.module_key,
            "fecha": source.fecha,
            "captured_at": source.captured_at,
            "evaluador": source.evaluador or "",
            "evaluador_id": source.evaluador_id,
            "evaluador_dni": source.evaluador_dni or "",
            "lote_id": source.lote_id,
            "fundo": source.fundo or "",
            "modulo": source.modulo or "",
            "lote": source.lote or "",
            "cortina": source.cortina,
            "hilera": source.hilera,
            "planta": source.planta,
            "valores": source.valores,
        }
    )


__all__ = ["_history_payload", "_payload_hash"]
