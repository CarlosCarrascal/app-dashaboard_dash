"""Corrección residual del modelo híbrido.

El residual aprende factores multiplicativos sobre la curva macro únicamente con
observaciones disponibles antes del corte. Este módulo no construye paneles ni
calibra priors; recibe un ``DataFrame`` de entrenamiento y devuelve el componente
estadístico que consume la fachada híbrida.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler

EPSILON = 0.1

FEATURES_RESIDUALES = [
    "legacy_frutos_por_planta",
    "legacy_peso_baya_g",
    "legacy_kg",
    "horizonte_semanas",
    "semana_objetivo_sin",
    "semana_objetivo_cos",
    "plantas",
    "dias_desde_poda",
    "kg_acumulado_asof",
    "kg_ultima_cosecha_asof",
    "kg_ultimas_4_semanas_asof",
    "semanas_cosecha_asof",
    "pasada_ultima_asof",
    "flores",
    "cuajo",
    "tasa_cuajo_observada",
    "indice_estado",
    "prop_e1",
    "prop_e2",
    "prop_e3",
    "prop_e4",
    "prop_e5",
    "diametro_baya_mm",
    "temp_media_7d",
    "temp_min_7d",
    "temp_max_7d",
    "dpv_kpa_7d",
    "eto_7d",
    "radiacion_7d",
    "gdd_0_0_7d",
    "gdd_4_4_7d",
    "gdd_7_0_7d",
    "gdd_8_0_7d",
    "temp_media_28d",
    "dpv_kpa_28d",
    "eto_28d",
    "radiacion_28d",
    "gdd_0_0_28d",
    "gdd_4_4_28d",
    "gdd_7_0_28d",
    "gdd_8_0_28d",
    "riego_lamina_mm_7d",
    "riego_reposicion_pct_7d",
    "riego_lamina_mm_28d",
    "riego_reposicion_pct_28d",
]

FEATURES_PROHIBIDAS = {
    "real_kg",
    "p50_kg",
    "p10_kg",
    "p90_kg",
    "peso_real_g",
    "frutos_reales_por_planta",
    "frutos_reales_por_planta_catalogo",
    "kg_r09",
    "frutos_por_planta_r09",
    "peso_baya_r09",
}


@dataclass
class _CorreccionResidual:
    modelo_frutos: Pipeline | None
    modelo_peso: Pipeline | None
    features_frutos: list[str]
    features_peso: list[str]
    q10_kg: float
    q90_kg: float
    n_entrenamiento: int


CorreccionResidual = _CorreccionResidual


def features_presentes(tabla: pd.DataFrame) -> tuple[list[str], list[str]]:
    numericas = []
    for columna in FEATURES_RESIDUALES:
        if (
            columna in tabla
            and pd.api.types.is_numeric_dtype(tabla[columna])
            and tabla[columna].notna().any()
        ):
            numericas.append(columna)
    categorias = [c for c in ("campania", "fundo", "modulo", "variedad") if c in tabla]
    return numericas, categorias


def pipeline_residual(tabla: pd.DataFrame, features: list[str]) -> Pipeline:
    intrusas = sorted(set(features) & FEATURES_PROHIBIDAS)
    if intrusas:
        raise ValueError(
            "La corrección residual no puede usar variables prohibidas: " + ", ".join(intrusas)
        )
    numericas = [c for c in features if c in tabla and pd.api.types.is_numeric_dtype(tabla[c])]
    categorias = [c for c in features if c in tabla and c not in numericas]
    transformadores = []
    if numericas:
        transformadores.append(
            (
                "numericas",
                Pipeline(
                    [
                        ("imputar", SimpleImputer(strategy="median", add_indicator=True)),
                        ("spline", SplineTransformer(n_knots=4, degree=2, include_bias=False)),
                        ("escalar", StandardScaler()),
                    ]
                ),
                numericas,
            )
        )
    if categorias:
        transformadores.append(
            (
                "categorias",
                Pipeline(
                    [
                        ("imputar", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorias,
            )
        )
    if not transformadores:
        raise ValueError("No hay features disponibles para la corrección residual")
    return Pipeline(
        [
            ("preparar", ColumnTransformer(transformadores, remainder="drop")),
            ("ridge", Ridge(alpha=10.0)),
        ]
    )


def ajustar_residuales(
    entrenamiento: pd.DataFrame, minimo_entrenamiento: int
) -> CorreccionResidual:
    eps = EPSILON
    base = entrenamiento.copy()
    base = base.replace([np.inf, -np.inf], np.nan)
    columnas_frutos = {"frutos_reales_por_planta_catalogo", "legacy_frutos_por_planta"}
    columnas_peso = {"peso_real_g", "legacy_peso_baya_g"}
    validos_frutos = (
        base[list(columnas_frutos)].notna().all(axis=1)
        if columnas_frutos <= set(base)
        else pd.Series(False, index=base.index)
    )
    validos_peso = (
        base[list(columnas_peso)].notna().all(axis=1)
        if columnas_peso <= set(base)
        else pd.Series(False, index=base.index)
    )
    validos_frutos &= base.frutos_reales_por_planta_catalogo.ge(
        0
    ) & base.legacy_frutos_por_planta.ge(0)
    validos_peso &= base.peso_real_g.gt(0) & base.legacy_peso_baya_g.gt(0)
    # Las columnas pueden existir en el panel pero estar completamente ausentes en
    # las filas que sí tienen objetivo de frutos o de peso. Seleccionarlas desde todo
    # el panel hacía que SimpleImputer descartara columnas y emitiera warnings durante
    # cada corte del replay. Cada componente recibe ahora solo variables observadas en
    # su propio conjunto de entrenamiento.
    features_frutos_num, features_frutos_cat = (
        features_presentes(base.loc[validos_frutos]) if validos_frutos.any() else ([], [])
    )
    features_peso_num, features_peso_cat = (
        features_presentes(base.loc[validos_peso]) if validos_peso.any() else ([], [])
    )
    features_frutos = [*features_frutos_num, *features_frutos_cat]
    features_peso = [*features_peso_num, *features_peso_cat]

    modelo_frutos = modelo_peso = None
    if validos_frutos.sum() >= minimo_entrenamiento and features_frutos:
        modelo_frutos = pipeline_residual(base.loc[validos_frutos], features_frutos)
        x = base.loc[validos_frutos, features_frutos]
        y = np.log(
            (base.loc[validos_frutos, "frutos_reales_por_planta_catalogo"] + eps)
            / (base.loc[validos_frutos, "legacy_frutos_por_planta"] + eps)
        )
        modelo_frutos.fit(x, y)
    if validos_peso.sum() >= minimo_entrenamiento and features_peso:
        modelo_peso = pipeline_residual(base.loc[validos_peso], features_peso)
        x = base.loc[validos_peso, features_peso]
        y = np.log(
            (base.loc[validos_peso, "peso_real_g"] + eps)
            / (base.loc[validos_peso, "legacy_peso_baya_g"] + eps)
        )
        modelo_peso.fit(x, y)

    kg_validos = (
        base[["real_kg", "legacy_kg"]].notna().all(axis=1)
        if {"real_kg", "legacy_kg"} <= set(base)
        else pd.Series(False, index=base.index)
    )
    kg_validos &= base.real_kg.ge(0) & base.legacy_kg.ge(0)
    if kg_validos.sum() >= 10:
        ratios = np.log(
            (base.loc[kg_validos, "real_kg"] + eps) / (base.loc[kg_validos, "legacy_kg"] + eps)
        )
        q10, q90 = np.nanquantile(ratios, [0.10, 0.90])
        q10, q90 = min(0.0, float(q10)), max(0.0, float(q90))
    else:
        q10, q90 = np.nan, np.nan
    return _CorreccionResidual(
        modelo_frutos=modelo_frutos,
        modelo_peso=modelo_peso,
        features_frutos=features_frutos,
        features_peso=features_peso,
        q10_kg=q10,
        q90_kg=q90,
        n_entrenamiento=int(max(validos_frutos.sum(), validos_peso.sum())),
    )


__all__ = [
    "CorreccionResidual",
    "EPSILON",
    "FEATURES_PROHIBIDAS",
    "FEATURES_RESIDUALES",
    "ajustar_residuales",
    "features_presentes",
    "pipeline_residual",
]
