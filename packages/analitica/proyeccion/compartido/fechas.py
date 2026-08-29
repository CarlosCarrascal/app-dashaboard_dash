"""Primitivas temporales puras para unir observaciones con semántica as-of."""

from __future__ import annotations

import numpy as np
import pandas as pd


def lunes_semana(valores: pd.Series | pd.Timestamp) -> pd.Series | pd.Timestamp:
    """Normaliza fechas al lunes de su semana calendario."""
    if not isinstance(valores, pd.Series):
        fecha = pd.Timestamp(valores).normalize()
        return fecha - pd.to_timedelta(fecha.weekday(), unit="D")
    fechas = pd.to_datetime(valores, errors="coerce").astype("datetime64[ns]").dt.normalize()
    return fechas - pd.to_timedelta(fechas.dt.weekday, unit="D")


def ultimo_disponible(
    objetivos: pd.DataFrame,
    observaciones: pd.DataFrame,
    columnas: list[str],
    *,
    entidad: str | list[str] = "lote_id",
    fecha_observacion: str = "fecha",
    fecha_corte: str = "fecha_emision",
) -> pd.DataFrame:
    """Une la última observación ``<= fecha_corte`` dentro de cada entidad."""
    if objetivos.empty:
        return objetivos.copy()
    salida = objetivos.copy()
    entidades = [entidad] if isinstance(entidad, str) else list(entidad)
    if (
        observaciones.empty
        or not set(entidades) <= set(observaciones)
        or not set(entidades) <= set(salida)
    ):
        for columna in columnas:
            salida[columna] = np.nan
        salida[f"{fecha_observacion}_observada"] = pd.NaT
        return salida

    izq = salida.copy()
    izq[fecha_corte] = pd.to_datetime(izq[fecha_corte]).dt.normalize()
    izq["__orden"] = np.arange(len(izq))
    der = observaciones[[*entidades, fecha_observacion, *columnas]].copy()
    der[fecha_observacion] = pd.to_datetime(der[fecha_observacion]).dt.normalize()
    der = der.dropna(subset=[*entidades, fecha_observacion])
    der = der.rename(columns={fecha_observacion: f"{fecha_observacion}_observada"})
    fecha_der = f"{fecha_observacion}_observada"
    unido = pd.merge_asof(
        izq.sort_values([fecha_corte, *entidades]),
        der.sort_values([fecha_der, *entidades]),
        left_on=fecha_corte,
        right_on=fecha_der,
        by=entidades,
        direction="backward",
        allow_exact_matches=True,
    )
    unido = unido.sort_values("__orden").drop(columns="__orden")
    if (unido[fecha_der] > unido[fecha_corte]).fillna(False).any():
        raise AssertionError("Fuga temporal: una observación posterior entró al panel as-of.")
    return unido

__all__ = ["lunes_semana", "ultimo_disponible"]
