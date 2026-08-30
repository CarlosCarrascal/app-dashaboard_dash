"""Persistencia JSON y hashes del contrato cross-campaign h1."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


def sha256_archivo(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _json_default(valor: object) -> object:
    if isinstance(valor, (pd.Timestamp, date)):
        return str(valor)
    if isinstance(valor, np.generic):
        return valor.item()
    if pd.isna(valor):
        return None
    raise TypeError(type(valor).__name__)


def escribir_json(resultado: dict[str, object], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


__all__ = ["escribir_json", "sha256_archivo"]
