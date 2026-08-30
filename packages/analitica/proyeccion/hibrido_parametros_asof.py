"""Fachada histórica del challenger híbrido con parámetros as-of.

La implementación vive en ``proyeccion.parametros``. Esta ruta se conserva para
integraciones existentes y reexporta los mismos objetos sin envolverlos, de modo que
la identidad y la API histórica permanezcan compatibles.
"""

from __future__ import annotations

from .compartido import sha256_archivo
from .parametros.contratos import (
    CLAVES,  # noqa: F401 - alias histórico
    NOMBRE_MODELO,  # noqa: F401 - alias histórico
    PARAMETROS_NOMBRADOS,  # noqa: F401 - alias histórico
    VERSION_MODELO,  # noqa: F401 - alias histórico
    ConfiguracionParametrosAsOf,  # noqa: F401 - alias histórico
)
from .parametros.desplazamientos import (
    _deduplicar_historial,  # noqa: F401 - alias histórico
    _desplazamiento_gdd_por_fila,  # noqa: F401 - alias histórico
    aprender_desplazamiento,  # noqa: F401 - alias histórico
    seleccionar_gdd_config,  # noqa: F401 - alias histórico
)
from .parametros.ejecucion import (
    backtest_hibrido_parametros_asof,  # noqa: F401 - alias histórico
    ejecutar_emision_parametros_asof,  # noqa: F401 - alias histórico
)
from .parametros.mezcla import (  # noqa: F401 - aliases históricos
    _completar_gdd,
    _interpolar_componentes,
    _mezclar_componentes,
    seleccionar_peso_macro,  # noqa: F401 - alias histórico
)
from .parametros.normalizacion import (
    _parametros_excel_asof,  # noqa: F401 - alias histórico
    _serie_numerica,  # noqa: F401 - alias histórico
    normalizar_parametros_excel,  # noqa: F401 - alias histórico
)
from .parametros.snapshots import (  # noqa: F401 - aliases históricos
    _deltas_parametros,
    construir_snapshot_parametros,
)

__all__ = [
    "NOMBRE_MODELO",
    "VERSION_MODELO",
    "ConfiguracionParametrosAsOf",
    "normalizar_parametros_excel",
    "sha256_archivo",
    "seleccionar_peso_macro",
    "aprender_desplazamiento",
    "seleccionar_gdd_config",
    "ejecutar_emision_parametros_asof",
    "backtest_hibrido_parametros_asof",
    "construir_snapshot_parametros",
]
