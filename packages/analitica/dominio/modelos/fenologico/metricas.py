"""Métricas y calibración interna del modelo fenológico."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.dominio.modelos.fenologico.ajuste import _ModeloAjustado, predecir


def sensibilidades(
    prueba: pd.DataFrame,
    ocurrencia: _ModeloAjustado,
    frutos: _ModeloAjustado,
    peso: _ModeloAjustado,
    base_prob: np.ndarray,
    base_frutos: np.ndarray,
    base_peso: np.ndarray,
) -> list[dict]:
    cambios = {
        "cuajado_pct": ("tasa_cuajo_observada", "pct", 10.0),
        "riego_pct": ("riego_lamina_mm_7d", "pct", 10.0),
        "temp_delta_c": ("temp_media_7d", "suma", 1.0),
        "dpv_delta_kpa": ("dpv_kpa_7d", "suma", 0.1),
        "poda_delta_dias": ("dias_desde_poda", "suma", -7.0),
    }
    por_fila = [dict() for _ in range(len(prueba))]
    for control, (feature, modo, delta) in cambios.items():
        if (
            not any(feature in ajuste.features for ajuste in (ocurrencia, frutos, peso))
            or feature not in prueba
        ):
            continue
        alterada = prueba.copy()
        actual = pd.to_numeric(alterada[feature], errors="coerce")
        alterada[feature] = actual * (1 + delta / 100) if modo == "pct" else actual + delta
        p = predecir(ocurrencia, alterada, probabilidad=True)
        f = predecir(frutos, alterada)
        w = predecir(peso, alterada)
        for i in range(len(prueba)):
            por_fila[i][control] = {
                "unidad_cambio": delta,
                "probabilidad_pct": float(100 * (p[i] / max(base_prob[i], 1e-6) - 1)),
                "frutos_pct": float(100 * (f[i] / max(base_frutos[i], 1e-6) - 1)),
                "peso_pct": float(100 * (w[i] / max(base_peso[i], 1e-6) - 1)),
                "etiqueta": "sensibilidad_predictiva_no_causal",
            }
    return por_fila


def intervalos_validacion(
    entrenamiento: pd.DataFrame,
    ocurrencia: _ModeloAjustado,
    frutos: _ModeloAjustado,
    peso: _ModeloAjustado,
    factor_validacion: pd.Series | None = None,
) -> tuple[float, float, int]:
    comunes = ocurrencia.valid_index.intersection(frutos.valid_index).intersection(peso.valid_index)
    if len(comunes) < 20:
        return np.nan, np.nan, len(comunes)
    p = pd.Series(ocurrencia.valid_pred, index=ocurrencia.valid_index).loc[comunes]
    f = pd.Series(frutos.valid_pred, index=frutos.valid_index).loc[comunes]
    w = pd.Series(peso.valid_pred, index=peso.valid_index).loc[comunes]
    pesos_observados = pd.to_numeric(entrenamiento.loc[comunes, "peso_real_g"], errors="coerce")
    pesos_observados = pesos_observados[pesos_observados.gt(0)].dropna()
    limite_peso = (
        float(max(0.1, pesos_observados.quantile(0.05))) if not pesos_observados.empty else 0.1
    )
    w = np.maximum(w, limite_peso)
    plantas = pd.to_numeric(entrenamiento.loc[comunes, "plantas"], errors="coerce")
    pred = p * plantas * f * w / 1000
    if factor_validacion is not None:
        pred = pred * pd.to_numeric(factor_validacion.reindex(comunes), errors="coerce").fillna(1.0)
    real = pd.to_numeric(entrenamiento.loc[comunes, "real_kg"], errors="coerce")
    residual = (real - pred).replace([np.inf, -np.inf], np.nan).dropna()
    if len(residual) < 20:
        return np.nan, np.nan, len(residual)
    ancho = float(np.quantile(residual.abs(), 0.9))
    return -ancho, ancho, len(residual)


def intervalos_volumen_directo(
    entrenamiento: pd.DataFrame, volumen: _ModeloAjustado
) -> tuple[float, float, int]:
    """Intervalo residual del volumen directo en su bloque temporal de validación."""
    indices = volumen.valid_index
    if len(indices) < 20:
        return np.nan, np.nan, len(indices)
    real = pd.to_numeric(entrenamiento.loc[indices, "real_kg"], errors="coerce")
    pred = pd.Series(volumen.valid_pred, index=indices)
    residual = (real - pred).replace([np.inf, -np.inf], np.nan).dropna()
    if len(residual) < 20:
        return np.nan, np.nan, len(residual)
    ancho = float(np.quantile(residual.abs(), 0.9))
    return -ancho, ancho, len(residual)


def calibrar_factor_volumen(
    entrenamiento: pd.DataFrame,
    prueba: pd.DataFrame,
    ocurrencia: _ModeloAjustado,
    frutos: _ModeloAjustado,
    peso: _ModeloAjustado,
) -> tuple[pd.Series, pd.Series, dict]:
    """Calibra la escala del volumen usando únicamente replay temporal anterior.

    La probabilidad de ocurrencia y los dos componentes biológicos describen una
    expectativa condicional, pero en la práctica pueden quedar sistemáticamente
    desescalados. Este factor corrige ese sesgo con la razón robusta entre kg reales y
    kg esperados en los bloques de validación temporal de los tres componentes.

    No es una causa, una probabilidad adicional ni una constante del cultivo. Es una
    calibración de volumen aprendida as-of; se publica por separado para que el usuario
    pueda auditar cuánto del p50 proviene de ella.
    """
    comunes = ocurrencia.valid_index.intersection(frutos.valid_index).intersection(peso.valid_index)
    factores_validacion = pd.Series(1.0, index=comunes, dtype=float)
    factores_prueba = pd.Series(1.0, index=prueba.index, dtype=float)
    if len(comunes) < 20:
        return (
            factores_validacion,
            factores_prueba,
            {
                "metodo": "sin_calibracion_historia_insuficiente",
                "factor_global": 1.0,
                "n_calibracion_volumen": int(len(comunes)),
            },
        )

    p = pd.Series(ocurrencia.valid_pred, index=ocurrencia.valid_index).loc[comunes]
    f = pd.Series(frutos.valid_pred, index=frutos.valid_index).loc[comunes]
    w = pd.Series(peso.valid_pred, index=peso.valid_index).loc[comunes]
    pesos_observados = pd.to_numeric(entrenamiento.loc[comunes, "peso_real_g"], errors="coerce")
    pesos_observados = pesos_observados[pesos_observados.gt(0)].dropna()
    limite_peso = (
        float(max(0.1, pesos_observados.quantile(0.05))) if not pesos_observados.empty else 0.1
    )
    w = np.maximum(w, limite_peso)
    plantas = pd.to_numeric(entrenamiento.loc[comunes, "plantas"], errors="coerce")
    real = pd.to_numeric(entrenamiento.loc[comunes, "real_kg"], errors="coerce")
    base = p * plantas * f * w / 1000
    valido = (
        base.gt(0.01)
        & real.ge(0)
        & base.notna()
        & real.notna()
        & np.isfinite(base)
        & np.isfinite(real)
    )
    if valido.sum() < 20:
        return (
            factores_validacion,
            factores_prueba,
            {
                "metodo": "sin_calibracion_volumen_valido_insuficiente",
                "factor_global": 1.0,
                "n_calibracion_volumen": int(valido.sum()),
            },
        )

    razones = (real[valido] / base[valido]).replace([np.inf, -np.inf], np.nan).dropna()
    razones = razones[razones.gt(0)]
    if len(razones) < 20:
        return (
            factores_validacion,
            factores_prueba,
            {
                "metodo": "sin_calibracion_razones_insuficientes",
                "factor_global": 1.0,
                "n_calibracion_volumen": int(len(razones)),
            },
        )

    # La mediana logarítmica evita que un lote excepcional domine la escala. Los
    # cuantiles solo acotan el resultado a la distribución observada; no fijan una
    # magnitud agronómica universal.
    log_razones = np.log(razones)
    factor_global = float(np.exp(np.median(log_razones)))
    q01, q99 = np.quantile(razones, [0.01, 0.99])
    factores_validacion.loc[razones.index] = factor_global
    factores_horizonte: dict[int, float] = {}
    tabla_h = entrenamiento.loc[razones.index, ["horizonte_semanas"]].copy()
    tabla_h["razon"] = razones
    for horizonte, grupo in tabla_h.groupby("horizonte_semanas", dropna=True):
        valores = pd.to_numeric(grupo.razon, errors="coerce").dropna()
        if len(valores) < 10:
            continue
        factores_horizonte[int(horizonte)] = float(np.exp(np.median(np.log(valores))))
        factores_validacion.loc[valores.index] = factores_horizonte[int(horizonte)]

    factores_validacion = factores_validacion.clip(lower=float(q01), upper=float(q99))
    factores_prueba.loc[:] = factor_global
    if "horizonte_semanas" in prueba:
        for horizonte, factor in factores_horizonte.items():
            mascara = pd.to_numeric(prueba.horizonte_semanas, errors="coerce").eq(horizonte)
            factores_prueba.loc[prueba.index[mascara]] = factor
    factores_prueba = factores_prueba.clip(lower=float(q01), upper=float(q99))
    return (
        factores_validacion,
        factores_prueba,
        {
            "metodo": "mediana_logaritmica_razon_real_sobre_predicho_bloque_temporal",
            "factor_global": factor_global,
            "factores_por_horizonte": factores_horizonte,
            "rango_observado_factor": [float(q01), float(q99)],
            "n_calibracion_volumen": int(len(razones)),
        },
    )


__all__ = [
    "calibrar_factor_volumen",
    "intervalos_validacion",
    "intervalos_volumen_directo",
    "sensibilidades",
]
