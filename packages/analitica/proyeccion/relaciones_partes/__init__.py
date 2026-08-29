"""Implementaciones físicas por responsabilidad para análisis de relaciones.

Cada submódulo es independiente de la fachada histórica ``relaciones.py``. La
fachada conserva los reexports para consumidores existentes, mientras este
paquete ofrece fronteras explícitas para panel, estadística, packing y evidencia.
"""

from .estadistica import (
    HIPOTESIS,
    ORDEN_CICLO,
    PREDICTORES_CULTIVO,
    PREDICTORES_EXTERNOS,
    RESPUESTAS_MATRIZ,
    REZAGOS_MATRIZ,
    Hipotesis,
    evaluar_matriz_relaciones,
    evaluar_relaciones,
)
from .evidencia import (
    clasificar_hallazgos,
    generar_claims,
    hallazgos_matriz,
    resumen_matriz,
    sensibilidad_gdd,
)
from .packing import panel_packing, relaciones_packing
from .panel import construir_panel_relaciones

__all__ = [
    "clasificar_hallazgos",
    "construir_panel_relaciones",
    "evaluar_matriz_relaciones",
    "evaluar_relaciones",
    "generar_claims",
    "hallazgos_matriz",
    "panel_packing",
    "relaciones_packing",
    "resumen_matriz",
    "sensibilidad_gdd",
    "HIPOTESIS",
    "ORDEN_CICLO",
    "PREDICTORES_CULTIVO",
    "PREDICTORES_EXTERNOS",
    "REZAGOS_MATRIZ",
    "RESPUESTAS_MATRIZ",
    "Hipotesis",
]
