"""Contexto operativo H01 con semántica as-of para run73."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .turno_reingreso_fuentes import CAMPANIA


def _preparar_h01(h01: pd.DataFrame) -> pd.DataFrame:
    requeridas = {"campania", "lote_id", "fecha", "turno", "kg"}
    faltantes = sorted(requeridas.difference(h01.columns))
    if faltantes:
        raise ValueError(f"H01 no cumple el contrato minimo: {faltantes}")
    historia = h01.copy()
    historia["fecha"] = pd.to_datetime(historia.fecha, errors="raise").dt.normalize()
    historia["kg"] = pd.to_numeric(historia.kg, errors="coerce").fillna(0.0)
    historia = historia[historia.kg.gt(0)].copy()
    historia["turno"] = historia.turno.fillna("").astype(str).str.strip()
    historia = historia.sort_values(["campania", "lote_id", "fecha", "kg"], kind="stable")
    claves_dia = ["campania", "lote_id", "fecha"]
    kilos = historia.groupby(claves_dia, as_index=False).kg.sum()
    turnos = historia[historia.turno.ne("")].drop_duplicates(claves_dia, keep="last")
    diaria = kilos.merge(turnos[claves_dia + ["turno"]], on=claves_dia, how="left")
    diaria["turno"] = diaria.turno.fillna("")
    return diaria.sort_values(claves_dia, kind="stable").reset_index(drop=True)


def _mediana_grupo(
    intervalos: pd.DataFrame,
    columnas: list[str],
    min_observaciones: int,
) -> dict[tuple[Any, ...], tuple[float, int]]:
    if intervalos.empty:
        return {}
    resultado: dict[tuple[Any, ...], tuple[float, int]] = {}
    agrupador: str | list[str] = columnas[0] if len(columnas) == 1 else columnas
    for clave, bloque in intervalos.groupby(agrupador, dropna=False, sort=False):
        valores = bloque.dias_reingreso.dropna().tail(200)
        if len(valores) < min_observaciones:
            continue
        clave_tupla = clave if isinstance(clave, tuple) else (clave,)
        resultado[clave_tupla] = (float(valores.median()), int(len(valores)))
    return resultado


def derivar_contexto_asof(
    macro: pd.DataFrame,
    h01: pd.DataFrame,
) -> pd.DataFrame:
    """Deriva ultimo cierre, Turno y reingreso jerarquico antes de la emision."""

    diaria = _preparar_h01(h01)
    dimension = macro[["lote_id", "fundo", "modulo"]].drop_duplicates("lote_id")
    diaria = diaria.merge(dimension, on="lote_id", how="left", validate="many_to_one")
    diaria["fecha_anterior"] = diaria.groupby(["campania", "lote_id"], sort=False).fecha.shift()
    diaria["dias_reingreso"] = (diaria.fecha - diaria.fecha_anterior).dt.days
    intervalos = diaria[diaria.dias_reingreso.between(5, 21)].copy()

    salidas: list[pd.DataFrame] = []
    for emision in sorted(pd.to_datetime(macro.fecha_emision).unique()):
        emision = pd.Timestamp(emision).normalize()
        previo = diaria[diaria.fecha.lt(emision)].copy()
        previo_int = intervalos[intervalos.fecha.lt(emision)].copy()
        ultimos = previo.sort_values("fecha", kind="stable").drop_duplicates("lote_id", keep="last")
        contexto = dimension.copy()
        contexto["campania"] = CAMPANIA
        contexto["fecha_emision"] = emision
        contexto = contexto.merge(
            ultimos[["lote_id", "fecha", "turno"]].rename(
                columns={"fecha": "fecha_ultima_cosecha_asof"}
            ),
            on="lote_id",
            how="left",
            validate="one_to_one",
        )
        contexto["turno"] = contexto.turno.fillna("")

        mapas = [
            ("lote", ["lote_id"], 2),
            ("modulo_turno", ["modulo", "turno"], 3),
            ("fundo_turno", ["fundo", "turno"], 5),
            ("turno", ["turno"], 5),
            ("modulo", ["modulo"], 3),
            ("fundo", ["fundo"], 5),
        ]
        diccionarios = [
            (nombre, columnas, _mediana_grupo(previo_int, columnas, minimo))
            for nombre, columnas, minimo in mapas
        ]
        global_valores = previo_int.dias_reingreso.dropna()
        global_mediana = (
            (float(global_valores.median()), int(len(global_valores)))
            if len(global_valores) >= 5
            else None
        )
        dias: list[float] = []
        niveles: list[str] = []
        observaciones: list[int] = []
        for fila in contexto.itertuples(index=False):
            elegido: tuple[float, int] | None = None
            nivel = "sin_reingreso"
            for nombre, columnas, valores in diccionarios:
                clave = tuple(getattr(fila, columna) for columna in columnas)
                if nombre in {"modulo_turno", "fundo_turno", "turno"} and not fila.turno:
                    continue
                if clave in valores:
                    elegido = valores[clave]
                    nivel = nombre
                    break
            if elegido is None and global_mediana is not None:
                elegido = global_mediana
                nivel = "global"
            dias.append(float(elegido[0]) if elegido else np.nan)
            observaciones.append(int(elegido[1]) if elegido else 0)
            niveles.append(nivel)
        contexto["dias_reingreso"] = dias
        contexto["nivel_reingreso"] = niveles
        contexto["n_intervalos_reingreso_asof"] = observaciones
        salidas.append(contexto)
    return pd.concat(salidas, ignore_index=True)


def enriquecer_macro(macro: pd.DataFrame, contexto: pd.DataFrame) -> pd.DataFrame:
    columnas = [
        "campania",
        "fecha_emision",
        "lote_id",
        "turno",
        "dias_reingreso",
        "nivel_reingreso",
        "n_intervalos_reingreso_asof",
        "fecha_ultima_cosecha_asof",
    ]
    salida = macro.merge(
        contexto[columnas],
        on=["campania", "fecha_emision", "lote_id"],
        how="left",
        validate="many_to_one",
    )
    salida["turno"] = salida.turno.fillna("")
    # El candidato exige las tres piezas: cierre, Turno y reingreso. La funcion
    # pura solo inspecciona cierre+dias, por lo que anulamos dias si Turno no fue
    # observado para evitar atribuir una programacion operativa inexistente.
    salida.loc[salida.turno.eq(""), "dias_reingreso"] = np.nan
    return salida
