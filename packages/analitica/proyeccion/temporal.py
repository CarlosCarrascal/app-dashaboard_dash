"""Fachada histórica de las primitivas temporales compartidas."""

from .compartido.fechas import (
    lunes_semana,
    ultimo_disponible,
)

__all__ = ["lunes_semana", "ultimo_disponible"]
