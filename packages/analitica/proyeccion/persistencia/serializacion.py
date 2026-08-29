"""Fachada de serialización usada por el repositorio analítico."""

from ..compartido.serializacion import limpiar_valor, serializar_json, serializar_jsonb

__all__ = ["limpiar_valor", "serializar_json", "serializar_jsonb"]
