"""Construcción de snapshots auditables de parámetros as-of."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _deltas_parametros(base: object, final: object) -> dict[str, float]:
    """Calcula ΔX/ΔO/ΔN/ΔA/ΔB sin esconder cambios del calibrador."""

    if not isinstance(base, dict) or not isinstance(final, dict):
        return {}
    campos = (
        "mu1",
        "sigma1",
        "N1",
        "mu2",
        "sigma2",
        "N2",
        "mu3",
        "sigma3",
        "N3",
        "peso_a",
        "peso_b",
        "peso_a2",
        "peso_b2",
        "peso_a3",
        "peso_b3",
    )
    salida: dict[str, float] = {}
    for campo in campos:
        try:
            valor_base = float(base[campo])
            valor_final = float(final[campo])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(valor_base) and np.isfinite(valor_final):
            salida[campo] = valor_final - valor_base
    return salida


def construir_snapshot_parametros(
    predicciones: pd.DataFrame,
    *,
    meta: dict[str, Any] | None = None,
    run_id: int | None = None,
    archivo_fuente: str | None = None,
    sha256_fuente: str | None = None,
) -> pd.DataFrame:
    """Construye filas para ``analytics.legacy_parameter_snapshot``."""

    if predicciones is None or predicciones.empty:
        return pd.DataFrame()
    meta = meta or {}
    filas = []
    for fila in predicciones.itertuples(index=False):
        parametros = getattr(fila, "parametros_legacy", {})
        if isinstance(parametros, str):
            parametros = {"detalle": parametros}
        parametros_base = getattr(fila, "legacy_parametros_base", parametros)
        if isinstance(parametros_base, str):
            parametros_base = {"detalle": parametros_base}
        deltas = _deltas_parametros(parametros_base, parametros)
        base = {
            "run_id": run_id,
            "campania": getattr(fila, "campania", None),
            "fecha_emision": getattr(fila, "fecha_emision", None),
            "lote_id": getattr(fila, "lote_id", None),
            "fundo": getattr(fila, "fundo", None),
            "modulo": getattr(fila, "modulo", None),
            "variedad": getattr(fila, "variedad", None),
            "nivel_calibracion": getattr(fila, "legacy_fuente_parametros", None),
            "n_observaciones_asof": getattr(fila, "legacy_n_observaciones", 0),
            "fuente_parametros": getattr(fila, "legacy_fuente_parametros", None),
            "archivo_fuente": getattr(fila, "legacy_archivo_fuente", None) or archivo_fuente,
            "sha256_fuente": getattr(fila, "legacy_sha256_fuente", None) or sha256_fuente,
            "parametros_base_json": parametros_base,
            "correcciones_json": {
                "parametros_delta": deltas,
                "frutos": getattr(fila, "correccion_frutos_factor", None),
                "peso": getattr(fila, "correccion_peso_factor", None),
                "desplazamiento_dias": getattr(fila, "desplazamiento_dias", 0),
                "peso_macro": getattr(fila, "peso_macro", 1.0),
            },
            "parametros_finales_json": {
                "base": parametros_base,
                "delta_parametros": deltas,
                "final": parametros,
                "correcciones": {
                    "frutos": getattr(fila, "correccion_frutos_factor", None),
                    "peso": getattr(fila, "correccion_peso_factor", None),
                    "desplazamiento_dias": getattr(fila, "desplazamiento_dias", 0),
                    "peso_macro": getattr(fila, "peso_macro", 1.0),
                },
            },
            "gdd_base": getattr(fila, "gdd_base", None),
            "gdd_ventana": getattr(fila, "gdd_ventana", None),
            "fecha_corte": getattr(fila, "fecha_emision", None),
        }
        filas.append(base)
    return pd.DataFrame(filas).drop_duplicates(["campania", "fecha_emision", "lote_id"])


__all__ = ["construir_snapshot_parametros"]
