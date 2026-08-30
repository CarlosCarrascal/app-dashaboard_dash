"""Contratos de datos compartidos por el núcleo analítico.

Este módulo contiene tipos pequeños y estables que pueden ser usados por varias
transformaciones sin obligarlas a importarse entre sí.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class Hallazgo:
    """Un problema de calidad detectado al armar el panel."""

    clave: str
    titulo: str
    gravedad: str  # "alta" | "media" | "baja"
    detalle: str
    efecto: str


@dataclass
class Panel:
    """Panel consolidado y hallazgos de calidad de la carga.

    El contrato vive aquí para que las transformaciones de datos, floración y poda
    compartan el tipo sin importarse entre sí. La asignación de ``__module__`` conserva
    la identidad histórica de ``analitica.dominio.nucleo.datos.Panel`` para pickles y consumidores
    que inspeccionan esa ruta pública.
    """

    tabla: "pd.DataFrame"
    hallazgos: list[Hallazgo] = field(default_factory=list)

    @property
    def n_modulos(self) -> int:
        return int(self.tabla.celda.nunique())

    @property
    def n_semanas(self) -> int:
        return int(self.tabla.nsem.nunique())

    def graves(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.gravedad == "alta"]


# Compatibilidad de serialización: antes la clase se definía en ``datos.py``.
Panel.__module__ = "analitica.dominio.nucleo.datos"
