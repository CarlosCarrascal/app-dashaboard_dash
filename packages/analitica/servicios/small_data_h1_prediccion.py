"""Construcción de panel y predicción rolling de small data H1."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor, Ridge
from sklearn.preprocessing import StandardScaler

from .small_data_h1_configuracion import FEATURE_SETS, Configuracion


def construir_panel_fundo(universo_lote: pd.DataFrame) -> pd.DataFrame:
    """Agrega a fundo-semana y crea únicamente features verificables as-of."""

    dimensiones = [
        "campania",
        "fecha_emision",
        "fecha_objetivo",
        "semana_fin",
        "semana_objetivo",
        "fundo_operativo",
    ]
    panel = universo_lote.groupby(dimensiones, as_index=False, dropna=False).agg(
        macro_kg=("macro_kg", "sum"),
        real_kg=("real_kg", "sum"),
        n_lotes=("lote_id", "size"),
    )
    panel = panel.sort_values(["fecha_objetivo", "fundo_operativo"], kind="stable")
    panel["log_macro"] = np.log1p(panel.macro_kg.clip(lower=0.0))
    semana_iso = panel.fecha_objetivo.dt.isocalendar().week.astype(float)
    panel["fase_sin"] = np.sin(2.0 * np.pi * semana_iso / 52.1775)
    panel["fase_cos"] = np.cos(2.0 * np.pi * semana_iso / 52.1775)
    panel["residuo_objetivo"] = np.log1p(panel.real_kg.clip(lower=0.0)) - panel.log_macro

    empresa = panel.groupby(
        ["campania", "fecha_emision", "fecha_objetivo", "semana_fin", "semana_objetivo"],
        as_index=False,
    ).agg(macro_kg=("macro_kg", "sum"), real_kg=("real_kg", "sum"))
    empresa["residuo"] = np.log1p(empresa.real_kg.clip(lower=0.0)) - np.log1p(
        empresa.macro_kg.clip(lower=0.0)
    )

    features: list[dict[str, float | int]] = []
    for fila in panel.itertuples(index=False):
        historia_local = panel.loc[
            panel.fundo_operativo.eq(fila.fundo_operativo)
            & panel.semana_fin.lt(fila.fecha_emision)
        ].sort_values("semana_fin", kind="stable")
        historia_empresa = empresa.loc[empresa.semana_fin.lt(fila.fecha_emision)].sort_values(
            "semana_fin", kind="stable"
        )
        # La forma de forecasts Macro emitidos previamente sí era conocida al
        # corte, aunque la semana inmediatamente anterior aún no tenga real.
        # Solo se usa Macro, nunca el resultado posterior de esas semanas.
        macro_previamente_emitida = panel.loc[
            panel.fundo_operativo.eq(fila.fundo_operativo)
            & panel.fecha_emision.lt(fila.fecha_emision)
        ].sort_values("fecha_emision", kind="stable")
        residuos_locales = historia_local.residuo_objetivo.tail(3)
        residuos_empresa = historia_empresa.residuo.tail(3)
        macro_anterior = (
            float(historia_local.macro_kg.iloc[-1]) if len(historia_local) else float(fila.macro_kg)
        )
        ultimas_macros = macro_previamente_emitida.macro_kg.tail(2).astype(float).tolist()
        macro_previa = ultimas_macros[-1] if ultimas_macros else float(fila.macro_kg)
        macro_previa_2 = ultimas_macros[-2] if len(ultimas_macros) >= 2 else macro_previa
        crecimiento_1 = float(np.log1p(max(fila.macro_kg, 0.0))) - float(
            np.log1p(max(macro_previa, 0.0))
        )
        crecimiento_previo = float(np.log1p(max(macro_previa, 0.0))) - float(
            np.log1p(max(macro_previa_2, 0.0))
        )
        features.append(
            {
                "lag_error_1": float(residuos_locales.iloc[-1]) if len(residuos_locales) else 0.0,
                "lag_error_media3": (
                    float(residuos_locales.mean()) if len(residuos_locales) else 0.0
                ),
                "lag_error_empresa_media3": (
                    float(residuos_empresa.mean()) if len(residuos_empresa) else 0.0
                ),
                "crecimiento_macro": float(np.log1p(max(fila.macro_kg, 0.0)))
                - float(np.log1p(max(macro_anterior, 0.0))),
                "crecimiento_macro_1": crecimiento_1,
                "aceleracion_macro": crecimiento_1 - crecimiento_previo,
                "n_historia_asof": int(len(historia_local)),
                "max_semana_historia": (
                    int(historia_local.semana_objetivo.iloc[-1]) if len(historia_local) else 0
                ),
            }
        )
    panel = pd.concat([panel.reset_index(drop=True), pd.DataFrame(features)], axis=1)
    return panel


def _ajustar_modelo(config: Configuracion, x: np.ndarray, y: np.ndarray) -> Any:
    if config.estimador == "ridge":
        return Ridge(alpha=config.alpha).fit(x, y)
    return HuberRegressor(
        alpha=config.alpha,
        epsilon=config.epsilon,
        max_iter=1000,
    ).fit(x, y)


def predecir_rolling(panel: pd.DataFrame, config: Configuracion) -> pd.DataFrame:
    """Predice cada origen usando solo observaciones cerradas antes de emitir."""

    columnas = list(FEATURE_SETS[config.feature_set])
    salida = panel.copy().sort_values(["fecha_emision", "fundo_operativo"], kind="stable")
    salida["candidate_kg"] = salida.macro_kg.astype(float)
    salida["correccion_log"] = 0.0
    salida["modelo_ajustado"] = False
    salida["n_entrenamiento"] = 0
    salida["max_semana_entrenamiento"] = 0

    grupos = salida.groupby(["fecha_emision", "fecha_objetivo"], sort=True).groups
    for (fecha_emision, _), indices in grupos.items():
        entrenamiento = salida.loc[
            salida.semana_fin.lt(pd.Timestamp(fecha_emision)) & salida.real_kg.notna()
        ].copy()
        objetivo = salida.loc[indices]
        if len(entrenamiento) < 20 or entrenamiento.semana_objetivo.nunique() < 5:
            continue
        x_train = entrenamiento[columnas].replace([np.inf, -np.inf], np.nan)
        medianas = x_train.median(numeric_only=True).fillna(0.0)
        x_train = x_train.fillna(medianas).fillna(0.0)
        x_test = objetivo[columnas].replace([np.inf, -np.inf], np.nan)
        x_test = x_test.fillna(medianas).fillna(0.0)
        escalador = StandardScaler()
        xt = escalador.fit_transform(x_train)
        xv = escalador.transform(x_test)
        try:
            modelo = _ajustar_modelo(
                config,
                xt,
                entrenamiento.residuo_objetivo.to_numpy(float),
            )
            correccion = np.asarray(modelo.predict(xv), dtype=float)
        except (ValueError, FloatingPointError):
            continue
        correccion = np.clip(
            correccion,
            np.log(config.factor_minimo),
            np.log(config.factor_maximo),
        )
        pred = np.expm1(objetivo.log_macro.to_numpy(float) + correccion)
        salida.loc[indices, "candidate_kg"] = np.maximum(pred, 0.0)
        salida.loc[indices, "correccion_log"] = correccion
        salida.loc[indices, "modelo_ajustado"] = True
        salida.loc[indices, "n_entrenamiento"] = len(entrenamiento)
        salida.loc[indices, "max_semana_entrenamiento"] = int(entrenamiento.semana_objetivo.max())
    return salida.sort_values(["fecha_objetivo", "fundo_operativo"], kind="stable")


def aplicar_candidato_a_lotes(
    universo_lote: pd.DataFrame,
    prediccion_fundo: pd.DataFrame,
) -> pd.DataFrame:
    claves = ["campania", "fecha_emision", "fecha_objetivo", "fundo_operativo"]
    factores = prediccion_fundo[claves + ["macro_kg", "candidate_kg"]].copy()
    factores["factor_candidato"] = np.where(
        factores.macro_kg.gt(0.0),
        factores.candidate_kg / factores.macro_kg,
        1.0,
    )
    lotes = universo_lote.merge(
        factores[claves + ["factor_candidato"]],
        on=claves,
        how="left",
        validate="many_to_one",
    )
    if lotes.factor_candidato.isna().any():
        raise AssertionError("El candidato no cubrió todo el universo Macro")
    lotes["candidate_kg"] = lotes.macro_kg * lotes.factor_candidato
    return lotes


__all__ = [
    "FEATURE_SETS",
    "Configuracion",
    "_ajustar_modelo",
    "aplicar_candidato_a_lotes",
    "construir_panel_fundo",
    "predecir_rolling",
]
