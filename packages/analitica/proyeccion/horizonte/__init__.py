"""Implementación interna del pronóstico y corrección por horizonte."""

from . import pronostico_horizonte as _implementacion

__all__ = list(_implementacion.__all__)
for _nombre in __all__:
    globals()[_nombre] = getattr(_implementacion, _nombre)
