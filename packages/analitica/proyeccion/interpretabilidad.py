"""Explicaciones globales e individuales robustas a variables correlacionadas."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error

FAMILIAS_AGRONOMICAS = {
    "temperatura_dpv_gdd": ["temp_media", "temp_max", "temp_min", "dpv_kpa", "gdd_4_4"],
    "radiacion_eto": ["radiacion", "eto"],
    "riego": ["agua_m3", "lamina_mm", "reposicion_pct"],
    "fenologia": [
        "flores_por_planta_muestra",
        "tasa_cuajo_observada",
        "indice_estado",
        "prop_e5",
        "diametro_baya_mm",
    ],
    "estructura": ["area_ha", "plantas_catalogo"],
}


def importancia_permutacion_grupos(
    modelo,
    x: pd.DataFrame,
    y: pd.Series,
    grupos: dict[str, list[str]] | None = None,
    repeticiones: int = 30,
    semilla: int = 42,
) -> pd.DataFrame:
    """Permuta juntas las señales colineales y mide pérdida de MAE."""
    grupos = grupos or FAMILIAS_AGRONOMICAS
    base = mean_absolute_error(y, modelo.predict(x))
    rng = np.random.default_rng(semilla)
    filas = []
    for nombre, candidatas in grupos.items():
        columnas = [c for c in candidatas if c in x]
        if not columnas:
            continue
        perdidas = []
        for _ in range(repeticiones):
            xp = x.copy()
            orden = rng.permutation(len(xp))
            xp.loc[:, columnas] = xp[columnas].to_numpy()[orden]
            perdidas.append(mean_absolute_error(y, modelo.predict(xp)) - base)
        filas.append(
            {
                "familia": nombre,
                "columnas": ", ".join(columnas),
                "aumento_mae": float(np.mean(perdidas)),
                "ic_inferior": float(np.quantile(perdidas, 0.025)),
                "ic_superior": float(np.quantile(perdidas, 0.975)),
            }
        )
    return pd.DataFrame(filas).sort_values("aumento_mae", ascending=False)


def importancia_permutacion_individual(modelo, x: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    resultado = permutation_importance(
        modelo, x, y, scoring="neg_mean_absolute_error", n_repeats=20, random_state=42, n_jobs=-1
    )
    return pd.DataFrame(
        {
            "variable": x.columns,
            "importancia_media": resultado.importances_mean,
            "importancia_sd": resultado.importances_std,
        }
    ).sort_values("importancia_media", ascending=False)


def ale_unidimensional(modelo, x: pd.DataFrame, variable: str, bins: int = 10) -> pd.DataFrame:
    """ALE empírico: solo evalúa cambios dentro del soporte observado de cada bin."""
    valores = x[variable].dropna()
    bordes = np.unique(np.quantile(valores, np.linspace(0, 1, bins + 1)))
    if len(bordes) < 3:
        return pd.DataFrame(columns=["variable", "x", "ale", "n"])
    codigo = np.clip(np.searchsorted(bordes, x[variable], side="right") - 1, 0, len(bordes) - 2)
    efectos, conteos = [], []
    for i in range(len(bordes) - 1):
        mascara = codigo == i
        xi = x.loc[mascara].copy()
        if xi.empty:
            efectos.append(0.0)
            conteos.append(0)
            continue
        bajo, alto = xi.copy(), xi.copy()
        bajo[variable], alto[variable] = bordes[i], bordes[i + 1]
        efectos.append(float(np.mean(modelo.predict(alto) - modelo.predict(bajo))))
        conteos.append(len(xi))
    acumulado = np.cumsum(efectos)
    centro = np.average(acumulado, weights=np.maximum(conteos, 1))
    return pd.DataFrame(
        {
            "variable": variable,
            "x": bordes[1:],
            "ale": acumulado - centro,
            "n": conteos,
        }
    )


def ablacion_familias(
    fabrica_modelo: Callable[[], object],
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_valid: pd.DataFrame,
    y_valid: pd.Series,
    grupos: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    grupos = grupos or FAMILIAS_AGRONOMICAS
    completo = fabrica_modelo().fit(x_train, y_train)
    mae_base = mean_absolute_error(y_valid, completo.predict(x_valid))
    filas = [{"ablacion": "ninguna", "mae": mae_base, "delta_mae": 0.0}]
    for nombre, candidatas in grupos.items():
        columnas = [c for c in x_train if c not in candidatas]
        if not columnas:
            continue
        modelo = fabrica_modelo().fit(x_train[columnas], y_train)
        valor = mean_absolute_error(y_valid, modelo.predict(x_valid[columnas]))
        filas.append({"ablacion": nombre, "mae": valor, "delta_mae": valor - mae_base})
    return pd.DataFrame(filas).sort_values("delta_mae", ascending=False)


def explicar_shap(modelo, x: pd.DataFrame, filas: int = 500) -> tuple[pd.DataFrame, object]:
    """SHAP identifica contribuciones a la predicción; la salida se etiqueta no causal."""
    import shap

    muestra = x.sample(min(filas, len(x)), random_state=42) if len(x) else x
    if modelo.__class__.__module__.startswith("xgboost"):
        # XGBoost 3 puede marcar internamente features aunque los valores sean numéricos;
        # TreeExplainer con rutas del árbol evita el masker interventional no compatible.
        explicador = shap.TreeExplainer(modelo, feature_perturbation="tree_path_dependent")
    else:
        explicador = shap.Explainer(modelo, muestra)
    valores = explicador(muestra)
    resumen = pd.DataFrame(
        {
            "variable": muestra.columns,
            "shap_abs_medio": np.abs(valores.values).mean(axis=0),
            "etiqueta": "contribucion_predictiva_no_causal",
        }
    ).sort_values("shap_abs_medio", ascending=False)
    return resumen, valores


def paquete_interpretabilidad_xgboost(r09: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Explicaciones sobre un bloque temporal final nunca usado para ajustar el modelo.

    El objetivo es el residual de R09. Esto conserva el rol de XGBoost como challenger
    explicable y evita presentar la explicación de un ajuste in-sample como desempeño.
    """
    from .modelos import FEATURES_CORRECCION, _fabricas_modelos, _preparar_features

    base = _preparar_features(r09[r09.modelo == "R09_publicado"].copy())
    base = base[(base.real_kg.notna()) & (base.fecha_objetivo < base.fecha_emision.max())]
    fechas = np.array(sorted(base.fecha_objetivo.unique()))
    if len(fechas) < 5:
        return {}
    corte = fechas[max(1, int(len(fechas) * 0.8))]
    train = base[base.fecha_objetivo < corte].copy()
    valid = base[base.fecha_objetivo >= corte].copy()
    if len(train) < 100 or len(valid) < 30:
        return {}
    medianas = train[FEATURES_CORRECCION].median().fillna(0)
    x_train = train[FEATURES_CORRECCION].fillna(medianas)
    x_valid = valid[FEATURES_CORRECCION].fillna(medianas)
    y_train = train.real_kg - train.p50_kg
    y_valid = valid.real_kg - valid.p50_kg
    fabrica = _fabricas_modelos()["XGBoost"][0]
    modelo = fabrica().fit(x_train, y_train)

    grupos = {
        "volumen_r09": ["p50_kg"],
        "horizonte": ["horizonte_semanas"],
        "estructura_productiva": ["plantas", "frutos_por_planta", "peso_baya_g"],
        "calendario": ["semana_objetivo_sin", "semana_objetivo_cos"],
    }
    agrupada = importancia_permutacion_grupos(modelo, x_valid, y_valid, grupos=grupos)
    individual = importancia_permutacion_individual(modelo, x_valid, y_valid)
    ablaciones = ablacion_familias(fabrica, x_train, y_train, x_valid, y_valid, grupos=grupos)
    ales = pd.concat(
        [ale_unidimensional(modelo, x_valid, variable) for variable in x_valid],
        ignore_index=True,
    )
    shap_resumen, _ = explicar_shap(modelo, x_valid)
    for tabla in (agrupada, individual, ablaciones, ales, shap_resumen):
        tabla["bloque_validacion_desde"] = pd.Timestamp(corte)
        tabla["etiqueta_causal"] = False
    return {
        "permutacion_agrupada": agrupada,
        "permutacion_individual": individual,
        "ablaciones": ablaciones,
        "ale": ales,
        "shap": shap_resumen,
    }
