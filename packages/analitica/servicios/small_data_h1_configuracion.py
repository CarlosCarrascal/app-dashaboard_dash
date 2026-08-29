"""Configuración del screening candidate-only de small data H1."""

from __future__ import annotations

from dataclasses import dataclass

from .small_data import (
    CAMPANIA_DEFAULT,
    RUN_ID_DEFAULT,
    ULTIMO_CIERRE_DEFAULT,
)

SEMANA_MAX_SELECCION = 30
SEMANAS_HOLDOUT = (31, 32, 33)
FUNDOS = ("Arena", "Ayllu", "Kawsay", "Quri")

FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "macro_lags": (
        "log_macro",
        "lag_error_1",
        "lag_error_media3",
        "lag_error_empresa_media3",
        "crecimiento_macro",
    ),
    "macro_lags_fase": (
        "log_macro",
        "lag_error_1",
        "lag_error_media3",
        "lag_error_empresa_media3",
        "crecimiento_macro",
        "fase_sin",
        "fase_cos",
    ),
    "macro_lags_forma": (
        "log_macro",
        "lag_error_1",
        "lag_error_media3",
        "lag_error_empresa_media3",
        "crecimiento_macro_1",
        "aceleracion_macro",
    ),
    "macro_lags_forma_fase": (
        "log_macro",
        "lag_error_1",
        "lag_error_media3",
        "lag_error_empresa_media3",
        "crecimiento_macro_1",
        "aceleracion_macro",
        "fase_sin",
        "fase_cos",
    ),
}


@dataclass(frozen=True)
class Configuracion:
    estimador: str
    feature_set: str
    alpha: float
    epsilon: float
    factor_minimo: float
    factor_maximo: float

    @property
    def id(self) -> str:
        return (
            f"{self.estimador}-{self.feature_set}-a{self.alpha:g}"
            f"-e{self.epsilon:g}-clip{self.factor_minimo:g}_{self.factor_maximo:g}"
        )


def configuraciones() -> list[Configuracion]:
    limites = ((0.65, 1.55), (0.80, 1.30))
    salida = [
        Configuracion("ridge", feature_set, alpha, 1.35, inferior, superior)
        for feature_set in FEATURE_SETS
        for alpha in (1.0, 10.0, 50.0)
        for inferior, superior in limites
    ]
    salida.extend(
        Configuracion("huber", feature_set, alpha, epsilon, inferior, superior)
        for feature_set in FEATURE_SETS
        for alpha in (0.001, 0.01)
        for epsilon in (1.35, 1.75)
        for inferior, superior in limites
    )
    return salida


__all__ = [
    "CAMPANIA_DEFAULT",
    "FEATURE_SETS",
    "FUNDOS",
    "RUN_ID_DEFAULT",
    "SEMANA_MAX_SELECCION",
    "SEMANAS_HOLDOUT",
    "ULTIMO_CIERRE_DEFAULT",
    "Configuracion",
    "configuraciones",
]
