"""Serialización compatible del screening de deltas Excel."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _json_default(valor: object) -> object:
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, np.floating):
        return float(valor)
    if isinstance(valor, pd.Timestamp):
        return valor.isoformat()
    if isinstance(valor, Path):
        return str(valor)
    raise TypeError(f"No serializable: {type(valor)!r}")


__all__ = ["_json_default"]
