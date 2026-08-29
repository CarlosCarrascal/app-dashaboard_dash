"""Implementación central del ajuste experto regularizado online.

El servicio contiene el algoritmo y su contrato de evaluación. Las entradas
``macro_kg`` y ``lagged_kg`` se construyen con información disponible antes de
la semana objetivo; R09 se conserva únicamente para comparación histórica.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.servicios.parametros_nowcast import (
    ACCESS_DEFAULT,
    leer_macro_h1,
    leer_reales_r09_fundo,
    normalizar_fundo,
)

PANEL_DEFAULT = Path(".tmp/lagged_parameter_h1_panel.parquet")


@dataclass(frozen=True)
class Configuracion:
    gamma_prior: float
    fuerza_prior: float
    shrink_fundo: float
    usar_escala: bool

    @property
    def id(self) -> str:
        return (
            f"g{self.gamma_prior:.2f}-p{self.fuerza_prior:.1f}-"
            f"k{self.shrink_fundo:.1f}-s{int(self.usar_escala)}"
        )


def _minimizar_absoluto(
    real: np.ndarray,
    macro: np.ndarray,
    lagged: np.ndarray,
    *,
    prior: float,
    fuerza_prior: float,
) -> float:
    if len(real) == 0:
        return float(prior)
    escala = max(float(np.median(np.abs(real))), 1.0)
    candidatos = np.linspace(0.0, 1.25, 51)
    perdidas = []
    for gamma in candidatos:
        pred = macro + gamma * (lagged - macro)
        perdida = float(np.abs(pred - real).sum())
        perdida += fuerza_prior * escala * abs(float(gamma) - prior)
        perdidas.append((perdida, float(gamma)))
    return min(perdidas)[1]


def _minimizar_escala(
    real: np.ndarray,
    base: np.ndarray,
    *,
    fuerza_prior: float,
) -> float:
    if len(real) == 0:
        return 1.0
    referencia = max(float(np.median(np.abs(real))), 1.0)
    candidatos = np.linspace(0.70, 1.30, 61)
    perdidas = []
    for escala in candidatos:
        perdida = float(np.abs(escala * base - real).sum())
        perdida += fuerza_prior * referencia * abs(float(escala) - 1.0)
        perdidas.append((perdida, float(escala)))
    return min(perdidas)[1]


def _ajustes(
    entrenamiento: pd.DataFrame,
    fundo: str,
    configuracion: Configuracion,
) -> tuple[float, float, int]:
    global_gamma = _minimizar_absoluto(
        entrenamiento.real_kg.to_numpy(float),
        entrenamiento.macro_kg.to_numpy(float),
        entrenamiento.lagged_kg.to_numpy(float),
        prior=configuracion.gamma_prior,
        fuerza_prior=configuracion.fuerza_prior,
    )
    local = entrenamiento.loc[entrenamiento.fundo_operativo.eq(fundo)]
    local_gamma = _minimizar_absoluto(
        local.real_kg.to_numpy(float),
        local.macro_kg.to_numpy(float),
        local.lagged_kg.to_numpy(float),
        prior=global_gamma,
        fuerza_prior=configuracion.fuerza_prior,
    )
    n_local = int(len(local))
    peso_local = n_local / (n_local + configuracion.shrink_fundo)
    gamma = peso_local * local_gamma + (1.0 - peso_local) * global_gamma

    if not configuracion.usar_escala:
        return float(gamma), 1.0, n_local
    base_global = entrenamiento.macro_kg.to_numpy(float) + global_gamma * (
        entrenamiento.lagged_kg.to_numpy(float) - entrenamiento.macro_kg.to_numpy(float)
    )
    escala_global = _minimizar_escala(
        entrenamiento.real_kg.to_numpy(float),
        base_global,
        fuerza_prior=configuracion.fuerza_prior,
    )
    base_local = local.macro_kg.to_numpy(float) + gamma * (
        local.lagged_kg.to_numpy(float) - local.macro_kg.to_numpy(float)
    )
    escala_local = _minimizar_escala(
        local.real_kg.to_numpy(float),
        base_local,
        fuerza_prior=configuracion.fuerza_prior,
    )
    escala = peso_local * escala_local + (1.0 - peso_local) * escala_global
    return float(gamma), float(escala), n_local


def _predecir_online(tabla: pd.DataFrame, configuracion: Configuracion) -> pd.DataFrame:
    salida = tabla.copy().sort_values(["semana_objetivo", "fundo_operativo"], kind="stable")
    salida["candidate_kg"] = salida.macro_kg
    salida["gamma"] = 0.0
    salida["escala"] = 1.0
    salida["n_historia_fundo"] = 0
    salida["ruta"] = "macro_sin_parametros"
    semanas = sorted(map(int, salida.semana_objetivo.unique()))
    for semana in semanas:
        entrenamiento = salida.loc[
            salida.semana_objetivo.lt(semana) & salida.lagged_disponible
        ].copy()
        objetivo = salida.semana_objetivo.eq(semana) & salida.lagged_disponible
        for indice in salida.index[objetivo]:
            gamma, escala, n_local = _ajustes(
                entrenamiento,
                str(salida.at[indice, "fundo_operativo"]),
                configuracion,
            )
            base = float(salida.at[indice, "macro_kg"]) + gamma * (
                float(salida.at[indice, "lagged_kg"])
                - float(salida.at[indice, "macro_kg"])
            )
            salida.at[indice, "candidate_kg"] = max(0.0, escala * base)
            salida.at[indice, "gamma"] = gamma
            salida.at[indice, "escala"] = escala
            salida.at[indice, "n_historia_fundo"] = n_local
            salida.at[indice, "ruta"] = "ajuste_experto_regularizado"
    return salida


def _metricas(
    tabla: pd.DataFrame, columna: str, grano: tuple[str, ...]
) -> dict[str, float | int]:
    bloque = tabla.groupby(list(grano), as_index=False).agg(
        real_kg=("real_kg", "sum"), pred_kg=(columna, "sum")
    )
    error = bloque.pred_kg - bloque.real_kg
    denominador = float(bloque.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador) if denominador else 0.0,
        "sesgo": float(error.sum() / denominador) if denominador else 0.0,
        "mae_kg": float(error.abs().mean()) if len(bloque) else 0.0,
        "n": int(len(bloque)),
    }


def _keyset_sha256(tabla: pd.DataFrame) -> str:
    columnas = ["campania", "semana_emision", "semana_objetivo", "fundo_operativo"]
    texto = (
        tabla[columnas]
        .sort_values(columnas, kind="stable")
        .astype(str)
        .agg("|".join, axis=1)
        .str.cat(sep="\n")
    )
    return hashlib.sha256(texto.encode()).hexdigest()


def _cargar_contrato(panel: Path, access: Path, campania: str) -> pd.DataFrame:
    macro = leer_macro_h1(campania)
    reales, r09 = leer_reales_r09_fundo(access, campania)
    lagged = pd.read_parquet(panel)
    lagged["fundo_operativo"] = lagged.fundo_operativo.map(normalizar_fundo)
    columnas_lagged = [
        "semana_emision",
        "semana_objetivo",
        "fundo_operativo",
        "lagged_kg",
        "archivo_fuente",
        "sha256_fuente",
    ]
    tabla = macro.merge(
        lagged[columnas_lagged],
        on=["semana_emision", "semana_objetivo", "fundo_operativo"],
        how="left",
        validate="one_to_one",
    )
    tabla = tabla.merge(
        reales,
        on=["semana_objetivo", "fundo_operativo"],
        how="left",
        validate="many_to_one",
    )
    tabla = tabla.merge(
        r09,
        on=["semana_emision", "semana_objetivo", "fundo_operativo"],
        how="left",
        validate="one_to_one",
    )
    tabla = tabla.loc[
        tabla.fecha_objetivo.add(pd.Timedelta(days=6)).le(pd.Timestamp("2026-08-16"))
    ].copy()
    tabla["real_kg"] = tabla.real_kg.fillna(0.0)
    tabla["lagged_disponible"] = tabla.lagged_kg.notna()
    tabla["r09_disponible"] = tabla.r09_kg.notna()
    tabla["r09_kg"] = tabla.r09_kg.fillna(0.0)
    tabla["lagged_kg"] = tabla.lagged_kg.fillna(tabla.macro_kg)
    return tabla


def ejecutar(
    *,
    panel: Path = PANEL_DEFAULT,
    access: Path = ACCESS_DEFAULT,
    campania: str = "C2026",
) -> dict[str, object]:
    contrato = _cargar_contrato(panel, access, campania)
    configuraciones = [
        Configuracion(gamma_prior=g, fuerza_prior=p, shrink_fundo=k, usar_escala=s)
        for g in (0.0, 0.25, 0.50)
        for p in (2.0, 6.0, 12.0)
        for k in (4.0, 8.0, 16.0)
        for s in (False, True)
    ]
    filas = []
    predicciones: dict[str, pd.DataFrame] = {}
    desarrollo = contrato.semana_objetivo.le(30)
    for configuracion in configuraciones:
        pred = _predecir_online(contrato, configuracion)
        predicciones[configuracion.id] = pred
        met = _metricas(
            pred.loc[desarrollo], "candidate_kg", ("semana_objetivo", "fundo_operativo")
        )
        filas.append({"configuracion_id": configuracion.id, **met})
    ranking = pd.DataFrame(filas)
    ranking = ranking.loc[ranking.sesgo.abs().le(0.15)].sort_values(
        ["wape", "sesgo"], kind="stable"
    )
    if ranking.empty:
        raise RuntimeError("Ninguna configuración superó el preflight de sesgo")
    ganador = str(ranking.iloc[0].configuracion_id)
    final = predicciones[ganador]
    periodos = {
        "desarrollo_hasta_s30": final.semana_objetivo.le(30),
        "holdout_s31_s33": final.semana_objetivo.ge(31),
        "contrato_completo": pd.Series(True, index=final.index),
    }
    metricas: dict[str, object] = {}
    for etiqueta, mascara in periodos.items():
        bloque = final.loc[mascara]
        metricas[etiqueta] = {
            "empresa_semana": {
                serie: _metricas(bloque, columna, ("semana_objetivo",))
                for serie, columna in (
                    ("candidato", "candidate_kg"),
                    ("macro", "macro_kg"),
                    ("r09_operacional", "r09_kg"),
                )
            },
            "fundo_semana": {
                serie: _metricas(
                    bloque, columna, ("semana_objetivo", "fundo_operativo")
                )
                for serie, columna in (
                    ("candidato", "candidate_kg"),
                    ("macro", "macro_kg"),
                    ("r09_operacional", "r09_kg"),
                )
            },
        }
    por_fundo = {
        str(fundo): {
            serie: _metricas(grupo, columna, ("semana_objetivo", "fundo_operativo"))
            for serie, columna in (
                ("candidato", "candidate_kg"),
                ("macro", "macro_kg"),
                ("r09_operacional", "r09_kg"),
            )
        }
        for fundo, grupo in final.groupby("fundo_operativo")
    }
    return {
        "schema": "screening-expert-adjustment-online-v1",
        "campania": campania,
        "ganador_micro_replay": ganador,
        "seleccion": "solo desarrollo <= S30; S31-S33 holdout",
        "evaluation_contract": {
            "keyset_sha256": _keyset_sha256(final),
            "n_filas": int(len(final)),
            "n_semanas": int(final.semana_objetivo.nunique()),
            "real_kg": float(final.real_kg.sum()),
            "ultima_semana_cerrada": 33,
        },
        "metricas": metricas,
        "por_fundo": por_fundo,
        "ranking_desarrollo": ranking.head(10).to_dict("records"),
        "detalle": final.to_dict("records"),
        "usa_r09_como_predictor": False,
        "publicable": False,
    }


# Nombres públicos y privados preservados para las fachadas históricas.
predecir_online = _predecir_online
metricas = _metricas
cargar_contrato = _cargar_contrato

__all__ = [
    "ACCESS_DEFAULT",
    "Configuracion",
    "PANEL_DEFAULT",
    "cargar_contrato",
    "ejecutar",
    "metricas",
    "predecir_online",
]
