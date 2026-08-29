"""Conversión del reporte de preflight a la tabla de calidad histórica."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd


def calidad_preflight(
    reporte: Mapping[str, Any],
    *,
    serializar: Callable[[Any], str],
) -> pd.DataFrame:
    """Mantiene la forma y severidad de los hallazgos del runner histórico."""

    filas: list[dict[str, Any]] = []
    for contrato in reporte.get("contratos", []):
        filas.append(
            {
                "regla": f"preflight_{contrato['regla']}",
                "estado": "error",
                "observados": 1,
                "afectados": int(contrato.get("afectados", 1)),
                "detalle": serializar(contrato),
            }
        )
    for gate in reporte.get("gates", []):
        filas.append(
            {
                "regla": f"preflight_{gate['regla']}",
                "estado": "ok" if gate.get("pasa") else "error",
                "observados": 1,
                "afectados": 0 if gate.get("pasa") else 1,
                "detalle": serializar(gate),
            }
        )
    return pd.DataFrame(filas)


__all__ = ["calidad_preflight"]
