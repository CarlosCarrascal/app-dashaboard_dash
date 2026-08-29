"""Selección de la confianza en Macro frente al componente residual."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .contratos import ConfiguracionParametrosAsOf


def seleccionar_peso_macro(
    historial: pd.DataFrame,
    banda: str,
    config: ConfiguracionParametrosAsOf | None = None,
) -> tuple[float, dict[str, Any]]:
    """Selecciona la mezcla Macro/residual solo con errores OOS anteriores.

    ``peso_macro=1`` equivale a confiar en la curva biológica. El residual solo gana
    influencia si mejora sobre el mismo universo y el peso se contrae hacia el prior
    para no reaccionar a una sola semana o a un solo lote.
    """

    config = config or ConfiguracionParametrosAsOf()
    if historial is None or historial.empty:
        return config.peso_macro_default, {"n": 0, "metodo": "prior_macro"}
    tabla = historial.copy()
    requeridas = {"real_kg", "legacy_kg", "residual_kg"}
    if not requeridas <= set(tabla):
        return config.peso_macro_default, {"n": 0, "metodo": "prior_macro_columnas_faltantes"}
    if "banda_horizonte" in tabla:
        parte = tabla[tabla.banda_horizonte.eq(banda)].copy()
        if len(parte) < 10:
            parte = tabla.copy()
    else:
        parte = tabla.copy()
    parte = parte.dropna(subset=list(requeridas))
    parte = parte[parte.real_kg.ge(0)]
    if parte.empty:
        return config.peso_macro_default, {"n": 0, "metodo": "prior_macro_sin_historia"}
    candidatos = np.linspace(config.peso_macro_min, config.peso_macro_max, 18)
    errores = []
    for peso in candidatos:
        combinado = peso * parte.legacy_kg + (1 - peso) * parte.residual_kg
        errores.append(float(np.abs(combinado - parte.real_kg).sum()))
    indice = int(np.argmin(errores))
    peso_crudo = float(candidatos[indice])
    n = len(parte)
    peso = (n * peso_crudo + config.regularizacion_peso * config.peso_macro_default) / (
        n + config.regularizacion_peso
    )
    detalle = {
        "n": int(n),
        "banda": banda,
        "peso_crudo": peso_crudo,
        "peso_final": float(peso),
        "mae_crudo": errores[indice] / max(n, 1),
        "metodo": "grid_oos_con_shrinkage",
    }
    return float(np.clip(peso, config.peso_macro_min, config.peso_macro_max)), detalle


__all__ = ["seleccionar_peso_macro"]
