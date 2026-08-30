"""Evidencia asociativa calculada dentro de cada fold temporal."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.dominio.modelos.fenologico.especificacion import (
    FEATURES_CONTROL,
    HIPOTESIS_FEATURE,
    NOMBRE_MODELO,
    REFERENCIAS_HIPOTESIS,
)


def hipotesis(feature: str) -> tuple[str, str]:
    if feature in HIPOTESIS_FEATURE:
        return HIPOTESIS_FEATURE[feature]
    if feature.startswith(("temp_", "humedad_", "dpv_", "eto_", "radiacion_", "lluvia_", "gdd_")):
        return "H6", "Clima se asocia con transición fenológica y peso."
    if feature.startswith("riego_"):
        return "H6_R", "Riego aplicado se asocia con transición y peso."
    if feature in FEATURES_CONTROL:
        return "CONTROL", "Variable de control temporal u operativo."
    return "DESCUBRIMIENTO", "Candidata del barrido multivariado; requiere validación temporal."


def correlacion(x: pd.Series, y: pd.Series) -> tuple[float, float, int]:
    from scipy import stats

    pares = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(pares) < 8 or pares.x.nunique() < 2 or pares.y.nunique() < 2:
        return np.nan, np.nan, len(pares)
    rho, p = stats.spearmanr(pares.x, pares.y)
    return float(rho), float(p), len(pares)


def evaluar_evidencia_fold(
    entrenamiento: pd.DataFrame,
    *,
    objetivo: str,
    features: list[str],
    modelo: str = NOMBRE_MODELO,
) -> pd.DataFrame:
    """Criba de relaciones calculada únicamente dentro del fold de entrenamiento."""

    filas = []
    orden = entrenamiento.sort_values(["lote_id", "fecha_emision", "fecha_objetivo"])
    for feature in features:
        if feature not in orden or objetivo not in orden:
            continue
        cobertura = float(orden[feature].notna().mean())
        rho, p, n = correlacion(orden[feature], orden[objetivo])
        futuro = orden.groupby("lote_id", dropna=False)[feature].shift(-1)
        placebo, _, _ = correlacion(futuro, orden[objetivo])
        signos = []
        if "modulo" in orden:
            for _, grupo in orden.groupby("modulo", dropna=False):
                r, _, ng = correlacion(grupo[feature], grupo[objetivo])
                if ng >= 8 and np.isfinite(r) and r != 0:
                    signos.append(np.sign(r))
        estabilidad = (
            float(max(signos.count(1.0), signos.count(-1.0)) / len(signos)) if signos else np.nan
        )
        codigo, hipotesis_texto = hipotesis(feature)
        filas.append(
            {
                "modelo": modelo,
                "predictor": feature,
                "objetivo": objetivo,
                "rezago": 0,
                "transformacion": "último valor o acumulado cerrado al corte",
                "hipotesis_id": codigo,
                "hipotesis": hipotesis_texto,
                "referencias": REFERENCIAS_HIPOTESIS.get(codigo, []),
                "metodo": "Spearman + estabilidad por módulo + placebo futuro",
                "cobertura": cobertura,
                "n_efectivo": int(orden.loc[orden[feature].notna(), "fecha_emision"].nunique()),
                "n": n,
                "estimacion": rho,
                "p_value": p,
                "placebo": placebo,
                "estabilidad_modulo": estabilidad,
                "papel": "control" if feature in FEATURES_CONTROL else "predictor_fundamentado",
                "etiqueta_causal": False,
            }
        )
    evidencia = pd.DataFrame(filas)
    if evidencia.empty:
        return evidencia
    validos = evidencia.p_value.notna()
    evidencia["q_value"] = np.nan
    if validos.any():
        from statsmodels.stats.multitest import multipletests

        evidencia.loc[validos, "q_value"] = multipletests(
            evidencia.loc[validos, "p_value"], method="fdr_bh"
        )[1]
    controles = evidencia.papel.eq("control")
    prior = evidencia.hipotesis_id.isin({"H1", "H2", "H3", "H4", "H6", "H6_R"})
    evidencia["admitida"] = controles | (
        evidencia.cobertura.ge(0.30)
        & evidencia.n_efectivo.ge(8)
        & (evidencia.q_value.le(0.20) | prior)
        & (
            evidencia.placebo.isna()
            | evidencia.estimacion.abs().add(0.05).ge(evidencia.placebo.abs())
        )
    )
    evidencia["estado"] = np.where(evidencia.admitida, "candidata_fold", "descartada_fold")
    evidencia["limitacion"] = (
        "Selección predictiva dentro del fold; asociación observacional, no efecto causal."
    )
    return evidencia


__all__ = ["correlacion", "evaluar_evidencia_fold", "hipotesis"]
