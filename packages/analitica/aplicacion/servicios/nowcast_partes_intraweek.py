"""Flujo intraweek histórico del servicio de nowcast."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from analitica import settings
from analitica.aplicacion.servicios.nowcast_partes_base import (
    ACCESS_DEFAULT,
    R09_ACCESS_DEFAULT,
    leer_diario,
)
from analitica.aplicacion.servicios.parametros_nowcast import leer_macro_h1, leer_reales_r09_fundo


@dataclass(frozen=True)
class Configuracion:
    lookback: int
    shrink_fundo: float
    peso_ritmo: float
    piso_share: float
    techo_share: float

    @property
    def id(self) -> str:
        return (
            f"l{self.lookback}-k{self.shrink_fundo:.1f}-w{self.peso_ritmo:.2f}-"
            f"p{self.piso_share:.2f}-t{self.techo_share:.2f}"
        )


def _metricas_intraweek(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    error = tabla[columna] - tabla.real_kg
    denominador = float(tabla.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador) if denominador else np.nan,
        "sesgo": float(error.sum() / denominador) if denominador else np.nan,
        "mae_kg": float(error.abs().mean()) if len(tabla) else np.nan,
        "n": int(len(tabla)),
    }


def _comparacion_pareada(
    tabla: pd.DataFrame,
    referencia: str,
    *,
    repeticiones: int = 5_000,
) -> dict[str, object] | None:
    bloque = tabla.loc[tabla[referencia].notna()].copy()
    if bloque.empty:
        return None
    candidato = _metricas_intraweek(bloque, "candidate_kg")
    ref = _metricas_intraweek(bloque, referencia)
    error_c = (bloque.candidate_kg - bloque.real_kg).abs().to_numpy(float)
    error_r = (bloque[referencia] - bloque.real_kg).abs().to_numpy(float)
    denominador = bloque.real_kg.abs().to_numpy(float)
    rng = np.random.default_rng(20260825)
    diferencias = []
    for _ in range(repeticiones):
        indices = rng.integers(0, len(bloque), len(bloque))
        den = float(denominador[indices].sum())
        if den:
            diferencias.append(float((error_c[indices].sum() - error_r[indices].sum()) / den))
    intervalo = np.quantile(diferencias, [0.025, 0.975]) if diferencias else [np.nan, np.nan]
    return {
        "n_semanas_comunes": int(len(bloque)),
        "candidato": candidato,
        "referencia": ref,
        "diferencia_wape_pp": float(100.0 * (candidato["wape"] - ref["wape"])),
        "semanas_ganadas": int((error_c < error_r).sum()),
        "empates": int(np.isclose(error_c, error_r).sum()),
        "bootstrap_diferencia_wape_pp_ic95": [
            float(100.0 * intervalo[0]),
            float(100.0 * intervalo[1]),
        ],
    }


def _keyset(tabla: pd.DataFrame) -> str:
    texto = (
        tabla[["campania", "semana_objetivo"]]
        .astype(str)
        .agg("|".join, axis=1)
        .str.cat(sep="\n")
    )
    return hashlib.sha256(texto.encode()).hexdigest()


def _leer_macro_s34_run73(campania: str) -> float | None:
    """Lee el h1 S33->S34 sin aplicar el cierre certificado S33 del router."""
    dsn = settings.postgres_dsn()
    if not dsn:
        return None
    with psycopg.connect(dsn) as conexion:
        fila = conexion.execute(
            """
            SELECT SUM(p50_kg)
            FROM analytics.prediction
            WHERE run_id = 73
              AND campania = %s
              AND modelo = 'MacroLegacy_v1'
              AND horizonte_semanas = 1
              AND fecha_emision = DATE '2026-08-10'
              AND fecha_objetivo = DATE '2026-08-17'
            """,
            (campania,),
        ).fetchone()
    if not fila or fila[0] is None:
        return None
    return float(fila[0])


def _cargar_contrato(
    access: Path,
    r09_access: Path,
    campania: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    macro = (
        leer_macro_h1(campania)
        .groupby(["campania", "semana_emision", "semana_objetivo"], as_index=False)
        .macro_kg.sum()
    )
    diario = leer_diario(access, campania)
    semanal_fundo = diario.groupby(["semana_objetivo", "fundo_operativo"], as_index=False).agg(
        real_kg=("kg", "sum"),
        montue_kg=("kg", lambda x: float(x[diario.loc[x.index, "dia_iso"].le(2)].sum())),
        fecha_max=("fecha", "max"),
    )
    semanal = semanal_fundo.groupby("semana_objetivo", as_index=False).agg(
        real_kg=("real_kg", "sum"),
        montue_kg=("montue_kg", "sum"),
        fecha_max=("fecha_max", "max"),
    )
    _, r09_fundo = leer_reales_r09_fundo(r09_access, campania)
    r09 = r09_fundo.groupby(["semana_emision", "semana_objetivo"], as_index=False).r09_kg.sum()
    previo = r09.rename(columns={"r09_kg": "r09_previo_kg"})
    contemporaneo = r09.copy()
    contemporaneo["semana_emision"] = contemporaneo.semana_emision - 1
    contemporaneo = contemporaneo.rename(columns={"r09_kg": "r09_misma_semana_kg"})
    tabla = macro.merge(semanal, on="semana_objetivo", how="inner", validate="one_to_one")
    tabla = tabla.merge(
        previo,
        on=["semana_emision", "semana_objetivo"],
        how="left",
        validate="one_to_one",
    )
    tabla = tabla.merge(
        contemporaneo,
        on=["semana_emision", "semana_objetivo"],
        how="left",
        validate="one_to_one",
    )
    return (
        tabla.loc[tabla.semana_objetivo.le(33)]
        .sort_values("semana_objetivo")
        .reset_index(drop=True),
        semanal_fundo,
    )


def _predecir(
    tabla: pd.DataFrame,
    semanal_fundo: pd.DataFrame,
    cfg: Configuracion,
) -> pd.DataFrame:
    salida = tabla.copy()
    salida["pace_kg"] = salida.macro_kg
    salida["candidate_kg"] = salida.macro_kg
    salida["share_global"] = np.nan
    salida["n_historia"] = 0
    for indice, fila in salida.iterrows():
        semana = int(fila.semana_objetivo)
        historia = semanal_fundo.loc[semanal_fundo.semana_objetivo.lt(semana)].copy()
        if cfg.lookback > 0:
            semanas = sorted(historia.semana_objetivo.unique())[-cfg.lookback :]
            historia = historia.loc[historia.semana_objetivo.isin(semanas)]
        historia = historia.loc[historia.real_kg.gt(0)].copy()
        historia["share"] = historia.montue_kg / historia.real_kg
        historia = historia.loc[historia.share.between(cfg.piso_share, cfg.techo_share)]
        if historia.empty:
            continue
        global_share = float(np.median(historia.share))
        actual = semanal_fundo.loc[semanal_fundo.semana_objetivo.eq(semana)]
        total_pace = 0.0
        for fondo, grupo in actual.groupby("fundo_operativo"):
            local = historia.loc[historia.fundo_operativo.eq(fondo), "share"]
            local_share = float(np.median(local)) if len(local) else global_share
            peso_local = len(local) / (len(local) + cfg.shrink_fundo)
            share = peso_local * local_share + (1.0 - peso_local) * global_share
            share = float(np.clip(share, cfg.piso_share, cfg.techo_share))
            total_pace += float(grupo.montue_kg.sum()) / share
        salida.at[indice, "pace_kg"] = max(float(fila.montue_kg), total_pace)
        salida.at[indice, "candidate_kg"] = cfg.peso_ritmo * max(
            float(fila.montue_kg), total_pace
        ) + (1.0 - cfg.peso_ritmo) * float(fila.macro_kg)
        salida.at[indice, "share_global"] = global_share
        salida.at[indice, "n_historia"] = int(historia.semana_objetivo.nunique())
    return salida


def _calibrar_residuo_online(
    tabla: pd.DataFrame,
    *,
    lookback: int,
    shrink: float,
) -> pd.DataFrame:
    """Corrige sesgo reciente usando exclusivamente semanas ya cerradas."""
    salida = tabla.copy().sort_values("semana_objetivo", kind="stable").reset_index(drop=True)
    salida["candidate_raw_kg"] = salida.candidate_kg
    salida["escala_residual"] = 1.0
    eps = 1_000.0
    for indice, fila in salida.iterrows():
        historia = salida.iloc[:indice]
        if lookback:
            historia = historia.tail(lookback)
        if historia.empty:
            continue
        razones = (historia.real_kg + eps) / (historia.candidate_raw_kg + eps)
        centro = float(np.median(razones))
        n = len(razones)
        peso = n / (n + shrink)
        escala = float(np.clip(peso * centro + (1.0 - peso), 0.85, 1.20))
        salida.at[indice, "escala_residual"] = escala
        salida.at[indice, "candidate_kg"] = float(fila.candidate_raw_kg) * escala
    return salida


def ejecutar_intraweek(
    *,
    access: Path = ACCESS_DEFAULT,
    r09_access: Path = R09_ACCESS_DEFAULT,
    campania: str = "C2026",
) -> dict[str, object]:
    """Ejecuta el screening intra-semanal sin mezclarlo con el forecast.

    La selección se ajusta únicamente en desarrollo hasta S30. Las semanas
    S31--S33 se reservan para holdout y R09 se incorpora solo como referencia
    de evaluación, nunca como predictor del candidato.
    """
    contrato, semanal_fundo = _cargar_contrato(access, r09_access, campania)
    configuraciones = [
        Configuracion(lookback, k, w, p, t)
        for lookback in (4, 6, 8, 12, 0)
        for k in (2.0, 4.0, 8.0, 16.0)
        for w in (0.50, 0.70, 0.85, 1.0)
        for p, t in ((0.15, 0.60), (0.20, 0.55), (0.20, 0.65))
    ]
    desarrollo = contrato.semana_objetivo.le(30)
    ranking = []
    predicciones: dict[str, pd.DataFrame] = {}
    for cfg in configuraciones:
        pred = _predecir(contrato, semanal_fundo, cfg)
        predicciones[cfg.id] = pred
        ranking.append(
            {
                "configuracion_id": cfg.id,
                **_metricas_intraweek(pred.loc[desarrollo], "candidate_kg"),
            }
        )
    orden = pd.DataFrame(ranking)
    orden = orden.loc[orden.sesgo.abs().le(0.15)].sort_values(["wape", "sesgo"], kind="stable")
    if orden.empty:
        raise RuntimeError("Ninguna configuracion paso el preflight")
    ganador = str(orden.iloc[0].configuracion_id)
    final_raw = predicciones[ganador]
    cfg_ganadora = next(cfg for cfg in configuraciones if cfg.id == ganador)
    calibraciones = [(0, 0.0), (2, 4.0), (2, 8.0), (3, 8.0), (4, 8.0)]
    ranking_calibracion = []
    predicciones_calibradas: dict[str, pd.DataFrame] = {}
    for lookback, shrink in calibraciones:
        etiqueta = "sin_calibracion" if lookback == 0 else f"l{lookback}-k{shrink:.1f}"
        if lookback == 0:
            pred = final_raw.copy()
            pred["candidate_raw_kg"] = pred.candidate_kg
            pred["escala_residual"] = 1.0
        else:
            pred = _calibrar_residuo_online(final_raw, lookback=lookback, shrink=shrink)
        predicciones_calibradas[etiqueta] = pred
        ranking_calibracion.append(
            {
                "calibracion_id": etiqueta,
                **_metricas_intraweek(pred.loc[desarrollo], "candidate_kg"),
            }
        )
    orden_calibracion = pd.DataFrame(ranking_calibracion)
    orden_calibracion = orden_calibracion.loc[orden_calibracion.sesgo.abs().le(0.15)].sort_values(
        ["wape", "sesgo"], kind="stable"
    )
    calibracion_ganadora = str(orden_calibracion.iloc[0].calibracion_id)
    final = predicciones_calibradas[calibracion_ganadora]
    periodos = {
        "desarrollo_hasta_s30": final.semana_objetivo.le(30),
        "holdout_s31_s33": final.semana_objetivo.ge(31),
        "contrato_completo": pd.Series(True, index=final.index),
    }
    metricas = {}
    for etiqueta, mascara in periodos.items():
        bloque = final.loc[mascara]
        metricas[etiqueta] = {
            "nowcast_candidato": _metricas_intraweek(bloque, "candidate_kg"),
            "macro_presemana": _metricas_intraweek(bloque, "macro_kg"),
            "r09_presemana": _metricas_intraweek(
                bloque.loc[bloque.r09_previo_kg.notna()], "r09_previo_kg"
            ),
            "r09_misma_semana": _metricas_intraweek(
                bloque.loc[bloque.r09_misma_semana_kg.notna()], "r09_misma_semana_kg"
            ),
            "pareado_vs_r09_presemana": _comparacion_pareada(bloque, "r09_previo_kg"),
            "pareado_vs_r09_misma_semana": _comparacion_pareada(bloque, "r09_misma_semana_kg"),
        }
    sensibilidad_s34: dict[str, object] | None = None
    macro34_kg = _leer_macro_s34_run73(campania)
    if macro34_kg is not None:
        semanal34 = semanal_fundo.loc[semanal_fundo.semana_objetivo.eq(34)]
        _, r09_fundo = leer_reales_r09_fundo(r09_access, campania)
        r09_previo = float(
            r09_fundo.loc[
                r09_fundo.semana_emision.eq(33) & r09_fundo.semana_objetivo.eq(34),
                "r09_kg",
            ].sum()
        )
        r09_misma = float(
            r09_fundo.loc[
                r09_fundo.semana_emision.eq(34) & r09_fundo.semana_objetivo.eq(34),
                "r09_kg",
            ].sum()
        )
        fila34 = pd.DataFrame(
            [
                {
                    "campania": campania,
                    "semana_emision": 33,
                    "semana_objetivo": 34,
                    "macro_kg": macro34_kg,
                    "real_kg": float(semanal34.real_kg.sum()),
                    "montue_kg": float(semanal34.montue_kg.sum()),
                    "fecha_max": semanal34.fecha_max.max(),
                    "r09_previo_kg": r09_previo,
                    "r09_misma_semana_kg": r09_misma,
                }
            ]
        )
        extendido = pd.concat([contrato, fila34], ignore_index=True)
        pred_extendido = _predecir(extendido, semanal_fundo, cfg_ganadora)
        if calibracion_ganadora == "sin_calibracion":
            pred34 = pred_extendido.iloc[-1]
        else:
            partes = calibracion_ganadora.removeprefix("l").split("-k")
            pred34 = _calibrar_residuo_online(
                pred_extendido,
                lookback=int(partes[0]),
                shrink=float(partes[1]),
            ).iloc[-1]
        sensibilidad_s34 = {
            "estado": "holdout_sensibilidad_no_promocion",
            "real_kg": float(pred34.real_kg),
            "nowcast_candidato_kg": float(pred34.candidate_kg),
            "macro_presemana_kg": float(pred34.macro_kg),
            "r09_presemana_kg": float(pred34.r09_previo_kg),
            "r09_misma_semana_kg": float(pred34.r09_misma_semana_kg),
            "error_abs_candidato_kg": abs(float(pred34.candidate_kg - pred34.real_kg)),
            "error_abs_r09_misma_semana_kg": abs(
                float(pred34.r09_misma_semana_kg - pred34.real_kg)
            ),
        }
    return {
        "schema": "screening-intraweek-nowcast-v1",
        "campania": campania,
        "producto": "nowcast de cierre emitible el miercoles con balanza lunes-martes",
        "ganador_micro_replay": ganador,
        "calibracion_residual_ganadora": calibracion_ganadora,
        "seleccion": "solo desarrollo <= S30; S31-S33 holdout",
        "evaluation_contract": {
            "keyset_sha256": _keyset(final),
            "n_semanas": int(len(final)),
            "real_kg": float(final.real_kg.sum()),
            "ultima_semana_cerrada": 33,
            "fuente_reales": str(access),
            "fuente_r09": str(r09_access),
        },
        "metricas": metricas,
        "sensibilidad_s34": sensibilidad_s34,
        "ranking_desarrollo": orden.head(20).to_dict("records"),
        "ranking_calibracion_desarrollo": orden_calibracion.to_dict("records"),
        "detalle": final.to_dict("records"),
        "usa_r09_como_predictor": False,
        "publicable": False,
    }


__all__ = [
    "ACCESS_DEFAULT",
    "Configuracion",
    "R09_ACCESS_DEFAULT",
    "ejecutar_intraweek",
    "leer_diario",
]
