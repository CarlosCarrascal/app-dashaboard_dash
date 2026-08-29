"""Identidad reproducible de configuraciones y tablas de proyección."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

import numpy as np
import pandas as pd


def _limpio_json(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {str(k): _limpio_json(v) for k, v in sorted(valor.items(), key=lambda x: str(x[0]))}
    if isinstance(valor, (list, tuple)):
        return [_limpio_json(v) for v in valor]
    if isinstance(valor, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(valor).isoformat()
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.floating, float)):
        return None if not np.isfinite(valor) else round(float(valor), 12)
    if isinstance(valor, (np.bool_,)):
        return bool(valor)
    if pd.isna(valor) if not isinstance(valor, (str, bytes)) else False:
        return None
    return valor


def json_reproducible(valor: Any) -> str:
    """Produce JSON estable para comparar configuraciones y manifiestos."""
    return json.dumps(
        _limpio_json(valor), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def sha256_dataframe(tabla: pd.DataFrame, columnas: tuple[str, ...] | list[str]) -> str:
    """Calcula una huella estable independiente del orden de las filas."""
    disponibles = [c for c in columnas if c in tabla]
    if not disponibles:
        return sha256(b"[]").hexdigest()
    t = tabla[disponibles].copy()
    for columna in t:
        if pd.api.types.is_datetime64_any_dtype(t[columna]):
            t[columna] = pd.to_datetime(t[columna], errors="coerce").dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_numeric_dtype(t[columna]):
            t[columna] = pd.to_numeric(t[columna], errors="coerce").round(10)
        else:
            t[columna] = t[columna].map(
                lambda v: json_reproducible(v) if isinstance(v, (dict, list, tuple)) else v
            )
    t = t.sort_values(disponibles, kind="mergesort", na_position="first").reset_index(drop=True)
    payload = t.to_json(orient="records", date_format="iso", double_precision=10)
    return sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["json_reproducible", "sha256_dataframe"]
