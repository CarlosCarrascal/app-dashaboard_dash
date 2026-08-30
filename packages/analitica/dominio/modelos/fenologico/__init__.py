"""API canónica del modelo fenológico por componentes."""

import sys
import types

from . import ajuste as _ajuste
from . import especificacion as _especificacion
from . import evidencia as _evidencia
from . import incertidumbre as _incertidumbre
from . import metricas as _metricas
from . import panel as _panel
from . import servicio as _servicio
from .contratos import EscenarioFenologico, ResultadoFenologico
from .incertidumbre import aplicar_escenario_fenologico
from .panel import (
    auditar_panel_fenologico,
    construir_panel_fenologico,
    cosecha_real_semanal,
)
from .servicio import backtest_fenologico_v1, proyectar_fenologico_v1

# Alias privado de compatibilidad para adaptadores y pruebas históricas.
_predecir_emision = _servicio._predecir_emision

# El paquete ofrece una API única para la familia fenológica, pero mantiene cada
# responsabilidad en su módulo: ajuste, especificación, panel, evidencia e
# incertidumbre. Así los consumidores no necesitan conocer la implementación interna.
for _modulo in (
    _ajuste,
    _especificacion,
    _evidencia,
    _incertidumbre,
    _metricas,
    _panel,
    _servicio,
):
    for _nombre in getattr(_modulo, "__all__", ()):
        globals()[_nombre] = getattr(_modulo, _nombre)

# ``fenologico.modelos`` fue una frontera de transición que solo reexportaba
# ``ajuste``. Se conserva el import sin mantener otro archivo físico.
_modelos_compat = types.ModuleType(f"{__name__}.modelos", _ajuste.__doc__)
_modelos_compat.__package__ = __name__
_modelos_compat.__file__ = _ajuste.__file__
_modelos_compat.__all__ = _ajuste.__all__
_modelos_compat.__dict__.update({nombre: getattr(_ajuste, nombre) for nombre in _ajuste.__all__})
sys.modules[_modelos_compat.__name__] = _modelos_compat
modelos = _modelos_compat

__all__ = [
    "EscenarioFenologico",
    "ResultadoFenologico",
    "aplicar_escenario_fenologico",
    "auditar_panel_fenologico",
    "backtest_fenologico_v1",
    "construir_panel_fenologico",
    "cosecha_real_semanal",
    "proyectar_fenologico_v1",
]
