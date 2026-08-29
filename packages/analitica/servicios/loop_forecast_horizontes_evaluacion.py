"""Evaluación de resultados y comparaciones del loop por horizontes."""

from __future__ import annotations

from typing import Any

import pandas as pd

from analitica.proyeccion.pronostico_horizonte import seleccionar_vintage_coherente

from .loop_forecast_horizontes_configuracion import HORIZONTES


def _semanal(tabla: pd.DataFrame, columna: str) -> pd.DataFrame:
    if tabla.empty:
        return pd.DataFrame(columns=["fecha_objetivo", "pred_kg", "real_kg"])
    t = tabla.copy()
    t["real_kg"] = pd.to_numeric(t["real_kg"], errors="coerce")
    t = t.dropna(subset=[columna, "real_kg"])
    if t.empty:
        return pd.DataFrame(columns=["fecha_objetivo", "pred_kg", "real_kg"])
    return t.groupby("fecha_objetivo", as_index=False).agg(
        pred_kg=(columna, "sum"),
        real_kg=("real_kg", lambda values: values.sum(min_count=1)),
    )


def _metricas(tabla: pd.DataFrame, columna: str) -> dict[str, Any]:
    semanal = _semanal(tabla, columna)
    if semanal.empty:
        return {
            "n_semanas": 0,
            "real_kg": 0.0,
            "pred_kg": 0.0,
            "wape": None,
            "mase": None,
            "mae_kg": None,
            "bias_pct": None,
        }
    error = semanal["pred_kg"] - semanal["real_kg"]
    denominador = float(semanal["real_kg"].abs().sum())
    escala = float(semanal.sort_values("fecha_objetivo")["real_kg"].diff().abs().dropna().mean())
    return {
        "n_semanas": int(len(semanal)),
        "real_kg": float(semanal["real_kg"].sum()),
        "pred_kg": float(semanal["pred_kg"].sum()),
        "wape": float(error.abs().sum() / denominador) if denominador else None,
        "mase": float(error.abs().mean() / escala) if escala > 0 else None,
        "mae_kg": float(error.abs().mean()),
        "bias_pct": float(error.sum() / denominador) if denominador else None,
    }


def _metricas_por_horizonte(tabla: pd.DataFrame, columna: str) -> dict[str, dict[str, Any]]:
    salida: dict[str, dict[str, Any]] = {}
    for horizonte, grupo in tabla.groupby("horizonte_semanas", sort=True):
        salida[str(int(horizonte))] = _metricas(grupo, columna)
    return salida


def _comparar_r09(candidato: pd.DataFrame, r09: pd.DataFrame) -> dict[str, Any]:
    """Compara R09 sólo en emisiones/objetivos/horizontes presentes en ambos."""

    if r09.empty:
        return {"n_semanas": 0, "cobertura_vintage": 0.0, "r09": None, "candidato": None}
    claves = ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    c = candidato.groupby(claves, as_index=False).agg(
        candidato_kg=("pred_kg", "sum"),
        real_kg=("real_kg", lambda values: values.sum(min_count=1)),
    )
    r = r09.groupby(claves, as_index=False).agg(
        r09_kg=("p50_kg", "sum"),
        real_r09=("real_kg", lambda values: values.sum(min_count=1)),
    )
    comunes = c.merge(r, on=claves, how="inner", validate="one_to_one")
    comunes["real_kg"] = comunes["real_kg"].combine_first(comunes["real_r09"])
    comunes = comunes.dropna(subset=["real_kg"])
    if comunes.empty:
        return {"n_semanas": 0, "cobertura_vintage": 0.0, "r09": None, "candidato": None}
    # Se agrega una vez por semana y se evita combinar vintages alternativos.
    comunes = comunes.rename(columns={"candidato_kg": "p50_kg"})
    comunes["lote_id"] = "__EMPRESA__"
    comunes["fundo"] = "__EMPRESA__"
    comunes["modulo"] = "__AGREGADO__"
    comunes = seleccionar_vintage_coherente(comunes).rename(columns={"p50_kg": "candidato_kg"})
    comunes["fecha_objetivo"] = pd.to_datetime(comunes["fecha_objetivo"])
    semanal = comunes.groupby("fecha_objetivo", as_index=False).agg(
        candidato_kg=("candidato_kg", "sum"),
        r09_kg=("r09_kg", "sum"),
        real_kg=("real_kg", "sum"),
    )
    denominador = float(semanal.real_kg.abs().sum())
    e_c = semanal.candidato_kg - semanal.real_kg
    e_r = semanal.r09_kg - semanal.real_kg
    return {
        "n_semanas": int(len(semanal)),
        "cobertura_vintage": float(len(semanal) / max(candidato.fecha_objetivo.nunique(), 1)),
        "candidato": {
            "wape": float(e_c.abs().sum() / denominador) if denominador else None,
            "bias_pct": float(e_c.sum() / denominador) if denominador else None,
        },
        "r09": {
            "wape": float(e_r.abs().sum() / denominador) if denominador else None,
            "bias_pct": float(e_r.sum() / denominador) if denominador else None,
        },
    }


def _resumen_nowcast_vs_v2(
    v2: pd.DataFrame, nowcast: pd.DataFrame, campania: str
) -> dict[str, Any]:
    if v2.empty or nowcast.empty:
        return {"comparabilidad": "sin datos", "v2": None, "nowcast": None}
    v = v2.loc[v2["horizonte_semanas"].eq(1)].copy()
    # ``v2`` llega agregado por fundo desde PostgreSQL.  La selección de
    # vintage usa el mismo contrato que el resto del loop, por lo que se le
    # asignan claves sintéticas sin volver a inventar filas ni kilos.
    v["modulo"] = "__agregado_fundo__"
    v["lote_id"] = "F::" + v["fundo"].astype(str)
    v = seleccionar_vintage_coherente(v)
    v = v.loc[v["fecha_objetivo"].le(pd.Timestamp("2026-08-10"))]
    n = nowcast.copy()
    n["fecha_objetivo"] = pd.to_datetime(n["fecha_objetivo"], errors="raise").dt.normalize()
    n["p50_kg"] = pd.to_numeric(n["p50_kg"], errors="coerce")
    n["real_kg"] = pd.to_numeric(n["real_kg"], errors="coerce")
    n = n.loc[n["fecha_objetivo"].le(pd.Timestamp("2026-08-10"))]
    empresa = n.loc[n["fundo"].astype(str).str.casefold().eq("empresa")]
    if not empresa.empty:
        n = empresa
    else:
        n = n.loc[~n["fundo"].astype(str).str.casefold().eq("empresa")]
    vs = _semanal(v, "p50_kg")
    ns = _semanal(n, "p50_kg")
    c = vs.merge(ns, on="fecha_objetivo", suffixes=("_v2", "_nowcast"), validate="one_to_one")
    if c.empty:
        return {"comparabilidad": "sin semanas comunes", "v2": None, "nowcast": None}
    c["real_kg"] = c["real_kg_v2"]
    return {
        "comparabilidad": (
            "tareas distintas: v2 se emite antes de la semana; nowcast observa lunes-martes"
        ),
        "semanas_comunes": int(len(c)),
        "v2": _metricas(c.rename(columns={"pred_kg_v2": "pred_kg"}), "pred_kg"),
        "nowcast": _metricas(c.rename(columns={"pred_kg_nowcast": "pred_kg"}), "pred_kg"),
    }


__all__ = [
    "HORIZONTES",
    "_comparar_r09",
    "_metricas",
    "_metricas_por_horizonte",
    "_resumen_nowcast_vs_v2",
    "_semanal",
    "seleccionar_vintage_coherente",
]
