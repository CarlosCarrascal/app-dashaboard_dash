"""Utilidades reutilizables para construir y normalizar replays.

Este módulo contiene solo lógica de aplicación compartida. Las entradas y
salidas conservan el contrato que históricamente exponían los scripts de
replay, pero ningún servicio depende de un script ejecutable.
"""

from __future__ import annotations

import pandas as pd

from analitica.proyeccion.fenologico_v1 import cosecha_real_semanal


def semanas_cerradas(datos, campania: str) -> pd.DatetimeIndex:
    """Devuelve las semanas de una campaña cuyo cierre ya es observable."""

    reales = cosecha_real_semanal(datos)
    if reales.empty:
        raise ValueError(f"No hay cosecha real para {campania}")
    reales = reales[reales.campania.astype(str).eq(str(campania))].copy()
    if reales.empty:
        raise ValueError(f"No hay cosecha real para {campania}")
    max_fecha = pd.to_datetime(
        datos.cosecha.loc[datos.cosecha.campania.astype(str).eq(str(campania)), "fecha"],
        errors="coerce",
    ).max()
    min_semana = pd.to_datetime(reales.fecha_objetivo).min().normalize()
    max_semana = pd.to_datetime(reales.fecha_objetivo).max().normalize()
    # El objetivo es un lunes; solo se evalúa si ya pasó el domingo de cierre.
    max_cierre = max_semana
    while max_cierre + pd.Timedelta(days=6) > max_fecha:
        max_cierre -= pd.Timedelta(days=7)
    if max_cierre < min_semana:
        raise ValueError(f"La campaña {campania} no tiene semanas completas evaluables")
    return pd.date_range(min_semana, max_cierre, freq="7D")


def emisiones_completas(
    datos, campania: str, max_targets: int | None = None
) -> pd.DataFrame:
    """Construye las emisiones sintéticas de un replay de campaña."""

    semanas = semanas_cerradas(datos, campania)
    if max_targets is not None:
        semanas = semanas[:max_targets]
    # Emitir el lunes previo permite que la semana objetivo sea horizonte operativo 1.
    return pd.DataFrame(
        {
            "campania": str(campania),
            "fecha_emision": semanas - pd.Timedelta(days=7),
        }
    )


def normalizar_modelo(tabla: pd.DataFrame) -> pd.DataFrame:
    """Normaliza las columnas comunes del contrato de predicciones de replay."""

    salida = tabla.copy()
    for columna in ("fecha_emision", "fecha_objetivo", "origen_emision"):
        if columna in salida:
            salida[columna] = pd.to_datetime(salida[columna], errors="coerce").dt.normalize()
    salida["horizonte_semanas"] = 1
    salida["banda_horizonte"] = "operativo"
    salida["p10_kg"] = pd.to_numeric(salida.get("p10_kg"), errors="coerce")
    salida["p90_kg"] = pd.to_numeric(salida.get("p90_kg"), errors="coerce")
    salida["tipo_prediccion"] = "replay"
    salida["es_replay_ciego"] = True
    salida["es_curva_stitched"] = True
    salida["estado_evaluacion"] = "evaluada"
    return salida


__all__ = ["emisiones_completas", "normalizar_modelo", "semanas_cerradas"]
