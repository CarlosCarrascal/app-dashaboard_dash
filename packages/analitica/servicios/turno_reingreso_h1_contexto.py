"""Derivación del contexto H01 as-of para run76 H1."""

from __future__ import annotations

import numpy as np
import pandas as pd


def derivar_turno_reingreso_asof(
    contrato: pd.DataFrame,
    h01: pd.DataFrame,
    *,
    ventana_intervalos: int = 5,
) -> pd.DataFrame:
    """Deriva Turno y mediana de reingreso usando solo H01 anterior al corte."""

    requeridas = {"campania", "lote_id", "fecha", "turno", "kg"}
    faltantes = sorted(requeridas.difference(h01.columns))
    if faltantes:
        raise ValueError(f"H01 no cumple el contrato mínimo: {faltantes}")
    historia = h01.copy()
    historia["fecha"] = pd.to_datetime(historia.fecha, errors="raise").dt.normalize()
    historia["kg"] = pd.to_numeric(historia.kg, errors="coerce").fillna(0.0)
    historia = historia[historia.kg.gt(0)].copy()
    historia["turno"] = historia.turno.fillna("").astype(str).str.strip()
    historia = historia.sort_values(["campania", "lote_id", "fecha"])

    por_lote = {
        (str(campania), int(lote_id)): bloque.copy()
        for (campania, lote_id), bloque in historia.groupby(["campania", "lote_id"], sort=False)
    }
    salida = contrato.copy()
    turnos: list[str | None] = []
    intervalos: list[float] = []
    observaciones: list[int] = []
    ultima_cosecha: list[pd.Timestamp | pd.NaT] = []
    for fila in salida.itertuples(index=False):
        bloque = por_lote.get((str(fila.campania), int(fila.lote_id)))
        if bloque is None:
            turnos.append(None)
            intervalos.append(np.nan)
            observaciones.append(0)
            ultima_cosecha.append(pd.NaT)
            continue
        previo = bloque[bloque.fecha.lt(pd.Timestamp(fila.fecha_emision))].copy()
        fechas = previo.fecha.drop_duplicates().sort_values()
        observaciones.append(int(len(fechas)))
        ultima_cosecha.append(fechas.max() if len(fechas) else pd.NaT)
        turno_valido = previo.loc[previo.turno.ne(""), "turno"]
        turnos.append(str(turno_valido.iloc[-1]) if len(turno_valido) else None)
        if len(fechas) < 2:
            intervalos.append(np.nan)
            continue
        dias = fechas.diff().dt.days.dropna()
        dias = dias[dias.between(5, 21)]
        if dias.empty:
            intervalos.append(np.nan)
            continue
        intervalos.append(float(dias.tail(ventana_intervalos).median()))
    salida["turno"] = turnos
    salida["dias_reingreso"] = intervalos
    salida["n_cosechas_previas_asof"] = observaciones
    salida["fecha_ultima_cosecha_asof"] = ultima_cosecha
    return salida
