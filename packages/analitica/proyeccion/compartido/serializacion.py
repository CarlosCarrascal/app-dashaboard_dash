"""Serialización determinista pura para persistencia y auditoría."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd


def serializar_json(valor: object) -> str:
    """Serializa metadatos sin dejar ``NaN`` inválidos en columnas JSONB."""

    def limpiar(obj):
        if isinstance(obj, dict):
            return {str(clave): limpiar(valor) for clave, valor in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [limpiar(valor) for valor in obj]
        if isinstance(obj, np.generic):
            obj = obj.item()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, float) and not np.isfinite(obj):
            return None
        if obj is None:
            return None
        try:
            perdido = pd.isna(obj)
            if isinstance(perdido, (bool, np.bool_)) and perdido:
                return None
        except (TypeError, ValueError):
            pass
        return obj

    return json.dumps(limpiar(valor), ensure_ascii=False, default=str, allow_nan=False)


def serializar_jsonb(valor: object) -> str:
    """Serializa una columna JSONB sin envolver dos veces JSON ya generado."""
    if isinstance(valor, str):
        try:
            decodificado = json.loads(valor)
        except (TypeError, ValueError):
            pass
        else:
            if isinstance(decodificado, (dict, list)):
                valor = decodificado
    return serializar_json(valor)


def limpiar_valor(valor: object) -> object:
    """Convierte valores pandas/numpy en valores aceptables para psycopg."""
    if isinstance(valor, dict):
        return {str(clave): limpiar_valor(elemento) for clave, elemento in valor.items()}
    if isinstance(valor, np.ndarray):
        return [limpiar_valor(elemento) for elemento in valor.tolist()]
    if isinstance(valor, list):
        return [limpiar_valor(elemento) for elemento in valor]
    if isinstance(valor, tuple):
        return tuple(limpiar_valor(elemento) for elemento in valor)
    if isinstance(valor, np.generic):
        valor = valor.item()
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()
    ausente = pd.isna(valor)
    if isinstance(ausente, (bool, np.bool_)) and ausente:
        return None
    if isinstance(valor, float) and not np.isfinite(valor):
        return None
    return valor

__all__ = ["limpiar_valor", "serializar_json", "serializar_jsonb"]
