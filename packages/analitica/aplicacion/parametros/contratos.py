"""Contratos compartidos del challenger de parámetros as-of."""

from __future__ import annotations

from dataclasses import dataclass

NOMBRE_MODELO = "HibridoParametrosAsOf_v1"
VERSION_MODELO = "excel_params_asof_gdd_residual_v1"
CLAVES = ["campania", "lote_id", "fecha_objetivo"]
PARAMETROS_NOMBRADOS = (
    "X1",
    "O1",
    "N1",
    "X2",
    "O2",
    "N2",
    "X3",
    "O3",
    "N3",
    "A1",
    "B1",
    "A2",
    "B2",
    "A3",
    "B3",
)


@dataclass(frozen=True)
class ConfiguracionParametrosAsOf:
    """Configuración explícita y auditable del challenger."""

    minimo_entrenamiento: int = 30
    minimo_obs_lote: int = 4
    minimo_semanas_lote: int = 2
    max_shift_days: int = 14
    gdd_bases: tuple[float, ...] = (0.0, 4.4, 7.0, 8.0)
    gdd_ventanas: tuple[int, ...] = (7, 14, 21, 28)
    peso_macro_min: float = 0.15
    peso_macro_max: float = 1.0
    peso_macro_default: float = 1.0
    regularizacion_peso: float = 20.0

    def __post_init__(self) -> None:
        if self.minimo_entrenamiento < 0:
            raise ValueError("minimo_entrenamiento no puede ser negativo")
        if not 0 <= self.peso_macro_min <= self.peso_macro_max <= 1:
            raise ValueError("los límites de peso Macro deben estar entre 0 y 1")
        if not self.peso_macro_min <= self.peso_macro_default <= self.peso_macro_max:
            raise ValueError("peso_macro_default debe estar dentro de los límites")


__all__ = [
    "NOMBRE_MODELO",
    "VERSION_MODELO",
    "CLAVES",
    "PARAMETROS_NOMBRADOS",
    "ConfiguracionParametrosAsOf",
]
