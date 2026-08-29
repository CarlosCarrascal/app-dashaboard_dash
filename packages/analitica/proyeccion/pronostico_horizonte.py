"""Fachada compatible para la implementación interna de horizonte."""

from contextlib import suppress as _suppress

from .horizonte import pronostico_horizonte as _implementacion

__all__ = list(_implementacion.__all__)

# Reexportamos también los nombres históricos fuera de ``__all__``. Esto evita
# que consumidores que usaban CLAVES o un helper interno queden rotos durante
# la extracción; la API documentada sigue siendo exactamente ``__all__``.
for _nombre in dir(_implementacion):
    if _nombre.startswith("__"):
        continue
    globals()[_nombre] = getattr(_implementacion, _nombre)

# Las funciones y la configuración conservan el módulo público antiguo en
# repr(), pickling e introspección, aunque su código viva bajo ``horizonte``.
_prefijo_interno = f"{_implementacion.__package__}."
for _nombre in __all__:
    _valor = globals()[_nombre]
    if getattr(_valor, "__module__", "").startswith(_prefijo_interno):
        with _suppress(AttributeError, TypeError):
            _valor.__module__ = __name__
