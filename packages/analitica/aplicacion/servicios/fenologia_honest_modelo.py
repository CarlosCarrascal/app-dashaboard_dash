"""Transformación de señales y predicción candidata del screening."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from .fenologia_honest_contratos import (
    HORIZONTES,
    SEMANA_DESARROLLO_FINAL,
    SEMANA_INICIAL,
    Configuracion,
)


def redistribuir_curva(valores: Iterable[float], desplazamiento: float) -> np.ndarray:
    """Desplaza h1-h6 por interpolación lineal y conserva exactamente su total."""

    origen = np.asarray(list(valores), dtype=float)
    if origen.shape != (6,):
        raise ValueError("La curva debe contener exactamente h1-h6")
    if np.any(origen < 0):
        raise ValueError("La curva no puede contener kilos negativos")
    destino = np.zeros(6, dtype=float)
    delta = float(np.clip(desplazamiento, -1.0, 1.0))
    for indice, kilos in enumerate(origen, start=1):
        posicion = float(np.clip(indice + delta, 1.0, 6.0))
        inferior = int(np.floor(posicion))
        superior = int(np.ceil(posicion))
        if inferior == superior:
            destino[inferior - 1] += kilos
        else:
            peso_superior = posicion - inferior
            destino[inferior - 1] += kilos * (1.0 - peso_superior)
            destino[superior - 1] += kilos * peso_superior
    if not np.isclose(destino.sum(), origen.sum(), rtol=0, atol=1e-8):
        raise AssertionError("El desplazamiento alteró el volumen h1-h6")
    return destino


def _columna_clima(config: Configuracion) -> str | None:
    if not config.variable_clima or not config.ventana_dias:
        return None
    if config.variable_clima == "gdd":
        if config.tbase is None:
            raise ValueError("GDD requiere temperatura base")
        etiqueta = str(config.tbase).replace(".", "_")
        return f"gdd_{etiqueta}_{config.ventana_dias}d"
    return f"{config.variable_clima}_{config.ventana_dias}d"


def _escalar_entrenamiento(
    panel: pd.DataFrame, columnas: Iterable[str]
) -> dict[str, tuple[float, float]]:
    entrenamiento = panel[panel.semana_h1.between(SEMANA_INICIAL, SEMANA_DESARROLLO_FINAL)]
    escalas: dict[str, tuple[float, float]] = {}
    for columna in columnas:
        serie = pd.to_numeric(entrenamiento[columna], errors="coerce").dropna()
        centro = float(serie.median()) if len(serie) else 0.0
        mad = float((serie - centro).abs().median()) if len(serie) else 0.0
        escala = 1.4826 * mad
        if not np.isfinite(escala) or escala < 1e-9:
            escala = float(serie.std(ddof=0)) if len(serie) else 1.0
        if not np.isfinite(escala) or escala < 1e-9:
            escala = 1.0
        escalas[columna] = (centro, escala)
    return escalas


def construir_panel_features(
    macro: pd.DataFrame,
    clima_asof: pd.DataFrame,
    fenologia_asof: pd.DataFrame,
) -> pd.DataFrame:
    emisiones = macro[["fecha_emision"]].drop_duplicates()
    fundos = macro[["fecha_emision", "fundo_operativo"]].drop_duplicates()
    panel = fundos.merge(clima_asof, on="fecha_emision", how="left", validate="many_to_one")
    panel = panel.merge(
        fenologia_asof,
        on=["fecha_emision", "fundo_operativo"],
        how="left",
        validate="one_to_one",
    )
    panel["semana_h1"] = (
        (panel.fecha_emision + pd.Timedelta(days=7)).dt.isocalendar().week.astype(int)
    )
    if len(panel) != len(fundos) or len(emisiones) != panel.fecha_emision.nunique():
        raise AssertionError("La integración de features cambió el grano emisión-fundo")
    return panel.sort_values(["fecha_emision", "fundo_operativo"]).reset_index(drop=True)


def calcular_desplazamientos(
    panel: pd.DataFrame,
    config: Configuracion,
    *,
    escalas: dict[str, tuple[float, float]] | None = None,
) -> tuple[pd.DataFrame, dict[str, tuple[float, float]]]:
    """Convierte señales as-of en semanas de adelanto/retraso, nunca en kg."""

    salida = panel.copy()
    columna_clima = _columna_clima(config)
    columnas = [c for c in (columna_clima, config.variable_fenologia) if c]
    escalas = escalas or _escalar_entrenamiento(salida, columnas)
    desplazamiento = pd.Series(0.0, index=salida.index)
    usable = pd.Series(False, index=salida.index)

    if columna_clima:
        cobertura = salida[f"clima_cobertura_{config.ventana_dias}d"].ge(0.80)
        valores = pd.to_numeric(salida[columna_clima], errors="coerce")
        centro, escala = escalas[columna_clima]
        z = ((valores - centro) / escala).clip(-3.0, 3.0).where(cobertura, 0.0)
        desplazamiento += config.coef_clima * z.fillna(0.0)
        usable |= cobertura & valores.notna()

    if config.variable_fenologia:
        es_estado = config.variable_fenologia in {"indice_estado", "prop_e45"}
        cobertura_col = "cobertura_estados" if es_estado else "cobertura_flores"
        cobertura = salida[cobertura_col].ge(0.30)
        valores = pd.to_numeric(salida[config.variable_fenologia], errors="coerce")
        centro, escala = escalas[config.variable_fenologia]
        z = ((valores - centro) / escala).clip(-3.0, 3.0).where(cobertura, 0.0)
        desplazamiento += config.coef_fenologia * z.fillna(0.0)
        usable |= cobertura & valores.notna()

    salida["desplazamiento_semanas"] = desplazamiento.clip(
        -config.desplazamiento_max, config.desplazamiento_max
    )
    salida["feature_usable"] = usable
    return salida, escalas


def aplicar_desplazamientos(curvas: pd.DataFrame, desplazamientos: pd.DataFrame) -> pd.DataFrame:
    """Aplica un único desplazamiento as-of por emisión-fundo."""

    claves = ["fecha_emision", "fundo_operativo"]
    columnas = claves + ["desplazamiento_semanas", "feature_usable"]
    tabla = curvas.merge(desplazamientos[columnas], on=claves, how="left", validate="many_to_one")
    tabla["desplazamiento_semanas"] = tabla.desplazamiento_semanas.fillna(0.0)
    tabla["feature_usable"] = tabla.feature_usable.fillna(False).astype(bool)
    tabla = tabla.sort_values([*claves, "horizonte_semanas"], kind="stable").reset_index(drop=True)
    tamanos = tabla.groupby(claves, sort=False).size()
    if not tamanos.eq(6).all():
        raise ValueError("Una curva agregada no contiene seis horizontes")
    matriz_h = tabla.horizonte_semanas.to_numpy(dtype=int).reshape(-1, 6)
    if not np.all(matriz_h == np.asarray(HORIZONTES, dtype=int)):
        raise ValueError("Una curva agregada no contiene h1-h6 ordenados")

    origen = tabla.macro_kg.to_numpy(dtype=float).reshape(-1, 6)
    delta = tabla.desplazamiento_semanas.to_numpy(dtype=float).reshape(-1, 6)[:, 0]
    delta = np.clip(delta, -1.0, 1.0)
    destino = np.zeros_like(origen)
    filas = np.arange(len(origen))
    for indice in range(6):
        posicion = np.clip((indice + 1) + delta, 1.0, 6.0)
        inferior = np.floor(posicion).astype(int) - 1
        superior = np.ceil(posicion).astype(int) - 1
        peso_superior = posicion - np.floor(posicion)
        np.add.at(destino, (filas, inferior), origen[:, indice] * (1.0 - peso_superior))
        np.add.at(destino, (filas, superior), origen[:, indice] * peso_superior)
    if not np.allclose(destino.sum(axis=1), origen.sum(axis=1), rtol=0, atol=1e-8):
        raise AssertionError("El desplazamiento alteró el volumen h1-h6")
    tabla["candidate_kg"] = destino.reshape(-1)
    return tabla
