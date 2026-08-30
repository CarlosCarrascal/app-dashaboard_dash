"""Utilidades compartidas por los módulos de proyección.

La implementación física está consolidada en ``utilidades.py``. Los nombres
de los antiguos submódulos se registran como aliases para conservar imports
existentes durante la transición.
"""

import sys
import types

from . import utilidades as _utilidades
from .utilidades import (
    CLAVE_FORECAST,
    CLAVE_RESIDUAL,
    json_reproducible,
    limpiar_valor,
    lunes_semana,
    normalizar_forecast_candidate,
    normalizar_panel,
    serializar_json,
    serializar_jsonb,
    sha256_archivo,
    sha256_dataframe,
    ultimo_disponible,
)

for _nombre in ("fechas", "hashes", "identidad", "normalizacion", "serializacion"):
    _compat = types.ModuleType(f"{__name__}.{_nombre}", _utilidades.__doc__)
    _compat.__package__ = __name__
    _compat.__file__ = _utilidades.__file__
    _compat.__all__ = _utilidades.__all__
    _compat.__dict__.update(
        {nombre: getattr(_utilidades, nombre) for nombre in _utilidades.__all__}
    )
    if _nombre == "identidad":
        _compat._limpio_json = _utilidades._limpio_json
    sys.modules[_compat.__name__] = _compat
    globals()[_nombre] = _compat

__all__ = [
    "json_reproducible",
    "CLAVE_FORECAST",
    "CLAVE_RESIDUAL",
    "limpiar_valor",
    "lunes_semana",
    "normalizar_forecast_candidate",
    "normalizar_panel",
    "serializar_json",
    "serializar_jsonb",
    "sha256_archivo",
    "sha256_dataframe",
    "ultimo_disponible",
]
