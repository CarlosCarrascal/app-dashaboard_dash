"""Núcleo analítico independiente de cualquier framework de interfaz.

El paquete no importa cálculos pesados al inicializarse: así leer la configuración no
obliga a cargar XGBoost, SHAP o Plotly. Las cinco rutas de paquete que se reorganizaron
(``nucleo``, ``servicios``, ``visualizaciones``, ``scripts`` y ``commands``) se registran
como aliases de compatibilidad hacia sus capas canónicas. Registrar el paquete no importa
ningún algoritmo; los consumidores cargan el módulo concreto cuando lo necesitan.
"""

from __future__ import annotations

import importlib
import sys

_FACHADAS_PAQUETE = {
    "nucleo": "analitica.dominio.nucleo",
    "servicios": "analitica.aplicacion.servicios",
    "visualizaciones": "analitica.interfaces.visualizaciones",
    "scripts": "analitica.interfaces.scripts",
    "commands": "analitica.interfaces.commands",
}


def _registrar_fachadas_paquete() -> None:
    """Conserva imports históricos sin duplicar archivos ni implementaciones."""

    for nombre, destino in _FACHADAS_PAQUETE.items():
        sys.modules.setdefault(f"{__name__}.{nombre}", importlib.import_module(destino))


_registrar_fachadas_paquete()

__all__ = list(_FACHADAS_PAQUETE)
