"""Modelos inferenciales complementarios; resultados observacionales, no causales."""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd


def _json_seguro(valor: dict[str, object]) -> str:
    def limpiar(v):
        if isinstance(v, dict):
            return {k: limpiar(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [limpiar(x) for x in v]
        if isinstance(v, (float, np.floating)) and not np.isfinite(v):
            return None
        if isinstance(v, np.generic):
            return v.item()
        return v

    return json.dumps(limpiar(valor), ensure_ascii=False, sort_keys=True, default=str)


def modelo_mixto(
    panel: pd.DataFrame, respuesta: str, predictor: str, grupo: str = "modulo"
) -> dict[str, object]:
    """Pendiente estandarizada con intercepto aleatorio por módulo."""
    try:
        import statsmodels.formula.api as smf
        from statsmodels.tools.sm_exceptions import ConvergenceWarning
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("statsmodels es necesario para MixedLM.") from exc
    columnas = [respuesta, predictor, grupo, "fecha_semana"]
    t = panel[columnas].dropna().copy()
    if len(t) < 40 or t[grupo].nunique() < 3:
        return {"estado": "muestra_insuficiente", "n": len(t)}
    for variable in (respuesta, predictor):
        sd = t[variable].std()
        t[f"z_{variable}"] = (t[variable] - t[variable].mean()) / sd if sd > 0 else 0
    semana = t.fecha_semana.dt.isocalendar().week.astype(float)
    t["semana_sin"] = np.sin(2 * np.pi * semana / 52.18)
    t["semana_cos"] = np.cos(2 * np.pi * semana / 52.18)
    formula = f"z_{respuesta} ~ z_{predictor} + semana_sin + semana_cos"
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=ConvergenceWarning,
            module=r"statsmodels\..*",
        )
        ajuste = smf.mixedlm(formula, t, groups=t[grupo]).fit(
            reml=False, method="lbfgs", maxiter=200, disp=False
        )
    nombre = f"z_{predictor}"
    ic = ajuste.conf_int().loc[nombre]
    return {
        "estado": "ok" if ajuste.converged else "no_convergente",
        "n": len(t),
        "grupos": int(t[grupo].nunique()),
        "estimacion_estandarizada": float(ajuste.params[nombre]),
        "ic_inferior": float(ic.iloc[0]),
        "ic_superior": float(ic.iloc[1]),
        "p_valor": float(ajuste.pvalues[nombre]),
        "nota": "Asociación ajustada por calendario e intercepto de módulo; no causal.",
    }


def modelo_ardl(
    panel: pd.DataFrame, respuesta: str, predictor: str, rezagos: int = 4
) -> dict[str, object]:
    """Precedencia temporal agregada con errores HAC."""
    try:
        import statsmodels.api as sm
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("statsmodels es necesario para ARDL/HAC.") from exc
    t = (
        panel.groupby("fecha_semana", as_index=False)[[respuesta, predictor]]
        .mean()
        .sort_values("fecha_semana")
    )
    for lag in range(rezagos + 1):
        t[f"{predictor}_lag{lag}"] = t[predictor].shift(lag)
    t[f"{respuesta}_lag1"] = t[respuesta].shift(1)
    t = t.dropna()
    if len(t) < max(30, 5 * rezagos):
        return {"estado": "muestra_insuficiente", "n": len(t)}
    x_cols = [f"{respuesta}_lag1", *[f"{predictor}_lag{i}" for i in range(rezagos + 1)]]
    ajuste = sm.OLS(t[respuesta], sm.add_constant(t[x_cols])).fit(
        cov_type="HAC", cov_kwds={"maxlags": rezagos}
    )
    return {
        "estado": "ok",
        "n": len(t),
        "aic": float(ajuste.aic),
        "coeficientes": {c: float(ajuste.params[c]) for c in x_cols},
        "p_valores_hac": {c: float(ajuste.pvalues[c]) for c in x_cols},
        "nota": "ARDL/HAC evalúa precedencia y rezagos; no demuestra causalidad.",
    }


def distributed_lag_spline(
    panel: pd.DataFrame,
    respuesta: str,
    predictor: str,
    max_rezago: int = 6,
) -> dict[str, object]:
    """Spline regularizado sobre niveles rezagados, inspirado en DLNM.

    Es una aproximación predictiva deliberadamente identificada como tal; no replica el
    estimador epidemiológico DLNM ni reclama sus propiedades inferenciales.
    """
    from sklearn.linear_model import RidgeCV
    from sklearn.metrics import mean_absolute_error
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import SplineTransformer, StandardScaler

    t = (
        panel.groupby("fecha_semana", as_index=False)[[respuesta, predictor]]
        .mean()
        .sort_values("fecha_semana")
    )
    lags = []
    for lag in range(max_rezago + 1):
        nombre = f"lag_{lag}"
        t[nombre] = t[predictor].shift(lag)
        lags.append(nombre)
    t = t.dropna()
    if len(t) < 40:
        return {"estado": "muestra_insuficiente", "n": len(t)}
    corte = int(len(t) * 0.8)
    train, test = t.iloc[:corte], t.iloc[corte:]
    modelo = make_pipeline(
        SplineTransformer(n_knots=4, degree=2),
        StandardScaler(),
        RidgeCV(alphas=np.logspace(-3, 3, 13)),
    )
    modelo.fit(train[lags], train[respuesta])
    return {
        "estado": "ok",
        "n_train": len(train),
        "n_test": len(test),
        "mae_temporal": float(mean_absolute_error(test[respuesta], modelo.predict(test[lags]))),
        "max_rezago": max_rezago,
        "nota": "Base spline regularizada validada en bloque final; predictiva, no causal.",
    }


def evaluar_matriz_inferencial(panel: pd.DataFrame) -> pd.DataFrame:
    """Ejecuta MixedLM, ARDL/HAC y spline para cada ruta con variables observadas."""
    from .relaciones import HIPOTESIS

    filas = []
    for hipotesis in HIPOTESIS:
        if hipotesis.predictor not in panel or hipotesis.respuesta not in panel:
            continue
        predictor, respuesta = hipotesis.predictor, hipotesis.respuesta
        especificaciones = (
            (
                "MixedLM",
                lambda p=predictor, r=respuesta: modelo_mixto(panel, r, p),
                "correlacional",
            ),
            (
                "ARDL_HAC",
                lambda p=predictor, r=respuesta: modelo_ardl(panel, r, p),
                "temporal",
            ),
            (
                "distributed_lag_spline",
                lambda p=predictor, r=respuesta: distributed_lag_spline(panel, r, p),
                "predictiva",
            ),
        )
        for metodo, funcion, clase in especificaciones:
            try:
                resultado = funcion()
            except (ValueError, np.linalg.LinAlgError) as exc:
                resultado = {
                    "estado": "no_estimable",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            filas.append(
                {
                    "hipotesis_id": hipotesis.codigo,
                    "hipotesis": hipotesis.enunciado,
                    "predictor": hipotesis.predictor,
                    "respuesta": hipotesis.respuesta,
                    "metodo": metodo,
                    "clase_evidencia": clase,
                    "estado": resultado.get("estado", "no_estimable"),
                    "n": resultado.get("n", resultado.get("n_train")),
                    "estimacion": resultado.get("estimacion_estandarizada"),
                    "intervalo_inferior": resultado.get("ic_inferior"),
                    "intervalo_superior": resultado.get("ic_superior"),
                    "p_valor": resultado.get("p_valor"),
                    "detalle": _json_seguro(resultado),
                    "etiqueta_causal": False,
                }
            )
    return pd.DataFrame(filas)
