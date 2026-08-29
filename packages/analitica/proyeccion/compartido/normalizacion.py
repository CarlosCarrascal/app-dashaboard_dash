"""Validaciones puras de paneles reutilizadas por las familias de proyección.

Este módulo no conoce candidatos concretos, servicios, persistencia ni fachadas
legacy. Los módulos de dominio conservan las constantes y reexportan estas
funciones para mantener las rutas históricas.
"""

from __future__ import annotations

import pandas as pd

from .fechas import lunes_semana

CLAVE_RESIDUAL = [
    "campania",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "lote_id",
]

CLAVE_FORECAST = [
    "evaluation_contract_id",
    "campania",
    "modelo",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "lote_id",
]


def normalizar_panel(tabla: pd.DataFrame) -> pd.DataFrame:
    """Normaliza un panel de residual sin alterar su contrato de columnas."""
    requeridas = set(CLAVE_RESIDUAL + ["fundo", "modulo", "p50_kg", "real_kg"])
    faltantes = sorted(requeridas.difference(tabla.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas para calibracion residual: {faltantes}")
    t = tabla.copy()
    t["fecha_emision"] = pd.to_datetime(t.fecha_emision, errors="raise").dt.normalize()
    t["fecha_objetivo"] = pd.to_datetime(t.fecha_objetivo, errors="raise").dt.normalize()
    t["horizonte_semanas"] = pd.to_numeric(t.horizonte_semanas, errors="raise").astype(int)
    t["p50_kg"] = pd.to_numeric(t.p50_kg, errors="coerce")
    t["real_kg"] = pd.to_numeric(t.real_kg, errors="coerce")
    if t.duplicated(CLAVE_RESIDUAL).any():
        raise ValueError("El panel repite una clave lote-emision-objetivo")
    if (t.fecha_emision >= t.fecha_objetivo).any():
        raise ValueError("El panel contiene una emision contemporanea o futura")
    if t.p50_kg.isna().any() or t.p50_kg.lt(0).any():
        raise ValueError("p50_kg debe ser conocido y no negativo")
    t["semana_fin"] = t.fecha_objetivo + pd.to_timedelta(6, unit="D")
    return t.sort_values(["campania", "fecha_emision", "fecha_objetivo", "lote_id"])


def normalizar_forecast_candidate(tabla: pd.DataFrame) -> pd.DataFrame:
    """Normaliza y rechaza un panel que no sea forecast as-of coherente."""
    requeridas = set(CLAVE_FORECAST + ["p50_kg"])
    faltantes = sorted(requeridas.difference(tabla.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas candidate-only: {faltantes}")

    t = tabla.copy()
    t["fecha_emision"] = pd.to_datetime(t.fecha_emision, errors="raise").dt.normalize()
    t["fecha_objetivo"] = pd.to_datetime(t.fecha_objetivo, errors="raise").dt.normalize()
    t["horizonte_semanas"] = pd.to_numeric(t.horizonte_semanas, errors="raise").astype(int)
    t["p50_kg"] = pd.to_numeric(t.p50_kg, errors="coerce")
    if t[CLAVE_FORECAST].isna().any().any():
        raise ValueError("La clave candidate-only contiene nulos")
    if t.p50_kg.isna().any() or t.p50_kg.lt(0).any():
        raise ValueError("p50_kg debe ser conocido y no negativo")
    if (t.fecha_objetivo != lunes_semana(t.fecha_objetivo)).any():
        raise ValueError("fecha_objetivo debe ser el lunes de la semana objetivo")
    if (t.fecha_emision >= t.fecha_objetivo).any():
        raise ValueError("El forecast contiene una emisión contemporánea o futura")
    if t.duplicated(CLAVE_FORECAST).any():
        raise ValueError("El forecast repite una clave contractual completa")

    semana_emision = lunes_semana(t.fecha_emision)
    horizonte_calculado = ((t.fecha_objetivo - semana_emision).dt.days // 7).astype(int)
    if horizonte_calculado.ne(t.horizonte_semanas).any():
        raise ValueError("El horizonte declarado no coincide con emisión y objetivo")

    grano_semana = [
        "evaluation_contract_id",
        "campania",
        "modelo",
        "fecha_objetivo",
        "horizonte_semanas",
    ]
    emisiones = t.groupby(grano_semana, dropna=False).fecha_emision.nunique()
    if emisiones.gt(1).any():
        raise ValueError("Una semana objetivo mezcla emisiones entre lotes")
    return t.sort_values(["campania", "fecha_emision", "lote_id", "fecha_objetivo"]).reset_index(
        drop=True
    )


__all__ = [
    "CLAVE_FORECAST",
    "CLAVE_RESIDUAL",
    "normalizar_forecast_candidate",
    "normalizar_panel",
]
