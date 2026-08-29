"""Fachada histórica de serialización; la implementación vive en ``compartido``."""

from ..compartido.serializacion import (
    limpiar_valor,
    serializar_json,
    serializar_jsonb,
)

__all__ = ["limpiar_valor", "serializar_json", "serializar_jsonb"]
