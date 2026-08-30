"""Predicción y aplicación de configuraciones del loop por horizontes."""

from __future__ import annotations

from typing import Any

import pandas as pd

from analitica.proyeccion.horizonte import (
    ConfiguracionCorreccionHorizonte,
    aplicar_correccion_horizonte,
    ejecutar_loop_por_horizonte,
)


def _aplicar_mejores(
    base: pd.DataFrame,
    resultado: dict[str, Any],
    *,
    panel_historial: pd.DataFrame | None = None,
) -> pd.DataFrame:
    partes: list[pd.DataFrame] = []
    for horizonte, info in resultado["resultados"].items():
        mejor = info.get("mejor_por_desarrollo") or {}
        configuracion = mejor.get("configuracion")
        h = int(horizonte)
        sub = base.loc[base["horizonte_semanas"].eq(h)].copy()
        if not configuracion:
            sub["pred_kg"] = sub["p50_kg"]
        else:
            sub = aplicar_correccion_horizonte(
                sub,
                ConfiguracionCorreccionHorizonte(**configuracion),
                # Una configuración agnóstica al horizonte debe ver H2-H6
                # cerrados como un solo historial, aunque la salida se aplique
                # a un horizonte a la vez.
                panel_historial=panel_historial,
            )
        partes.append(sub)
    return pd.concat(partes, ignore_index=True) if partes else base.iloc[0:0].copy()


__all__ = [
    "_aplicar_mejores",
    "ConfiguracionCorreccionHorizonte",
    "aplicar_correccion_horizonte",
    "ejecutar_loop_por_horizonte",
]
