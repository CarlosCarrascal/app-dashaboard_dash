"""Servicios estables para los micro-replays de estado experto.

Este módulo concentra, sin cambiar la lógica, los dos candidatos históricos
que antes vivían en scripts: el override experto y la corrección residual
online. Las observaciones R09 se usan únicamente después de producir la
predicción de su propia semana; por eso nunca son un predictor contemporáneo.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.servicios.expertos import (
    ACCESS_DEFAULT,
    PANEL_DEFAULT,
    cargar_contrato,
    metricas,
)


@dataclass(frozen=True)
class ConfiguracionOverride:
    """Parámetros del ajuste de estado experto y real."""

    alpha_experto: float
    alpha_real: float
    peso_experto: float
    shrink_fundo: float
    clip_log: float

    @property
    def id(self) -> str:
        return (
            f"ae{self.alpha_experto:.2f}-ar{self.alpha_real:.2f}-"
            f"we{self.peso_experto:.2f}-k{self.shrink_fundo:.1f}-c{self.clip_log:.2f}"
        )


@dataclass(frozen=True)
class ConfiguracionResidual:
    """Parámetros de la corrección residual multiplicativa online."""

    peso_experto: float
    alpha_global: float
    alpha_fundo: float
    shrink_fundo: float
    clip_log: float

    @property
    def id(self) -> str:
        return (
            f"e{self.peso_experto:.2f}-ag{self.alpha_global:.2f}-"
            f"af{self.alpha_fundo:.2f}-k{self.shrink_fundo:.1f}-c{self.clip_log:.2f}"
        )


def _metricas_semana_override(
    tabla: pd.DataFrame, columna: str
) -> dict[str, float | int]:
    return metricas(tabla, columna, ("semana_objetivo",))


def _actualizar_override(previo: float, observacion: float, alpha: float) -> float:
    return float((1.0 - alpha) * previo + alpha * observacion)


def predecir_override(tabla: pd.DataFrame, cfg: ConfiguracionOverride) -> pd.DataFrame:
    salida = tabla.copy().sort_values(["semana_objetivo", "fundo_operativo"], kind="stable")
    salida["candidate_kg"] = salida.macro_kg
    salida["ajuste_experto_log"] = 0.0
    salida["ajuste_real_log"] = 0.0
    salida["correccion_log"] = 0.0
    exp_global = 0.0
    real_global = 0.0
    exp_fundo: dict[str, float] = {}
    real_fundo: dict[str, float] = {}
    n_exp: dict[str, int] = {}
    n_real: dict[str, int] = {}
    eps = 1_000.0
    for semana in sorted(map(int, salida.semana_objetivo.unique())):
        indices = salida.index[salida.semana_objetivo.eq(semana)]
        for indice in indices:
            fundo = str(salida.at[indice, "fundo_operativo"])
            ne = n_exp.get(fundo, 0)
            nr = n_real.get(fundo, 0)
            pe = ne / (ne + cfg.shrink_fundo)
            pr = nr / (nr + cfg.shrink_fundo)
            experto = pe * exp_fundo.get(fundo, exp_global) + (1.0 - pe) * exp_global
            real = pr * real_fundo.get(fundo, real_global) + (1.0 - pr) * real_global
            correccion = cfg.peso_experto * experto + (1.0 - cfg.peso_experto) * real
            correccion = float(np.clip(correccion, -cfg.clip_log, cfg.clip_log))
            salida.at[indice, "candidate_kg"] = max(
                0.0, float(salida.at[indice, "macro_kg"]) * float(np.exp(correccion))
            )
            salida.at[indice, "ajuste_experto_log"] = experto
            salida.at[indice, "ajuste_real_log"] = real
            salida.at[indice, "correccion_log"] = correccion

        bloque = salida.loc[indices]
        macro_total = float(bloque.macro_kg.sum())
        real_total = float(bloque.real_kg.sum())
        obs_real_g = float(np.log((real_total + eps) / (macro_total + eps)))
        obs_real_g = float(np.clip(obs_real_g, -cfg.clip_log, cfg.clip_log))
        real_global = _actualizar_override(real_global, obs_real_g, cfg.alpha_real)
        r09_bloque = bloque.loc[bloque.r09_disponible]
        if len(r09_bloque):
            macro_r09 = float(r09_bloque.macro_kg.sum())
            r09_total = float(r09_bloque.r09_kg.sum())
            obs_exp_g = float(np.log((r09_total + eps) / (macro_r09 + eps)))
            obs_exp_g = float(np.clip(obs_exp_g, -cfg.clip_log, cfg.clip_log))
            exp_global = _actualizar_override(exp_global, obs_exp_g, cfg.alpha_experto)

        for fundo, grupo in bloque.groupby("fundo_operativo"):
            f = str(fundo)
            macro = float(grupo.macro_kg.sum())
            real = float(grupo.real_kg.sum())
            obs_real = float(np.log((real + eps) / (macro + eps)))
            obs_real = float(np.clip(obs_real, -cfg.clip_log, cfg.clip_log))
            real_fundo[f] = _actualizar_override(
                real_fundo.get(f, real_global), obs_real, cfg.alpha_real
            )
            n_real[f] = n_real.get(f, 0) + 1
            disponible = grupo.loc[grupo.r09_disponible]
            if len(disponible):
                r09 = float(disponible.r09_kg.sum())
                macro_d = float(disponible.macro_kg.sum())
                obs_exp = float(np.log((r09 + eps) / (macro_d + eps)))
                obs_exp = float(np.clip(obs_exp, -cfg.clip_log, cfg.clip_log))
                exp_fundo[f] = _actualizar_override(
                    exp_fundo.get(f, exp_global), obs_exp, cfg.alpha_experto
                )
                n_exp[f] = n_exp.get(f, 0) + 1
    return salida


def _keyset_override(tabla: pd.DataFrame) -> str:
    columnas = ["campania", "semana_emision", "semana_objetivo", "fundo_operativo"]
    texto = (
        tabla[columnas].sort_values(columnas).astype(str).agg("|".join, axis=1).str.cat(sep="\n")
    )
    return hashlib.sha256(texto.encode()).hexdigest()


def ejecutar_override(
    *,
    panel: Path = PANEL_DEFAULT,
    access: Path = ACCESS_DEFAULT,
    campania: str = "C2026",
) -> dict[str, object]:
    contrato = cargar_contrato(panel, access, campania)
    configuraciones = [
        ConfiguracionOverride(ae, ar, we, k, c)
        for ae in (0.10, 0.25, 0.40, 0.60)
        for ar in (0.10, 0.25, 0.40, 0.60)
        for we in (0.25, 0.50, 0.75, 1.0)
        for k in (4.0, 8.0, 16.0)
        for c in (0.25, 0.40, 0.60)
    ]
    desarrollo = contrato.semana_objetivo.le(30)
    ranking = []
    predicciones: dict[str, pd.DataFrame] = {}
    for cfg in configuraciones:
        pred = predecir_override(contrato, cfg)
        predicciones[cfg.id] = pred
        ranking.append(
            {
                "configuracion_id": cfg.id,
                **_metricas_semana_override(pred.loc[desarrollo], "candidate_kg"),
            }
        )
    orden = pd.DataFrame(ranking)
    orden = orden.loc[orden.sesgo.abs().le(0.15)].sort_values(["wape", "sesgo"], kind="stable")
    if orden.empty:
        raise RuntimeError("Ninguna configuracion paso el preflight")
    ganador = str(orden.iloc[0].configuracion_id)
    final = predicciones[ganador]
    periodos = {
        "desarrollo_hasta_s30": final.semana_objetivo.le(30),
        "holdout_s31_s33": final.semana_objetivo.ge(31),
        "contrato_completo": pd.Series(True, index=final.index),
    }
    metricas_resultado = {}
    for etiqueta, mascara in periodos.items():
        bloque = final.loc[mascara]
        r09 = bloque.loc[bloque.r09_disponible]
        metricas_resultado[etiqueta] = {
            "candidato": _metricas_semana_override(bloque, "candidate_kg"),
            "macro": _metricas_semana_override(bloque, "macro_kg"),
            "r09_condicionado": (
                _metricas_semana_override(r09, "r09_kg") if len(r09) else None
            ),
        }
    return {
        "schema": "screening-expert-override-state-v1",
        "campania": campania,
        "ganador_micro_replay": ganador,
        "seleccion": "solo desarrollo <= S30; S31-S33 holdout",
        "evaluation_contract": {
            "keyset_sha256": _keyset_override(final),
            "n_filas": int(len(final)),
            "n_semanas": int(final.semana_objetivo.nunique()),
            "real_kg": float(final.real_kg.sum()),
            "ultima_semana_cerrada": 33,
        },
        "metricas": metricas_resultado,
        "ranking_desarrollo": orden.head(20).to_dict("records"),
        "detalle": final.to_dict("records"),
        "usa_r09_actual_como_predictor": False,
        "usa_ajustes_r09_historicos": True,
        "publicable": False,
    }


def _keyset_residual(tabla: pd.DataFrame) -> str:
    columnas = ["campania", "semana_emision", "semana_objetivo", "fundo_operativo"]
    texto = (
        tabla[columnas]
        .sort_values(columnas, kind="stable")
        .astype(str)
        .agg("|".join, axis=1)
        .str.cat(sep="\n")
    )
    return hashlib.sha256(texto.encode()).hexdigest()


def _base_residual(tabla: pd.DataFrame, peso_experto: float) -> pd.Series:
    experto = tabla.lagged_kg.where(tabla.lagged_disponible, tabla.macro_kg)
    return tabla.macro_kg + float(peso_experto) * (experto - tabla.macro_kg)


def _actualizar_residual(estado: float, observacion: float, alpha: float) -> float:
    return float((1.0 - alpha) * estado + alpha * observacion)


def predecir_residual_online(tabla: pd.DataFrame, cfg: ConfiguracionResidual) -> pd.DataFrame:
    salida = tabla.copy().sort_values(["semana_objetivo", "fundo_operativo"], kind="stable")
    salida["base_kg"] = _base_residual(salida, cfg.peso_experto).clip(lower=0.0)
    salida["candidate_kg"] = salida.base_kg
    salida["estado_global_log"] = 0.0
    salida["estado_fundo_log"] = 0.0
    salida["n_historia_global"] = 0
    salida["n_historia_fundo"] = 0

    estado_global = 0.0
    estados_fundo: dict[str, float] = {}
    n_global = 0
    n_fundo: dict[str, int] = {}
    epsilon = 1_000.0

    for n_global, semana in enumerate(sorted(map(int, salida.semana_objetivo.unique()))):
        indices = salida.index[salida.semana_objetivo.eq(semana)]
        # Todas las predicciones de una misma semana ven exactamente el mismo
        # estado; las observaciones de esa semana se incorporan solo despues.
        for indice in indices:
            fundo = str(salida.at[indice, "fundo_operativo"])
            local = estados_fundo.get(fundo, estado_global)
            n_local = n_fundo.get(fundo, 0)
            peso_local = n_local / (n_local + cfg.shrink_fundo)
            estado = peso_local * local + (1.0 - peso_local) * estado_global
            estado = float(np.clip(estado, -cfg.clip_log, cfg.clip_log))
            salida.at[indice, "candidate_kg"] = max(
                0.0, float(salida.at[indice, "base_kg"]) * float(np.exp(estado))
            )
            salida.at[indice, "estado_global_log"] = estado_global
            salida.at[indice, "estado_fundo_log"] = estado
            salida.at[indice, "n_historia_global"] = n_global
            salida.at[indice, "n_historia_fundo"] = n_local

        # Cierre de la semana: recien aqui se observan los kilos reales.
        bloque = salida.loc[indices]
        real_total = float(bloque.real_kg.sum())
        base_total = float(bloque.base_kg.sum())
        obs_global = float(np.log((real_total + epsilon) / (base_total + epsilon)))
        obs_global = float(np.clip(obs_global, -cfg.clip_log, cfg.clip_log))
        estado_global = _actualizar_residual(estado_global, obs_global, cfg.alpha_global)
        for fundo, grupo in bloque.groupby("fundo_operativo"):
            real = float(grupo.real_kg.sum())
            base = float(grupo.base_kg.sum())
            observacion = float(np.log((real + epsilon) / (base + epsilon)))
            observacion = float(np.clip(observacion, -cfg.clip_log, cfg.clip_log))
            previo = estados_fundo.get(str(fundo), estado_global)
            estados_fundo[str(fundo)] = _actualizar_residual(
                previo, observacion, cfg.alpha_fundo
            )
            n_fundo[str(fundo)] = n_fundo.get(str(fundo), 0) + 1
    return salida


def _resumen_residual(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    return metricas(tabla, columna, ("semana_objetivo",))


def _por_fundo_residual(
    tabla: pd.DataFrame, columna: str
) -> dict[str, dict[str, float | int]]:
    return {
        str(fundo): metricas(grupo, columna, ("semana_objetivo", "fundo_operativo"))
        for fundo, grupo in tabla.groupby("fundo_operativo")
    }


def ejecutar_residual(
    *,
    panel: Path = PANEL_DEFAULT,
    access: Path = ACCESS_DEFAULT,
    campania: str = "C2026",
) -> dict[str, object]:
    contrato = cargar_contrato(panel, access, campania)
    configuraciones = [
        ConfiguracionResidual(e, ag, af, k, c)
        for e in (0.0, 0.15, 0.30)
        for ag in (0.10, 0.25, 0.40, 0.60)
        for af in (0.10, 0.25, 0.40, 0.60)
        for k in (4.0, 8.0, 16.0)
        for c in (0.25, 0.40, 0.60)
    ]
    desarrollo = contrato.semana_objetivo.le(30)
    resultados = []
    predicciones: dict[str, pd.DataFrame] = {}
    for cfg in configuraciones:
        pred = predecir_residual_online(contrato, cfg)
        predicciones[cfg.id] = pred
        met = _resumen_residual(pred.loc[desarrollo], "candidate_kg")
        resultados.append({"configuracion_id": cfg.id, **met})
    ranking = pd.DataFrame(resultados)
    ranking = ranking.loc[ranking.sesgo.abs().le(0.15)].sort_values(
        ["wape", "sesgo"], kind="stable"
    )
    if ranking.empty:
        raise RuntimeError("Ninguna configuracion paso el preflight de sesgo")
    ganador = str(ranking.iloc[0].configuracion_id)
    final = predicciones[ganador]
    periodos = {
        "desarrollo_hasta_s30": final.semana_objetivo.le(30),
        "holdout_s31_s33": final.semana_objetivo.ge(31),
        "contrato_completo": pd.Series(True, index=final.index),
    }
    metricas_resultado = {}
    for etiqueta, mascara in periodos.items():
        bloque = final.loc[mascara]
        r09_disponible = bloque.loc[bloque.r09_disponible]
        metricas_resultado[etiqueta] = {
            "candidato": _resumen_residual(bloque, "candidate_kg"),
            "macro": _resumen_residual(bloque, "macro_kg"),
            "r09_operacional": _resumen_residual(bloque, "r09_kg"),
            "r09_condicionado": (
                _resumen_residual(r09_disponible, "r09_kg") if len(r09_disponible) else None
            ),
            "por_fundo_candidato": _por_fundo_residual(bloque, "candidate_kg"),
            "por_fundo_macro": _por_fundo_residual(bloque, "macro_kg"),
        }
    return {
        "schema": "screening-residual-state-online-v1",
        "campania": campania,
        "ganador_micro_replay": ganador,
        "seleccion": "solo desarrollo <= S30; S31-S33 holdout",
        "evaluation_contract": {
            "keyset_sha256": _keyset_residual(final),
            "n_filas": int(len(final)),
            "n_semanas": int(final.semana_objetivo.nunique()),
            "real_kg": float(final.real_kg.sum()),
            "ultima_semana_cerrada": 33,
        },
        "metricas": metricas_resultado,
        "ranking_desarrollo": ranking.head(20).to_dict("records"),
        "detalle": final.to_dict("records"),
        "usa_r09_como_predictor": False,
        "publicable": False,
    }


__all__ = [
    "ACCESS_DEFAULT",
    "ConfiguracionOverride",
    "ConfiguracionResidual",
    "PANEL_DEFAULT",
    "cargar_contrato",
    "ejecutar_override",
    "ejecutar_residual",
    "metricas",
    "predecir_override",
    "predecir_residual_online",
]
