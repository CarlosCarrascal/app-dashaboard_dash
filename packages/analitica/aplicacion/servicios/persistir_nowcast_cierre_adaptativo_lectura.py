"""Lectura y normalizacion de fuentes del nowcast de cierre adaptativo."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd

from analitica.aplicacion.servicios.nowcast import leer_diario as _leer_diario_default
from analitica.aplicacion.servicios.nowcast import (
    normalizar_fundo_r09 as _normalizar_fundo_r09_default,
)
from analitica.aplicacion.servicios.parametros_nowcast import (
    leer_macro_h1 as _leer_macro_h1_default,
)
from analitica.aplicacion.servicios.parametros_nowcast import (
    leer_reales_r09_fundo as _leer_r09_default,
)


def normalizar_detalle_artifact(path: Path, *, campaign: str) -> pd.DataFrame:
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document.get("detalle", {}).get(campaign, [])
    if not rows:
        raise RuntimeError(f"El artefacto no contiene detalle {campaign}")
    table = pd.DataFrame(rows)
    required = {
        "campania",
        "fecha_objetivo",
        "fundo_operativo",
        "macro_kg",
        "montue_kg",
        "real_kg",
        "r09_presemana_kg",
        "r09_misma_semana_kg",
    }
    missing = required.difference(table.columns)
    if missing:
        raise RuntimeError(f"Faltan columnas en el artefacto: {sorted(missing)}")
    table["fecha_objetivo"] = pd.to_datetime(table.fecha_objetivo).dt.normalize()
    table["fecha_corte_asof"] = table.fecha_objetivo + pd.Timedelta(days=1)
    table["dias_montue_observados"] = 2
    return table


def append_latest_closed_week(
    base: pd.DataFrame,
    *,
    real_access: Path,
    r09_access: Path,
    campaign: str,
    fundos: tuple[str, ...],
    macro_run_s34: int,
    leer_macro_h1: Callable[..., pd.DataFrame] = _leer_macro_h1_default,
    leer_diario: Callable[..., pd.DataFrame] = _leer_diario_default,
    leer_reales_r09_fundo: Callable[..., tuple[object, pd.DataFrame]] = _leer_r09_default,
    normalizar_fundo_r09: Callable[[object], object] = _normalizar_fundo_r09_default,
) -> pd.DataFrame:
    """Anexa S34 solo si existen Lun-Mar y cierre real hasta viernes.

    La historia certificada termina en S33. El snapshot Access congelado tiene
    H01 completo hasta el viernes 21/08, por lo que S34 ya puede evaluarse tras
    su domingo de cierre. Macro h1 se toma de la corrida 73, que contiene la
    emision previa S33 para el objetivo S34.
    """

    target = pd.Timestamp(base.fecha_objetivo.max()).normalize() + pd.Timedelta(days=7)
    if target.date() != date(2026, 8, 17):
        raise RuntimeError(f"Se esperaba anexar S34 (17/08), no {target.date()}")
    if pd.Timestamp.today().normalize() <= target + pd.Timedelta(days=6):
        raise RuntimeError("S34 todavia no ha cerrado en calendario")

    macro = leer_macro_h1(campaign, run_id=macro_run_s34)
    macro = macro.loc[
        macro.fecha_objetivo.eq(target) & macro.fecha_emision.eq(target - pd.Timedelta(days=7))
    ].copy()
    if set(macro.fundo_operativo) != set(fundos):
        raise RuntimeError("Macro S34 no cubre exactamente los cuatro fundos")

    daily = leer_diario(real_access, campaign)
    daily["fecha_objetivo"] = daily.fecha - pd.to_timedelta(daily.dia_iso - 1, unit="D")
    daily["es_montue"] = daily.dia_iso.le(2)
    week = daily.loc[daily.fecha_objetivo.eq(target)].copy()
    if week.empty or pd.Timestamp(week.fecha.max()).normalize() < target + pd.Timedelta(days=4):
        raise RuntimeError("S34 no tiene cierre operativo hasta el viernes")
    days = week.loc[week.es_montue].groupby("fundo_operativo").fecha.nunique()
    if set(days.index) != set(fundos) or not days.eq(2).all():
        raise RuntimeError("S34 no tiene lunes y martes completos en los cuatro fundos")
    weekly = week.groupby("fundo_operativo", as_index=False).agg(
        real_kg=("kg", "sum"),
        montue_kg=("kg", lambda x: float(x[week.loc[x.index, "es_montue"]].sum())),
        fecha_max_real=("fecha", "max"),
    )

    _, r09 = leer_reales_r09_fundo(r09_access, campaign)
    r09["fundo_operativo"] = r09.fundo_operativo.map(normalizar_fundo_r09)
    r09 = r09.groupby(
        ["semana_emision", "semana_objetivo", "fundo_operativo"], as_index=False
    ).r09_kg.sum()
    iso_week = int(target.isocalendar().week)
    pre = r09.loc[
        r09.semana_emision.eq(iso_week - 1) & r09.semana_objetivo.eq(iso_week),
        ["fundo_operativo", "r09_kg"],
    ].rename(columns={"r09_kg": "r09_presemana_kg"})
    same = r09.loc[
        r09.semana_emision.eq(iso_week) & r09.semana_objetivo.eq(iso_week),
        ["fundo_operativo", "r09_kg"],
    ].rename(columns={"r09_kg": "r09_misma_semana_kg"})

    extra = (
        macro.merge(weekly, on="fundo_operativo", how="inner", validate="one_to_one")
        .merge(pre, on="fundo_operativo", how="left", validate="one_to_one")
        .merge(same, on="fundo_operativo", how="left", validate="one_to_one")
    )
    extra["fecha_corte_asof"] = target + pd.Timedelta(days=1)
    extra["dias_montue_observados"] = 2
    columns = sorted(set(base.columns).union(extra.columns))
    return pd.concat(
        [base.reindex(columns=columns), extra.reindex(columns=columns)],
        ignore_index=True,
    ).sort_values(["fecha_objetivo", "fundo_operativo"], kind="stable")


__all__ = ["append_latest_closed_week", "normalizar_detalle_artifact"]
