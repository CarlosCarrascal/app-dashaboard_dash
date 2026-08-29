"""Normalización de fechas y claves para comparar corridas operativas."""

from __future__ import annotations

import pandas as pd


def _fecha(valor: object) -> pd.Timestamp:
    fecha = pd.to_datetime(valor, errors="coerce")
    if pd.isna(fecha):
        raise ValueError(f"Fecha de emisión inválida: {valor!r}")
    return pd.Timestamp(fecha).normalize()


def _normalizar_claves(tabla: pd.DataFrame) -> pd.DataFrame:
    salida = tabla.copy()
    for columna in ("Paña", "ReiRe"):
        if columna in salida:
            salida[columna] = pd.to_numeric(salida[columna], errors="coerce").round(8)
    for columna in ("Fechaini", "FeCos"):
        if columna in salida:
            salida[columna] = pd.to_datetime(salida[columna], errors="coerce").dt.date
    return salida


def _campana_unica(tabla: pd.DataFrame) -> str | None:
    valores = tabla.get("Campaña", pd.Series(dtype=object)).dropna().astype(str).str.strip()
    valores = valores[valores.ne("")].unique().tolist()
    return valores[0] if len(valores) == 1 else None


__all__ = ["_campana_unica", "_fecha", "_normalizar_claves"]
