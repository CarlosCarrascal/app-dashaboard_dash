"""Familias de ajuste y predicción del modelo fenológico."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from analitica.dominio.modelos.fenologico.especificacion import FEATURES_PROHIBIDAS


@dataclass
class _ModeloAjustado:
    modelo: object
    nombre: str
    features: list[str]
    categorias: list[str]
    valid_index: pd.Index
    valid_pred: np.ndarray
    score: float


@dataclass
class _MixedLMFinal:
    resultado: object
    features: list[str]
    medianas: pd.Series
    medias: pd.Series
    escalas: pd.Series

    def _exog(self, tabla: pd.DataFrame) -> pd.DataFrame:
        numerica = tabla[self.features].apply(pd.to_numeric, errors="coerce")
        numerica = numerica.fillna(self.medianas)
        numerica = (numerica - self.medias) / self.escalas
        return pd.concat(
            [pd.Series(1.0, index=tabla.index, name="const"), numerica], axis=1
        ).astype(float)

    def predict(self, tabla: pd.DataFrame) -> np.ndarray:
        exog = self._exog(tabla)
        pred = np.asarray(self.resultado.predict(exog), dtype=float)
        grupos = tabla["modulo"].fillna("SIN_MODULO").astype(str)
        try:
            efectos = self.resultado.random_effects
        except (np.linalg.LinAlgError, ValueError):
            # MixedLM puede ajustar correctamente la parte fija y, aun así, no poder
            # invertir la covarianza de los efectos aleatorios. En ese caso la predicción
            # global sigue siendo válida, pero no se debe inventar un intercepto por módulo.
            efectos = {}
        for posicion, grupo in enumerate(grupos):
            if grupo in efectos:
                pred[posicion] += float(np.asarray(efectos[grupo]).ravel()[0])
        return pred


def columnas_modelo(tabla: pd.DataFrame, features: list[str]) -> tuple[list[str], list[str]]:
    numericas = [
        c
        for c in features
        if c in tabla and c not in FEATURES_PROHIBIDAS and pd.api.types.is_numeric_dtype(tabla[c])
    ]
    categorias = [c for c in ("campania", "fundo", "modulo", "variedad") if c in tabla]
    return numericas, categorias


def preprocesador(numericas: list[str], categorias: list[str], *, spline: bool = False):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler

    pasos_num: list[tuple[str, object]] = [("imputa", SimpleImputer(strategy="median"))]
    if spline:
        pasos_num.extend(
            [
                ("spline", SplineTransformer(n_knots=4, degree=2, include_bias=False)),
                ("escala", StandardScaler()),
            ]
        )
    else:
        pasos_num.append(("escala", StandardScaler()))
    transformadores = [("num", Pipeline(pasos_num), numericas)]
    if categorias:
        transformadores.append(
            (
                "cat",
                Pipeline(
                    [
                        ("imputa", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorias,
            )
        )
    return ColumnTransformer(transformadores, remainder="drop")


def regresores(objetivo: str) -> list[tuple[str, Callable[[], object]]]:
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge, TweedieRegressor

    candidatos: list[tuple[str, Callable[[], object]]] = [
        (
            "Tweedie",
            lambda: TweedieRegressor(
                power=1.5 if objetivo == "frutos_reales_por_planta_catalogo" else 0,
                alpha=1.0,
                link="log" if objetivo == "frutos_reales_por_planta_catalogo" else "identity",
                max_iter=1000,
            ),
        ),
        ("SplineRidge", lambda: Ridge(alpha=10.0)),
        (
            "RandomForest",
            lambda: RandomForestRegressor(
                n_estimators=140,
                max_depth=9,
                min_samples_leaf=8,
                random_state=42,
                n_jobs=1,
            ),
        ),
        (
            "HistGradientBoosting",
            lambda: HistGradientBoostingRegressor(
                max_iter=160, max_depth=6, min_samples_leaf=12, l2_regularization=1.0
            ),
        ),
    ]
    try:
        from xgboost import XGBRegressor

        if objetivo != "real_kg":
            candidatos.append(
                (
                    "XGBoost",
                    lambda: XGBRegressor(
                        n_estimators=160,
                        max_depth=4,
                        learning_rate=0.04,
                        subsample=0.8,
                        colsample_bytree=0.8,
                        objective="reg:squarederror",
                        random_state=42,
                        n_jobs=1,
                    ),
                )
            )
    except ImportError:
        pass
    return candidatos


def clasificadores() -> list[tuple[str, Callable[[], object]]]:
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    candidatos: list[tuple[str, Callable[[], object]]] = [
        (
            "Logistica",
            lambda: LogisticRegression(max_iter=1000, class_weight="balanced", C=0.5),
        ),
        (
            "RandomForest",
            lambda: RandomForestClassifier(
                n_estimators=160,
                max_depth=8,
                min_samples_leaf=12,
                class_weight="balanced",
                random_state=42,
                n_jobs=1,
            ),
        ),
        (
            "HistGradientBoosting",
            lambda: HistGradientBoostingClassifier(
                max_iter=160, max_depth=6, min_samples_leaf=12, l2_regularization=1.0
            ),
        ),
    ]
    try:
        from xgboost import XGBClassifier

        candidatos.append(
            (
                "XGBoost",
                lambda: XGBClassifier(
                    n_estimators=160,
                    max_depth=4,
                    learning_rate=0.04,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    eval_metric="logloss",
                    random_state=42,
                    n_jobs=1,
                ),
            )
        )
    except ImportError:
        pass
    return candidatos


def corte_temporal(tabla: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    orden = tabla.sort_values(["fecha_objetivo", "lote_id"])
    fechas = sorted(orden.fecha_objetivo.dropna().unique())
    if len(fechas) < 5:
        corte = max(1, int(len(orden) * 0.8))
        return orden.iloc[:corte], orden.iloc[corte:]
    fecha_corte = pd.Timestamp(fechas[max(1, int(len(fechas) * 0.8)) - 1])
    return orden[orden.fecha_objetivo <= fecha_corte], orden[orden.fecha_objetivo > fecha_corte]


def pipeline(
    estimador: object,
    numericas: list[str],
    categorias: list[str],
    *,
    spline: bool = False,
):
    from sklearn.pipeline import Pipeline

    return Pipeline(
        [("prepara", preprocesador(numericas, categorias, spline=spline)), ("modelo", estimador)]
    )


def ajustar_mixedlm(
    tabla: pd.DataFrame,
    objetivo: str,
    features: list[str],
) -> tuple[_MixedLMFinal, list[str]]:
    import statsmodels.api as sm

    if "modulo" not in tabla or tabla.modulo.nunique() < 2:
        raise ValueError("MixedLM necesita al menos dos módulos")
    preferidas = [
        "horizonte_semanas",
        "dias_desde_poda",
        "indice_estado",
        "prop_e4",
        "prop_e5",
        "diametro_baya_mm",
        "peso_real_g_ultimo_asof",
        "temp_media_7d",
        "dpv_kpa_7d",
        "eto_7d",
        "riego_lamina_mm_7d",
    ]
    disponibles = [
        feature
        for feature in preferidas
        if feature in features
        and feature in tabla
        and pd.to_numeric(tabla[feature], errors="coerce").nunique() > 1
    ][:8]
    if not disponibles:
        raise ValueError("MixedLM no tiene covariables numéricas utilizables")
    numerica = tabla[disponibles].apply(pd.to_numeric, errors="coerce")
    medianas = numerica.median().fillna(0)
    numerica = numerica.fillna(medianas)
    medias = numerica.mean()
    escalas = numerica.std().replace(0, 1).fillna(1)
    exog = pd.concat(
        [
            pd.Series(1.0, index=tabla.index, name="const"),
            (numerica - medias) / escalas,
        ],
        axis=1,
    ).astype(float)
    grupos = tabla.modulo.fillna("SIN_MODULO").astype(str)
    resultado = sm.MixedLM(
        pd.to_numeric(tabla[objetivo], errors="coerce").astype(float),
        exog,
        groups=grupos,
    ).fit(reml=False, method="lbfgs", maxiter=300, disp=False)
    return _MixedLMFinal(resultado, disponibles, medianas, medias, escalas), disponibles


def ajustar_regresor(
    tabla: pd.DataFrame,
    objetivo: str,
    features: list[str],
    *,
    usar_mixedlm: bool = True,
) -> _ModeloAjustado:
    from sklearn.metrics import mean_absolute_error

    tabla = tabla.dropna(subset=[objetivo]).copy()
    numericas, categorias = columnas_modelo(tabla, features)
    if not numericas or len(tabla) < 60:
        raise ValueError(f"Historia insuficiente para {objetivo}")
    interno, validacion = corte_temporal(tabla)
    if len(interno) < 40 or len(validacion) < 10:
        raise ValueError(f"No existe bloque temporal suficiente para {objetivo}")
    # Una variable puede existir en el panel completo y, aun así, estar completamente
    # ausente en el bloque temprano de entrenamiento. No se la entrega al imputador: eso
    # evita warnings engañosos y deja la pérdida de cobertura en la evidencia del corte.
    numericas = [c for c in numericas if interno[c].notna().any()]
    categorias = [c for c in categorias if interno[c].notna().any()]
    if not numericas:
        raise ValueError(f"No hay variables numéricas observadas para {objetivo}")
    columnas = [*numericas, *categorias]
    mejor = None
    for nombre, fabrica in regresores(objetivo):
        try:
            modelo = pipeline(fabrica(), numericas, categorias, spline=nombre == "SplineRidge")
            modelo.fit(interno[columnas], interno[objetivo])
            pred = np.maximum(0, modelo.predict(validacion[columnas]))
            score = float(mean_absolute_error(validacion[objetivo], pred))
            if mejor is None or score < mejor[0]:
                mejor = (score, nombre, fabrica, pred)
        except (ValueError, TypeError, FloatingPointError):
            continue
    mixto_valid_pred = None
    mixto_features: list[str] = []
    if usar_mixedlm and objetivo == "peso_real_g":
        try:
            mixto_interno, mixto_features = ajustar_mixedlm(interno, objetivo, numericas)
            mixto_valid_pred = np.maximum(
                0,
                mixto_interno.predict(validacion[[*mixto_features, "modulo"]]),
            )
            score_mixto = float(mean_absolute_error(validacion[objetivo], mixto_valid_pred))
            if mejor is None or score_mixto < mejor[0]:
                mixto_final, mixto_features = ajustar_mixedlm(tabla, objetivo, numericas)
                return _ModeloAjustado(
                    mixto_final,
                    "MixedLM_intercepto_modulo",
                    mixto_features,
                    ["modulo"],
                    validacion.index,
                    mixto_valid_pred,
                    score_mixto,
                )
        except (ValueError, TypeError, np.linalg.LinAlgError):
            pass
    if mejor is None:
        raise ValueError(f"Ninguna familia pudo ajustar {objetivo}")
    score, nombre, fabrica, valid_pred = mejor
    final = pipeline(fabrica(), numericas, categorias, spline=nombre == "SplineRidge")
    final.fit(tabla[columnas], tabla[objetivo])
    return _ModeloAjustado(
        final, nombre, numericas, categorias, validacion.index, valid_pred, score
    )


def ajustar_clasificador(tabla: pd.DataFrame, features: list[str]) -> _ModeloAjustado:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import brier_score_loss

    tabla = tabla.dropna(subset=["ocurre_cosecha"]).copy()
    numericas, categorias = columnas_modelo(tabla, features)
    if not numericas or len(tabla) < 100 or tabla.ocurre_cosecha.nunique() < 2:
        raise ValueError("Historia insuficiente para ocurrencia")
    interno, validacion = corte_temporal(tabla)
    if interno.ocurre_cosecha.nunique() < 2 or validacion.empty:
        raise ValueError("El corte temporal de ocurrencia no contiene ambas clases")
    columnas = [*numericas, *categorias]
    mejor = None
    for nombre, fabrica in clasificadores():
        try:
            modelo = pipeline(fabrica(), numericas, categorias)
            modelo.fit(interno[columnas], interno.ocurre_cosecha.astype(int))
            pred = modelo.predict_proba(validacion[columnas])[:, 1]
            score = float(brier_score_loss(validacion.ocurre_cosecha, pred))
            if mejor is None or score < mejor[0]:
                mejor = (score, nombre, fabrica, pred)
        except (ValueError, TypeError, FloatingPointError):
            continue
    if mejor is None:
        raise ValueError("Ninguna familia pudo ajustar ocurrencia")
    score, nombre, fabrica, valid_pred = mejor
    ordenada = tabla.sort_values(["fecha_objetivo", "lote_id"]).reset_index(drop=True)
    y_ordenada = ordenada.ocurre_cosecha.astype(int)
    splits = []
    for fraccion in (0.60, 0.72, 0.84):
        inicio_validacion = int(len(ordenada) * fraccion)
        fin_validacion = min(len(ordenada), inicio_validacion + max(20, len(ordenada) // 8))
        train_idx = np.arange(inicio_validacion)
        valid_idx = np.arange(inicio_validacion, fin_validacion)
        if (
            len(valid_idx) >= 10
            and y_ordenada.iloc[train_idx].nunique() == 2
            and y_ordenada.iloc[valid_idx].nunique() == 2
        ):
            splits.append((train_idx, valid_idx))
    if not splits:
        raise ValueError("No hay bloques temporales con ambas clases para calibrar ocurrencia")
    final = CalibratedClassifierCV(
        pipeline(fabrica(), numericas, categorias),
        method="sigmoid",
        cv=splits,
        ensemble=True,
    )
    final.fit(ordenada[columnas], y_ordenada)
    return _ModeloAjustado(
        final,
        f"{nombre}_calibrado_temporal",
        numericas,
        categorias,
        validacion.index,
        valid_pred,
        score,
    )


def predecir(
    ajuste: _ModeloAjustado, tabla: pd.DataFrame, *, probabilidad: bool = False
) -> np.ndarray:
    columnas = [*ajuste.features, *ajuste.categorias]
    if probabilidad:
        return np.clip(ajuste.modelo.predict_proba(tabla[columnas])[:, 1], 0, 1)
    return np.maximum(0, ajuste.modelo.predict(tabla[columnas]))


__all__ = [
    "_ModeloAjustado",
    "_MixedLMFinal",
    "ajustar_clasificador",
    "ajustar_mixedlm",
    "ajustar_regresor",
    "clasificadores",
    "columnas_modelo",
    "corte_temporal",
    "pipeline",
    "predecir",
    "preprocesador",
    "regresores",
]
