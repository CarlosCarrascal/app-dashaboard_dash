"""Servicio único para el screening de desplazamiento temporal online.

La implementación conserva el contrato histórico de
``screening_temporal_shift_online``: MacroLegacy emite simultáneamente h1, h2
y h3, la selección usa únicamente semanas cerradas y R09 se reporta como
referencia operacional, nunca como predictor.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.procesos.candidatos import (
    escribir_json_reproducible as _escribir_json_reproducible,
)
from analitica.aplicacion.servicios.parametros_nowcast import (
    ACCESS_DEFAULT,
    leer_reales_r09_fundo,
)
from analitica.aplicacion.servicios.router_horizonte import agregar, leer

escribir_json_reproducible = _escribir_json_reproducible


@dataclass(frozen=True)
class Configuracion:
    lookback: int
    min_historia: int
    half_life: float
    penalizacion_shift: float
    penalizacion_escala: float

    @property
    def id(self) -> str:
        return (
            f"l{self.lookback}-m{self.min_historia}-h{self.half_life:.1f}-"
            f"pd{self.penalizacion_shift:.2f}-ps{self.penalizacion_escala:.2f}"
        )


def _metricas(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    error = tabla[columna] - tabla.real_kg
    denominador = float(tabla.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador) if denominador else np.nan,
        "sesgo": float(error.sum() / denominador) if denominador else np.nan,
        "mae_kg": float(error.abs().mean()) if len(tabla) else np.nan,
        "n": int(len(tabla)),
    }


def _keyset_sha256(tabla: pd.DataFrame) -> str:
    columnas = ["campania", "fecha_emision", "fecha_objetivo", "semana_objetivo"]
    texto = (
        tabla[columnas]
        .sort_values(columnas, kind="stable")
        .astype(str)
        .agg("|".join, axis=1)
        .str.cat(sep="\n")
    )
    return hashlib.sha256(texto.encode()).hexdigest()


def _cargar_contrato(access: Path, campania: str) -> pd.DataFrame:
    h1 = agregar(leer(76, campania, "MacroLegacy_v1", (1,)), "macro_h1").drop(
        columns="real_kg"
    )
    largos = agregar(leer(73, campania, "MacroLegacy_v1", (2, 3)), "macro_largo").drop(
        columns="real_kg"
    )
    h2 = largos.loc[largos.horizonte_semanas.eq(2), ["fecha_emision", "macro_largo"]].rename(
        columns={"macro_largo": "macro_h2"}
    )
    h3 = largos.loc[largos.horizonte_semanas.eq(3), ["fecha_emision", "macro_largo"]].rename(
        columns={"macro_largo": "macro_h3"}
    )
    tabla = h1.merge(h2, on="fecha_emision", how="left", validate="one_to_one")
    tabla = tabla.merge(h3, on="fecha_emision", how="left", validate="one_to_one")
    reales_fundo, r09_fundo = leer_reales_r09_fundo(access, campania)
    reales = reales_fundo.groupby("semana_objetivo", as_index=False).real_kg.sum()
    r09 = r09_fundo.groupby(["semana_emision", "semana_objetivo"], as_index=False).r09_kg.sum()
    tabla["semana_emision"] = tabla.fecha_emision.dt.isocalendar().week.astype(int)
    tabla["semana_objetivo"] = tabla.fecha_objetivo.dt.isocalendar().week.astype(int)
    tabla = tabla.merge(reales, on="semana_objetivo", how="left", validate="many_to_one")
    tabla = tabla.merge(
        r09,
        on=["semana_emision", "semana_objetivo"],
        how="left",
        validate="one_to_one",
    )
    tabla = tabla.loc[
        tabla.fecha_objetivo.add(pd.Timedelta(days=6)).le(pd.Timestamp("2026-08-16"))
    ].copy()
    tabla["real_kg"] = tabla.real_kg.fillna(0.0)
    tabla["r09_disponible"] = tabla.r09_kg.notna()
    tabla["r09_kg"] = tabla.r09_kg.fillna(0.0)
    return tabla.sort_values("semana_objetivo", kind="stable").reset_index(drop=True)


def _ponderaciones(n: int, half_life: float) -> np.ndarray:
    edad = np.arange(n - 1, -1, -1, dtype=float)
    if half_life <= 0:
        return np.ones(n, dtype=float)
    return np.power(0.5, edad / half_life)


def _elegir(historia: pd.DataFrame, cfg: Configuracion) -> tuple[int, float]:
    if len(historia) < cfg.min_historia:
        return 0, 1.0
    h = historia.tail(cfg.lookback) if cfg.lookback > 0 else historia
    pesos = _ponderaciones(len(h), cfg.half_life)
    escala_real = max(float(np.average(np.abs(h.real_kg), weights=pesos)), 1.0)
    candidatos: list[tuple[float, int, float]] = []
    for shift, columna in ((0, "macro_h1"), (1, "macro_h2"), (2, "macro_h3")):
        valido = h[columna].notna()
        if int(valido.sum()) < cfg.min_historia:
            continue
        hv = h.loc[valido]
        pv = pesos[valido.to_numpy()]
        for escala in np.linspace(0.70, 1.30, 61):
            error = np.abs(escala * hv[columna].to_numpy(float) - hv.real_kg.to_numpy(float))
            perdida = float(np.average(error, weights=pv))
            perdida += cfg.penalizacion_shift * escala_real * shift
            perdida += cfg.penalizacion_escala * escala_real * abs(float(escala) - 1.0)
            candidatos.append((perdida, shift, float(escala)))
    if not candidatos:
        return 0, 1.0
    _, shift, escala = min(candidatos)
    return int(shift), float(escala)


def _predecir_online(tabla: pd.DataFrame, cfg: Configuracion) -> pd.DataFrame:
    salida = tabla.copy()
    salida["candidate_kg"] = salida.macro_h1
    salida["shift"] = 0
    salida["escala"] = 1.0
    salida["n_historia"] = 0
    columnas = {0: "macro_h1", 1: "macro_h2", 2: "macro_h3"}
    for indice, fila in salida.iterrows():
        historia = salida.iloc[:indice].copy()
        shift, escala = _elegir(historia, cfg)
        columna = columnas[shift]
        valor = fila[columna]
        if pd.isna(valor):
            shift, escala, columna, valor = 0, 1.0, "macro_h1", fila.macro_h1
        salida.at[indice, "candidate_kg"] = max(0.0, escala * float(valor))
        salida.at[indice, "shift"] = shift
        salida.at[indice, "escala"] = escala
        salida.at[indice, "n_historia"] = len(historia)
    return salida


def ejecutar(*, access: Path = ACCESS_DEFAULT, campania: str = "C2026") -> dict[str, object]:
    contrato = _cargar_contrato(access, campania)
    configuraciones = [
        Configuracion(lookback, m, h, pd_, ps)
        for lookback in (4, 6, 8, 12, 0)
        for m in (4, 6)
        for h in (2.0, 4.0, 8.0)
        for pd_ in (0.0, 0.02, 0.05)
        for ps in (0.0, 0.02, 0.05)
    ]
    desarrollo = contrato.semana_objetivo.le(30)
    ranking = []
    predicciones: dict[str, pd.DataFrame] = {}
    for cfg in configuraciones:
        pred = _predecir_online(contrato, cfg)
        predicciones[cfg.id] = pred
        ranking.append(
            {"configuracion_id": cfg.id, **_metricas(pred.loc[desarrollo], "candidate_kg")}
        )
    orden = pd.DataFrame(ranking)
    orden = orden.loc[orden.sesgo.abs().le(0.15)].sort_values(["wape", "sesgo"], kind="stable")
    if orden.empty:
        raise RuntimeError("Ninguna configuracion paso el preflight de sesgo")
    ganador = str(orden.iloc[0].configuracion_id)
    final = predicciones[ganador]
    periodos = {
        "desarrollo_hasta_s30": final.semana_objetivo.le(30),
        "holdout_s31_s33": final.semana_objetivo.ge(31),
        "contrato_completo": pd.Series(True, index=final.index),
    }
    metricas = {}
    for etiqueta, mascara in periodos.items():
        bloque = final.loc[mascara]
        r09_valido = bloque.loc[bloque.r09_disponible]
        metricas[etiqueta] = {
            "candidato": _metricas(bloque, "candidate_kg"),
            "macro": _metricas(bloque, "macro_h1"),
            "r09_operacional": _metricas(bloque, "r09_kg"),
            "r09_condicionado": _metricas(r09_valido, "r09_kg") if len(r09_valido) else None,
            "shifts": {str(int(k)): int(v) for k, v in bloque.groupby("shift").size().items()},
        }
    return {
        "schema": "screening-temporal-shift-online-v1",
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
        "ranking_desarrollo": orden.head(20).to_dict("records"),
        "detalle": final.to_dict("records"),
        "usa_r09_como_predictor": False,
        "publicable": False,
    }
