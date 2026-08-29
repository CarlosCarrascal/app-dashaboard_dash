"""Contratos y configuración del corrector por horizonte."""

from __future__ import annotations

from dataclasses import dataclass

CLAVES = (
    "campania",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "lote_id",
)


@dataclass(frozen=True)
class ConfiguracionCorreccionHorizonte:
    """Configuración pequeña que puede someterse a successive halving."""

    nivel: str = "ninguno"
    ventana: int = 8
    regularizacion: float = 4.0
    factor_min: float = 0.75
    factor_max: float = 1.25
    peso_correccion: float = 1.0
    minimo_observaciones: int = 2
    por_horizonte: bool = True

    def __post_init__(self) -> None:
        if self.nivel not in {"ninguno", "global", "fundo", "modulo"}:
            raise ValueError("nivel debe ser ninguno, global, fundo o modulo")
        if self.ventana < 2:
            raise ValueError("ventana debe ser al menos 2")
        if self.regularizacion < 0:
            raise ValueError("regularizacion no puede ser negativa")
        if not 0 < self.factor_min <= 1 <= self.factor_max:
            raise ValueError("los límites deben contener el factor 1")
        if not 0 <= self.peso_correccion <= 1:
            raise ValueError("peso_correccion debe estar entre 0 y 1")
        if self.minimo_observaciones < 1:
            raise ValueError("minimo_observaciones debe ser al menos 1")
