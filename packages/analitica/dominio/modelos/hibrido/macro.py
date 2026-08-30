"""Implementación pura de la macro ``forecast`` de Excel.

Este módulo contiene únicamente la matemática y sus adaptadores de parámetros. No lee
libros Excel ni conoce PostgreSQL; la ruta histórica ``macro_legacy`` queda como fachada
compatible para los consumidores existentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp

import numpy as np
import pandas as pd
from scipy.special import ndtr


@dataclass(frozen=True)
class MacroParams:
    """Parámetros nombrados equivalentes a las columnas de ``Parametros``."""

    area_ha: float
    plantas: float
    fecha_pivote: pd.Timestamp
    ola_1_media_dias: float
    ola_1_desvio_dias: float
    ola_1_multiplicador: float
    ola_2_media_dias: float
    ola_2_desvio_dias: float
    ola_2_multiplicador: float
    ola_3_media_dias: float
    ola_3_desvio_dias: float
    ola_3_multiplicador: float
    peso_1_base_g: float
    peso_1_tasa: float
    peso_2_base_g: float
    peso_2_tasa: float
    peso_3_base_g: float
    peso_3_tasa: float
    multiplicador_carga: float = 1.0

    def __post_init__(self) -> None:
        if self.area_ha <= 0:
            raise ValueError("area_ha debe ser positiva")
        if self.plantas <= 0:
            raise ValueError("plantas debe ser positivo")
        if any(
            valor < 0
            for valor in (
                self.ola_1_desvio_dias,
                self.ola_2_desvio_dias,
                self.ola_3_desvio_dias,
            )
        ):
            raise ValueError("la desviación de cada ola no puede ser negativa")
        if self.multiplicador_carga < 0:
            raise ValueError("multiplicador_carga no puede ser negativo")


def _fraccion_ola(
    inicio: pd.Timestamp,
    fin: pd.Timestamp,
    pivote: pd.Timestamp,
    media: float,
    desvio: float,
    multiplicador: float,
) -> float:
    """Frutos de una ola en la ventana [inicio, fin], como en ``NormDist`` acumulada."""

    if desvio <= 0:
        return float(multiplicador if inicio <= pivote + pd.Timedelta(days=media) <= fin else 0.0)
    z_fin = ((fin - pivote).days - media) / desvio
    z_inicio = ((inicio - pivote).days - media) / desvio
    return float((ndtr(z_fin) - ndtr(z_inicio)) * multiplicador)


def proyectar_macro(
    parametros: MacroParams,
    ventanas: pd.DataFrame,
) -> pd.DataFrame:
    """Reproduce la salida esencial de la macro para una o varias pasadas."""

    requeridas = {"fecha_inicio", "fecha_objetivo"}
    faltantes = requeridas - set(ventanas.columns)
    if faltantes:
        raise ValueError(f"ventanas requiere: {sorted(faltantes)}")
    salida = ventanas.copy()
    salida["fecha_inicio"] = pd.to_datetime(salida["fecha_inicio"], errors="raise")
    salida["fecha_objetivo"] = pd.to_datetime(salida["fecha_objetivo"], errors="raise")
    if (salida.fecha_objetivo < salida.fecha_inicio).any():
        raise ValueError("fecha_objetivo no puede ser anterior a fecha_inicio")

    olas = (
        (parametros.ola_1_media_dias, parametros.ola_1_desvio_dias, parametros.ola_1_multiplicador),
        (parametros.ola_2_media_dias, parametros.ola_2_desvio_dias, parametros.ola_2_multiplicador),
        (parametros.ola_3_media_dias, parametros.ola_3_desvio_dias, parametros.ola_3_multiplicador),
    )
    pesos = (
        (parametros.peso_1_base_g, parametros.peso_1_tasa),
        (parametros.peso_2_base_g, parametros.peso_2_tasa),
        (parametros.peso_3_base_g, parametros.peso_3_tasa),
    )

    filas: list[dict[str, float]] = []
    for fila in salida.itertuples(index=False):
        inicio = fila.fecha_inicio
        fin = fila.fecha_objetivo
        cantidades = np.asarray(
            [
                _fraccion_ola(inicio, fin, parametros.fecha_pivote, media, desvio, escala)
                for media, desvio, escala in olas
            ],
            dtype=float,
        )
        carga = float(getattr(fila, "multiplicador_carga", parametros.multiplicador_carga))
        frutos = float(np.maximum(cantidades, 0).sum() * carga)
        dias = (fin - parametros.fecha_pivote).days
        pesos_ola = np.asarray([base * exp(tasa * dias) for base, tasa in pesos], dtype=float)
        cantidades_positivas = np.maximum(cantidades, 0)
        total_cantidades = cantidades_positivas.sum()
        peso = (
            float(np.dot(cantidades_positivas, pesos_ola) / total_cantidades)
            if total_cantidades > 0
            else 0.0
        )
        kg = float(parametros.plantas * frutos * peso / 1000)
        resultado = {
            "frutos_por_planta": frutos,
            "peso_baya_g": peso,
            "plantas": float(parametros.plantas),
            "kg": kg,
            "kg_ha": kg / float(parametros.area_ha),
            "macro_dias_desde_pivote": float(dias),
            "macro_multiplicador_carga": carga,
        }
        if hasattr(fila, "pasada"):
            resultado["pasada"] = fila.pasada
        filas.append(resultado)
    calculo = pd.DataFrame(filas, index=salida.index)
    return pd.concat([salida, calculo], axis=1)


def parametros_desde_fila(fila: dict[str, object] | pd.Series) -> MacroParams:
    """Construye parámetros desde nombres de columnas, no desde posiciones Excel."""

    get = lambda nombre: fila[nombre]  # noqa: E731
    return MacroParams(
        area_ha=float(get("Area" if "Area" in fila else "area_ha")),
        plantas=float(get("NPlantas" if "NPlantas" in fila else "plantas")),
        fecha_pivote=pd.Timestamp(get("FPoda" if "FPoda" in fila else "fecha_poda")),
        ola_1_media_dias=float(get("X1" if "X1" in fila else "ola_1_media_dias")),
        ola_1_desvio_dias=float(get("O1" if "O1" in fila else "ola_1_desvio_dias")),
        ola_1_multiplicador=float(get("N1" if "N1" in fila else "ola_1_multiplicador")),
        ola_2_media_dias=float(get("X2" if "X2" in fila else "ola_2_media_dias")),
        ola_2_desvio_dias=float(get("O2" if "O2" in fila else "ola_2_desvio_dias")),
        ola_2_multiplicador=float(get("N2" if "N2" in fila else "ola_2_multiplicador")),
        ola_3_media_dias=float(get("X3" if "X3" in fila else "ola_3_media_dias")),
        ola_3_desvio_dias=float(get("O3" if "O3" in fila else "ola_3_desvio_dias")),
        ola_3_multiplicador=float(get("N3" if "N3" in fila else "ola_3_multiplicador")),
        peso_1_base_g=float(get("A1" if "A1" in fila else "peso_1_base_g")),
        peso_1_tasa=float(get("B1" if "B1" in fila else "peso_1_tasa")),
        peso_2_base_g=float(get("A2" if "A2" in fila else "peso_2_base_g")),
        peso_2_tasa=float(get("B2" if "B2" in fila else "peso_2_tasa")),
        peso_3_base_g=float(get("A3" if "A3" in fila else "peso_3_base_g")),
        peso_3_tasa=float(get("B3" if "B3" in fila else "peso_3_tasa")),
        multiplicador_carga=(
            float(get("multiplicador_carga")) if "multiplicador_carga" in fila else 1.0
        ),
    )


def parametros_desde_bhattacharya(parametros, *, area_ha: float = 1.0) -> MacroParams:
    """Adapta los parámetros nombrados de ``bhattacharya`` a la macro legacy."""

    fecha_poda = pd.Timestamp(parametros.fecha_poda or "2025-12-29")
    peso_a = float(parametros.peso_a)
    peso_b = float(parametros.peso_b)
    peso_a2 = float(
        parametros.peso_a2 if getattr(parametros, "peso_a2", None) is not None else peso_a
    )
    peso_b2 = float(
        parametros.peso_b2 if getattr(parametros, "peso_b2", None) is not None else peso_b
    )
    peso_a3 = float(
        parametros.peso_a3 if getattr(parametros, "peso_a3", None) is not None else peso_a
    )
    peso_b3 = float(
        parametros.peso_b3 if getattr(parametros, "peso_b3", None) is not None else peso_b
    )
    return MacroParams(
        area_ha=max(float(area_ha), 1e-9),
        plantas=max(float(parametros.n_plantas), 1.0),
        fecha_pivote=fecha_poda,
        ola_1_media_dias=float(parametros.mu1),
        ola_1_desvio_dias=float(parametros.sigma1),
        ola_1_multiplicador=float(parametros.N1),
        ola_2_media_dias=float(parametros.mu2),
        ola_2_desvio_dias=float(parametros.sigma2),
        ola_2_multiplicador=float(parametros.N2),
        ola_3_media_dias=float(parametros.mu3),
        ola_3_desvio_dias=float(parametros.sigma3),
        ola_3_multiplicador=float(parametros.N3),
        peso_1_base_g=peso_a,
        peso_1_tasa=peso_b,
        peso_2_base_g=peso_a2,
        peso_2_tasa=peso_b2,
        peso_3_base_g=peso_a3,
        peso_3_tasa=peso_b3,
        multiplicador_carga=1.0,
    )


__all__ = [
    "MacroParams",
    "_fraccion_ola",
    "parametros_desde_bhattacharya",
    "parametros_desde_fila",
    "proyectar_macro",
]
