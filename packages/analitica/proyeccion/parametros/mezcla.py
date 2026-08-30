"""Mezcla e interpolación de los componentes del challenger as-of."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .contratos import CLAVES, NOMBRE_MODELO, VERSION_MODELO, ConfiguracionParametrosAsOf


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


def _interpolar_componentes(
    tabla: pd.DataFrame,
    desplazamiento: int | float | pd.Series,
) -> pd.DataFrame:
    """Mueve frutos y peso en la curva, con desplazamiento global o por fila."""

    if tabla.empty:
        return tabla
    salida = tabla.copy()
    if isinstance(desplazamiento, pd.Series):
        desplazamientos = (
            pd.to_numeric(desplazamiento, errors="coerce").reindex(salida.index).fillna(0.0)
        )
    else:
        desplazamientos = pd.Series(float(desplazamiento), index=salida.index)
    desplazamientos = (np.rint(desplazamientos / 7.0) * 7.0).clip(-14, 14)
    for _, indices in salida.groupby(["campania", "lote_id"], sort=False).groups.items():
        # ``np.interp`` exige un eje creciente. El panel de Access suele venir
        # ordenado, pero el contrato no debe depender del orden de extracción.
        indices_ordenados = salida.loc[indices].sort_values("fecha_objetivo").index
        bloque = salida.loc[indices_ordenados].copy()
        x = pd.to_datetime(bloque.fecha_objetivo).map(pd.Timestamp.timestamp).to_numpy(float)
        if len(np.unique(x)) < 3:
            continue
        shifts = desplazamientos.loc[indices_ordenados].to_numpy(float)
        origen = x - shifts * 86400.0
        for columna in ("frutos_por_planta", "peso_baya_g"):
            if columna not in bloque:
                continue
            y = pd.to_numeric(bloque[columna], errors="coerce").to_numpy(float)
            valido = np.isfinite(y) & np.isfinite(x)
            if valido.sum() < 3:
                continue
            nuevo = np.interp(origen, x[valido], y[valido])
            salida.loc[indices_ordenados, columna] = nuevo
    if {"plantas", "frutos_por_planta", "peso_baya_g"} <= set(salida):
        salida["p50_kg"] = (
            pd.to_numeric(salida.plantas, errors="coerce")
            * pd.to_numeric(salida.frutos_por_planta, errors="coerce")
            * pd.to_numeric(salida.peso_baya_g, errors="coerce")
            / 1000.0
        ).clip(lower=0)
    salida["desplazamiento_dias"] = desplazamientos.astype(float)
    return salida


def _completar_gdd(tabla: pd.DataFrame, base: float | None, ventana: int | None) -> pd.DataFrame:
    salida = tabla.copy()
    salida["gdd_base"] = base
    salida["gdd_ventana"] = ventana
    if base is not None and ventana is not None:
        nombre = f"gdd_{str(base).replace('.', '_')}_{ventana}d"
        salida["gdd_utilizado"] = pd.to_numeric(
            salida.get(nombre, pd.Series(np.nan, index=salida.index)), errors="coerce"
        )
    else:
        salida["gdd_utilizado"] = np.nan
    return salida


def _mezclar_componentes(
    macro: pd.DataFrame,
    residual: pd.DataFrame,
    historial: pd.DataFrame,
    config: ConfiguracionParametrosAsOf,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    salida = macro.copy()
    pesos: dict[str, dict[str, Any]] = {}
    peso_por_banda = {}
    for banda in sorted(salida.banda_horizonte.dropna().astype(str).unique()):
        peso_por_banda[banda], pesos[banda] = seleccionar_peso_macro(historial, banda, config)
    peso = salida.banda_horizonte.astype(str).map(peso_por_banda).fillna(config.peso_macro_default)
    for columna in ("frutos_por_planta", "peso_baya_g"):
        valor_residual = (
            residual.set_index(CLAVES)[columna]
            .reindex(pd.MultiIndex.from_frame(salida[CLAVES]))
            .to_numpy(float)
        )
        valor_macro = pd.to_numeric(salida[columna], errors="coerce").to_numpy(float)
        valor_residual = np.where(np.isfinite(valor_residual), valor_residual, valor_macro)
        salida[columna] = (
            peso.to_numpy(float) * valor_macro + (1 - peso.to_numpy(float)) * valor_residual
        )
    salida["plantas"] = pd.to_numeric(salida.plantas, errors="coerce")
    salida["p50_kg"] = (
        salida.plantas * salida.frutos_por_planta * salida.peso_baya_g / 1000.0
    ).clip(lower=0)
    salida["p10_kg"] = np.nan
    salida["p90_kg"] = np.nan
    salida["peso_macro"] = peso.to_numpy(float)
    salida["kg_legacy"] = macro.p50_kg.to_numpy(float)
    salida["kg_residual"] = (
        residual.set_index(CLAVES)["p50_kg"]
        .reindex(pd.MultiIndex.from_frame(salida[CLAVES]))
        .to_numpy(float)
    )
    salida["kg_residual"] = np.where(
        np.isfinite(salida["kg_residual"]), salida["kg_residual"], salida["kg_legacy"]
    )
    # Contrato canónico para los selectores as-of. Se conservan ambos nombres
    # porque la persistencia usa ``kg_*`` y los estimadores históricos reciben
    # ``*_kg``; sin estos alias la mezcla siempre volvía al prior Macro.
    salida["legacy_kg"] = salida["kg_legacy"]
    salida["residual_kg"] = salida["kg_residual"]
    salida["correccion_frutos_factor"] = salida.frutos_por_planta / macro.frutos_por_planta.replace(
        0, np.nan
    )
    salida["correccion_peso_factor"] = salida.peso_baya_g / macro.peso_baya_g.replace(0, np.nan)
    salida["correccion_frutos_factor"] = salida.correccion_frutos_factor.replace(
        [np.inf, -np.inf], np.nan
    ).fillna(1.0)
    salida["correccion_peso_factor"] = salida.correccion_peso_factor.replace(
        [np.inf, -np.inf], np.nan
    ).fillna(1.0)
    salida["probabilidad_ocurrencia"] = np.nan
    salida["modelo"] = NOMBRE_MODELO
    salida["version_fuente"] = VERSION_MODELO
    salida["real_kg"] = np.nan
    salida["confianza"] = np.where(
        salida.legacy_n_observaciones.ge(config.minimo_obs_lote), "media", "baja"
    )
    return salida, pesos


__all__ = ["seleccionar_peso_macro"]
