"""Modelos rolling y configuración del screening cross-campaign h1."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor, Ridge
from sklearn.preprocessing import StandardScaler

from .cross_campaign_lectura import FUNDOS

FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "compacto": (
        "log_macro",
        "participacion_macro",
        "pendiente_macro",
        "pendiente_macro_empresa",
        "residuo_fundo_ultimo",
        "residuo_fundo_media3",
        "residuo_empresa_media3",
        "fase_sin",
        "fase_cos",
        "log_n_historia",
    ),
    "forma_estado": (
        "log_macro",
        "participacion_macro",
        "pendiente_macro",
        "aceleracion_macro",
        "pendiente_macro_empresa",
        "residuo_fundo_ultimo",
        "residuo_fundo_media3",
        "residuo_fundo_media6",
        "residuo_empresa_media3",
        "log_real_ultimo",
        "tendencia_real",
        "fase_sin",
        "fase_cos",
        "log_n_historia",
    ),
}


@dataclass(frozen=True)
class Configuracion:
    estimador: str
    feature_set: str = "compacto"
    alpha: float = 10.0
    epsilon_huber: float = 1.35
    lookback: int = 0
    shrink_fundo: float = 8.0
    decaimiento: float = 0.92
    peso_correccion: float = 0.50
    factor_minimo: float = 0.70
    factor_maximo: float = 1.45

    @property
    def id(self) -> str:
        if self.estimador == "bayes_shrinkage":
            return (
                f"bayes-l{self.lookback}-k{self.shrink_fundo:g}-"
                f"d{self.decaimiento:.2f}-w{self.peso_correccion:.2f}-"
                f"clip{self.factor_minimo:g}_{self.factor_maximo:g}"
            )
        return (
            f"{self.estimador}-{self.feature_set}-a{self.alpha:g}-"
            f"e{self.epsilon_huber:g}-w{self.peso_correccion:.2f}-"
            f"clip{self.factor_minimo:g}_{self.factor_maximo:g}"
        )


def configuraciones() -> list[Configuracion]:
    clips = ((0.65, 1.55), (0.80, 1.35))
    salida = [
        Configuracion(
            estimador="ridge",
            feature_set=features,
            alpha=alpha,
            peso_correccion=peso,
            factor_minimo=inferior,
            factor_maximo=superior,
        )
        for features in FEATURE_SETS
        for alpha in (1.0, 10.0, 50.0)
        for peso in (0.25, 0.50, 0.75)
        for inferior, superior in clips
    ]
    salida.extend(
        Configuracion(
            estimador="huber",
            feature_set=features,
            alpha=alpha,
            epsilon_huber=epsilon,
            peso_correccion=peso,
            factor_minimo=inferior,
            factor_maximo=superior,
        )
        for features in FEATURE_SETS
        for alpha in (0.001, 0.01)
        for epsilon in (1.35, 1.75)
        for peso in (0.25, 0.50, 0.75)
        for inferior, superior in clips
    )
    salida.extend(
        Configuracion(
            estimador="bayes_shrinkage",
            lookback=lookback,
            shrink_fundo=shrink,
            decaimiento=decaimiento,
            peso_correccion=peso,
            factor_minimo=inferior,
            factor_maximo=superior,
        )
        for lookback in (8, 0)
        for shrink in (4.0, 12.0)
        for decaimiento in (0.90,)
        for peso in (0.25, 0.50, 0.75)
        for inferior, superior in clips
    )
    return salida


def _columnas_modelo(feature_set: str) -> list[str]:
    return [*FEATURE_SETS[feature_set], *[f"fundo_{f}" for f in FUNDOS[1:]]]


def _matriz(tabla: pd.DataFrame, feature_set: str) -> pd.DataFrame:
    x = tabla[list(FEATURE_SETS[feature_set])].copy()
    categorias = pd.Categorical(tabla.fundo_operativo, categories=FUNDOS)
    dummies = pd.get_dummies(categorias, prefix="fundo", dtype=float)
    dummies.index = tabla.index
    x = pd.concat([x, dummies.drop(columns=["fundo_Arena"], errors="ignore")], axis=1)
    return x.reindex(columns=_columnas_modelo(feature_set), fill_value=0.0)


def mascara_entrenamiento(panel: pd.DataFrame, fila: pd.Series) -> pd.Series:
    cerrada = panel.semana_fin.lt(pd.Timestamp(fila.fecha_emision))
    if str(fila.campania) == "C2025":
        return cerrada & panel.campania.eq("C2024")
    if str(fila.campania) == "C2026":
        return cerrada & panel.campania.isin(["C2024", "C2025", "C2026"])
    return pd.Series(False, index=panel.index)


def _predecir_bayes(
    entrenamiento: pd.DataFrame, objetivo: pd.DataFrame, config: Configuracion
) -> np.ndarray:
    historia = entrenamiento.sort_values("semana_fin", kind="stable").copy()
    if config.lookback > 0:
        fechas = sorted(historia.fecha_objetivo.unique())[-config.lookback :]
        historia = historia.loc[historia.fecha_objetivo.isin(fechas)]
    if historia.empty:
        return np.zeros(len(objetivo), dtype=float)
    orden = historia.semana_fin.rank(method="dense", ascending=False).to_numpy(float)
    pesos = np.power(config.decaimiento, np.maximum(orden - 1.0, 0.0))
    residuos = historia.residuo_objetivo.to_numpy(float)
    global_mean = float(np.average(residuos, weights=pesos))
    correcciones = []
    for fundo in objetivo.fundo_operativo.astype(str):
        mascara = historia.fundo_operativo.astype(str).eq(fundo).to_numpy()
        if not mascara.any():
            correcciones.append(global_mean)
            continue
        peso_local = pesos[mascara]
        local_mean = float(np.average(residuos[mascara], weights=peso_local))
        n_efectivo = float(peso_local.sum())
        posterior = (n_efectivo * local_mean + config.shrink_fundo * global_mean) / (
            n_efectivo + config.shrink_fundo
        )
        correcciones.append(float(posterior))
    return np.asarray(correcciones, dtype=float)


def predecir_rolling(panel: pd.DataFrame, config: Configuracion) -> pd.DataFrame:
    """Predice C2025/C2026; el real objetivo nunca entra en su propio ajuste."""

    salida = panel.copy().sort_values(
        ["fecha_objetivo", "campania", "fundo_operativo"], kind="stable"
    )
    salida["candidate_kg"] = salida.macro_kg.astype(float)
    salida["correccion_log"] = 0.0
    salida["modelo_ajustado"] = False
    salida["n_entrenamiento"] = 0
    salida["max_cierre_entrenamiento"] = pd.NaT

    grupos = (
        salida.loc[salida.campania.isin(["C2025", "C2026"])]
        .groupby(["campania", "fecha_emision", "fecha_objetivo"], sort=True)
        .groups
    )
    for _, indices in grupos.items():
        objetivo = salida.loc[indices]
        mascara = mascara_entrenamiento(salida, objetivo.iloc[0])
        entrenamiento = salida.loc[mascara].copy()
        if len(entrenamiento) < 20 or entrenamiento.fecha_objetivo.nunique() < 5:
            continue
        if config.estimador == "bayes_shrinkage":
            correccion = _predecir_bayes(entrenamiento, objetivo, config)
        else:
            x_train = _matriz(entrenamiento, config.feature_set).replace(
                [np.inf, -np.inf], np.nan
            )
            x_test = _matriz(objetivo, config.feature_set).replace([np.inf, -np.inf], np.nan)
            medianas = x_train.median(numeric_only=True).fillna(0.0)
            x_train = x_train.fillna(medianas).fillna(0.0)
            x_test = x_test.fillna(medianas).fillna(0.0)
            scaler = StandardScaler()
            xt = scaler.fit_transform(x_train)
            xv = scaler.transform(x_test)
            y = entrenamiento.residuo_objetivo.to_numpy(float)
            try:
                if config.estimador == "ridge":
                    modelo: Any = Ridge(alpha=config.alpha).fit(xt, y)
                else:
                    modelo = HuberRegressor(
                        alpha=config.alpha,
                        epsilon=config.epsilon_huber,
                        max_iter=1000,
                    ).fit(xt, y)
                correccion = np.asarray(modelo.predict(xv), dtype=float)
            except (ValueError, FloatingPointError):
                continue
        correccion = np.clip(
            correccion * config.peso_correccion,
            math.log(config.factor_minimo),
            math.log(config.factor_maximo),
        )
        prediccion = np.expm1(np.log1p(objetivo.macro_kg.to_numpy(float)) + correccion)
        salida.loc[indices, "candidate_kg"] = np.maximum(prediccion, 0.0)
        salida.loc[indices, "correccion_log"] = correccion
        salida.loc[indices, "modelo_ajustado"] = True
        salida.loc[indices, "n_entrenamiento"] = int(len(entrenamiento))
        salida.loc[indices, "max_cierre_entrenamiento"] = entrenamiento.semana_fin.max()
    return salida


__all__ = [
    "FEATURE_SETS",
    "Configuracion",
    "configuraciones",
    "mascara_entrenamiento",
    "predecir_rolling",
]
