"""Síntesis de «cómo afectan las variables»: individual y conjunta, en un solo lugar.

Responde la pregunta que atraviesa todo el tablero — qué variable, con qué desfase,
explica mejor kg/ha, Frutos, Peso y Floración — combinando dos análisis que hasta ahora
vivían separados y no se hablaban entre sí:

  * Individual (`clima.mejor_rezago_por_variable`): cada variable SOLA, correlacionada
    contra cada objetivo, buscando su propio mejor desfase. No dice qué pasa cuando las
    variables actúan juntas.
  * Conjunta (`aporte_conjunto_por_objetivo`, acá): el mismo modelo XGBoost de siempre —
    las 7 `FEATURES` con la ventana que esté activa en el sidebar — entrenado una vez por
    objetivo y explicado con SHAP. Dice cuánto pesa cada variable DADO que las demás ya
    están en el modelo.

Ninguna de las dos reemplaza a la otra: la individual sirve para elegir con criterio la
ventana de cada variable en el sidebar; la conjunta dice qué le queda a cada una una vez
que se controla por el resto.

«Floración» entra como objetivo, no como predictor: probado directo (floración con su
propio desfase como una `FEATURE` más), la muestra colapsa a 20-30 filas y el modelo se
rompe (ver `docs/data/resumen_sesion.md` §12) — pero como objetivo, con las MISMAS 7
`FEATURES` de siempre, la muestra es 117 filas y el modelo generaliza (R² honesto +0,19).
Es la mitad que faltaba de la cadena clima → floración → Frutos: acá se mide si el clima y
el riego, juntos, explican la floración; `rezago_floracion` mide la otra mitad
(floración → Frutos) al grano de la celda con efecto fijo de módulo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import FEATURES, etiqueta
from . import evaluacion as _ev
from . import modelo as _modelo

OBJETIVOS: tuple[tuple[str, str], ...] = (
    ("KgHa", "kg/ha"), ("Frutos", "Frutos"), ("Peso", "Peso"),
    ("flores_promedio", "Floración"),
)


def aporte_conjunto_por_objetivo(tabla: pd.DataFrame) -> pd.DataFrame:
    """SHAP del modelo de 7 variables, repetido para KgHa, Frutos y Peso.

    Mismas `FEATURES`, mismos hiperparámetros (`PARAMS`, calibrados para KgHa — ver
    `honesto_por_objetivo` para saber si eso es razonable en cada caso) y la ventana de
    rezago que esté activa en el panel recibido: cambiar el sidebar y volver a llamar esta
    función mueve las tres columnas a la vez, porque las tres leen la misma tabla.
    """
    filas = []
    for objetivo, nombre in OBJETIVOS:
        if objetivo not in tabla.columns or tabla[objetivo].notna().sum() < 30:
            continue
        ajuste = _modelo.entrenar(tabla, objetivo=objetivo)
        for variable, valor in ajuste.importancia.items():
            filas.append({
                "Objetivo": nombre,
                "Variable": etiqueta(variable),
                "clave": variable,
                "Aporte SHAP medio (|valor|)": float(valor),
                "n filas del ajuste": len(ajuste.X),
            })
    return pd.DataFrame(filas)


def honesto_por_objetivo(
    tabla: pd.DataFrame, particion_clave: str = "por_bloque",
) -> pd.DataFrame:
    """R² y MAE fuera de muestra del modelo de 7 variables, para cada objetivo.

    Sin esto, un ranking SHAP de Frutos o Peso podría leerse con la misma confianza que
    el de KgHa aunque no generalice nada — los hiperparámetros no se calibraron para ellos
    (ver el docstring de `modelo.entrenar`). Se reporta con la partición honesta por
    defecto, no con la optimista.
    """
    particion = _ev.PARTICIONES[particion_clave]
    conjunto = _ev.CONJUNTOS["completo"]
    filas = []
    for objetivo, nombre in OBJETIVOS:
        if objetivo not in tabla.columns or tabla[objetivo].notna().sum() < 30:
            continue
        base = tabla.dropna(subset=[*FEATURES, objetivo])
        piso = float(np.mean((base[objetivo] - base[objetivo].mean()) ** 2))
        m = _ev.medir(tabla, conjunto, particion, objetivo=objetivo)
        filas.append({
            "Objetivo": nombre,
            "R² honesto": m.r2,
            "MAE honesto": m.mae,
            "n filas": len(base),
            "Varianza del objetivo (referencia)": piso,
            "Hiperparámetros propios": objetivo == "KgHa",
        })
    return pd.DataFrame(filas)
