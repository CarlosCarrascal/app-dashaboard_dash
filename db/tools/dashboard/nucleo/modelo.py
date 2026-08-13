"""Ajuste del XGBoost sobre el panel completo y su explicación con SHAP.

Este modelo es el que se EXPLICA (importancia global, waterfall por celda). El que se
VALIDA vive en `evaluacion.py` y se reentrena por partición: son usos distintos y no
deben compartir instancia — explicar sobre un modelo que vio todo es correcto; medir su
precisión sobre esos mismos datos, no.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import shap
import xgboost as xgb

from config import FEATURES, OBJETIVO, PARAMS


@dataclass
class Ajuste:
    """Modelo entrenado sobre todo el panel, con sus valores SHAP ya calculados."""

    modelo: xgb.XGBRegressor
    shap_values: np.ndarray
    base_value: float
    X: pd.DataFrame
    importancia: pd.Series

    def tiene(self, indice) -> bool:
        """Si esa fila del panel entró al ajuste (algunas se descartan, ver `entrenar`)."""
        return indice in self.X.index

    def contribuciones(self, indice) -> pd.Series:
        """Aporte de cada variable, en kg/ha, para una fila del panel ORIGINAL.

        `indice` es la etiqueta del índice de `panel.tabla`, no una posición. `X` puede
        tener menos filas que el panel (se descartan las sin ventana de rezago completa),
        así que la posición dentro de `X` no coincide en general con la del panel.
        """
        pos = self.X.index.get_loc(indice)
        return pd.Series(self.shap_values[pos], index=list(FEATURES))

    def prediccion(self, indice) -> float:
        """El valor base más todas las contribuciones — la predicción del modelo."""
        pos = self.X.index.get_loc(indice)
        return float(self.base_value + self.shap_values[pos].sum())


def entrenar(
    tabla: pd.DataFrame, params: dict | None = None, objetivo: str = OBJETIVO
) -> Ajuste:
    """Entrena sobre el panel entero y calcula SHAP.

    Descarta las filas sin ventana de rezago completa (`nucleo/datos.py` las deja en NaN
    a propósito): un promedio parcial no es lo que pide la ventana configurada, así que
    no debe entrar al ajuste. Cuántas filas se pierden queda registrado como Hallazgo en
    el panel, no aquí.

    `objetivo` permite entrenar el mismo modelo (mismas `FEATURES`, mismos hiperparámetros)
    contra Frutos o Peso en vez de KgHa — ver `nucleo/sintesis.py`. Los hiperparámetros de
    `PARAMS` se barrieron para KgHa; reusarlos en otro objetivo es una aproximación, no una
    calibración propia.
    """
    tabla = tabla.dropna(subset=[*FEATURES, objetivo])
    X = tabla[list(FEATURES)]
    y = tabla[objetivo]
    modelo = xgb.XGBRegressor(**(params or PARAMS)).fit(X, y)
    valores = shap.TreeExplainer(modelo)(X)
    return Ajuste(
        modelo=modelo,
        shap_values=valores.values,
        base_value=float(np.ravel(valores.base_values)[0]),
        X=X,
        importancia=pd.Series(
            np.abs(valores.values).mean(0), index=list(FEATURES)
        ).sort_values(ascending=False),
    )


@dataclass(frozen=True)
class Consistencia:
    """Resultado de comprobar, fila por fila, que el reparto SHAP reconstruye el modelo."""

    n_filas: int
    coinciden: int
    diferencia_maxima: float
    tolerancia: float

    @property
    def todas_coinciden(self) -> bool:
        return self.coinciden == self.n_filas


def verificar_consistencia(ajuste: Ajuste, tolerancia: float = 1e-2) -> Consistencia:
    """Comprueba que valor_base + suma(contribuciones SHAP) == predicción cruda del modelo.

    Esto NO es una prueba estadística ni una medida de qué tan bueno es el modelo — de eso
    se ocupa `evaluacion.py`. Es una comprobación de que el reparto no tiene un error de
    cálculo: los valores de Shapley cumplen esta igualdad por construcción (el axioma de
    eficiencia, Lundberg & Lee 2017), así que debería cumplirse siempre y para las 452
    filas, no solo para la que se esté mirando. Se verifica en vez de asumirse.
    """
    pred_shap = ajuste.base_value + ajuste.shap_values.sum(axis=1)
    pred_cruda = ajuste.modelo.predict(ajuste.X)
    diferencia = np.abs(pred_shap - pred_cruda)
    return Consistencia(
        n_filas=len(diferencia),
        coinciden=int((diferencia < tolerancia).sum()),
        diferencia_maxima=float(diferencia.max()),
        tolerancia=tolerancia,
    )
