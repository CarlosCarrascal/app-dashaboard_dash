"""Serialización determinista usada para las firmas de certificación."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha256(valor: Any) -> str:
    texto = json.dumps(valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


__all__ = ["_sha256", "hashlib", "json"]
