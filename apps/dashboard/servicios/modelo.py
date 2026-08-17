"""Entrenamiento cacheado del modelo XGBoost (`nucleo.entrenar`).

Entrenar tarda unos segundos (452 filas, 300 árboles + SHAP). Un diccionario de proceso
alcanza como caché — no hace falta `Serverside` ni `flask_caching` acá: el panel es un
único Excel por proceso (esta app todavía no tiene subida de otro archivo, ver
`servicios/carga.py`), así que cachear por objetivo es correcto y no arriesga servir un
ajuste viejo contra datos nuevos. Cada página sigue llamando esta función directo desde su
propio callback — el `Ajuste` nunca necesita viajar por un `dcc.Store` porque no sale del
proceso de Python.
"""

from __future__ import annotations

import pandas as pd

from analitica import nucleo

_CACHE: dict[str, "nucleo.Ajuste"] = {}


def entrenar(tabla: pd.DataFrame, objetivo: str = "KgHa") -> "nucleo.Ajuste":
    if objetivo not in _CACHE:
        _CACHE[objetivo] = nucleo.entrenar(tabla, objetivo=objetivo)
    return _CACHE[objetivo]
