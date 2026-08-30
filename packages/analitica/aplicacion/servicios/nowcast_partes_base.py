"""Primitivas de entrada compartidas por las variantes de nowcast."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.servicios.parametros_nowcast import ACCESS_DEFAULT, columna_campania

R09_ACCESS_DEFAULT = Path(r"C:\Users\CCARRASCAL\Downloads\BD_AQUANQA_26_v2.accdb")
RUNS_CERTIFICADOS = {"C2024": 78, "C2025": 78, "C2026": 76}
FUNDOS = ("Arena", "Ayllu", "Kawsay", "Quri")
EPS = 1_000.0


def _mapear_fundo_h01(tabla: pd.DataFrame) -> pd.DataFrame:
    t = tabla.copy()
    modulo = t.modulo.astype(str).str.extract(r"(\d+)", expand=False).astype(float)
    fisico = t.fundo_fisico.astype(str).str.casefold()
    t["fundo_operativo"] = np.select(
        [
            fisico.eq("aqu anqa") & modulo.between(1, 4),
            fisico.eq("aqu anqa ii") & modulo.between(1, 5),
            fisico.eq("aqu anqa ii") & modulo.between(6, 11),
            fisico.eq("aqu anqa ii") & modulo.between(12, 15),
            fisico.eq("aqu anqa ii") & modulo.between(16, 17),
        ],
        ["Arena", "Quri", "Kawsay", "Ayllu", "Kawsay"],
        default="",
    )
    if t.fundo_operativo.eq("").any():
        raise ValueError("H01 contiene fundo/modulo sin mapeo operativo")
    return t


def leer_diario(access: Path, campania: str) -> pd.DataFrame:
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "Este comando necesita pyodbc y el controlador ODBC de Microsoft Access."
        ) from exc
    cadena = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(access)
    with pyodbc.connect(cadena) as conexion:
        cursor = conexion.cursor()
        camp = columna_campania(cursor, "H01_ProdHistorica")
        tabla = pd.read_sql(
            "SELECT [Fundo], [Modulo], [Fecha], [Semana], Sum([KG]) AS total_kg "
            "FROM [H01_ProdHistorica] "
            f"WHERE [{camp}] = ? GROUP BY [Fundo], [Modulo], [Fecha], [Semana]",
            conexion,
            params=[campania],
        )
    tabla.columns = ["fundo_fisico", "modulo", "fecha", "semana_objetivo", "kg"]
    tabla["fecha"] = pd.to_datetime(tabla.fecha).dt.normalize()
    tabla["dia_iso"] = tabla.fecha.dt.isocalendar().day.astype(int)
    return _mapear_fundo_h01(tabla)


def _agregar_empresa(tabla: pd.DataFrame, columnas: Iterable[str]) -> pd.DataFrame:
    agregaciones = {"real_kg": ("real_kg", "sum")}
    for columna in columnas:
        agregaciones[columna] = (columna, "sum")
    return tabla.groupby(["campania", "fecha_objetivo"], as_index=False).agg(**agregaciones)


def _metricas_adaptativa(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    if tabla.empty:
        return {"wape": np.nan, "sesgo": np.nan, "mae_kg": np.nan, "n": 0}
    error = tabla[columna].astype(float) - tabla.real_kg.astype(float)
    denominador = float(tabla.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador) if denominador else np.nan,
        "sesgo": float(error.sum() / denominador) if denominador else np.nan,
        "mae_kg": float(error.abs().mean()),
        "n": int(len(tabla)),
    }


def _hash_keyset(tabla: pd.DataFrame) -> str:
    columnas = ["campania", "fecha_objetivo", "fundo_operativo"]
    texto = (
        tabla[columnas]
        .sort_values(columnas, kind="stable")
        .astype(str)
        .agg("|".join, axis=1)
        .str.cat(sep="\n")
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def sha256_archivo(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def diagnostico_shares(tabla: pd.DataFrame) -> dict[str, float | int]:
    validas = tabla.loc[tabla.real_kg.gt(0)].copy()
    share_fundo = validas.montue_kg / validas.real_kg
    share_fundo = share_fundo.loc[share_fundo.between(0.0, 1.0)]
    empresa = validas.groupby("fecha_objetivo", as_index=False).agg(
        real_kg=("real_kg", "sum"), montue_kg=("montue_kg", "sum")
    )
    share_empresa = empresa.montue_kg / empresa.real_kg
    share_empresa = share_empresa.loc[share_empresa.between(0.0, 1.0)]
    return {
        "mediana_empresa_semana": float(share_empresa.median()) if len(share_empresa) else np.nan,
        "mediana_fundo_semana": float(share_fundo.median()) if len(share_fundo) else np.nan,
        "p10_fundo_semana": float(share_fundo.quantile(0.10)) if len(share_fundo) else np.nan,
        "p90_fundo_semana": float(share_fundo.quantile(0.90)) if len(share_fundo) else np.nan,
        "n_fundo_semana": int(len(share_fundo)),
        "n_empresa_semana": int(len(share_empresa)),
        "uso": "diagnostico descriptivo; no selecciona la configuracion externa",
    }


def normalizar_fundo_r09(valor: object) -> str:
    """Unifica nombres descriptivos históricos y códigos Aqu Anqa 1..5."""
    texto = str(valor or "").strip()
    bajo = texto.casefold()
    if "arena azul" in bajo or bajo == "arena":
        return "Arena"
    if "ayllu allpa" in bajo or bajo == "ayllu":
        return "Ayllu"
    if "kawsay allpa" in bajo or bajo == "kawsay":
        return "Kawsay"
    if "quri allpa" in bajo or bajo == "quri":
        return "Quri"
    return texto


__all__ = [
    "ACCESS_DEFAULT",
    "EPS",
    "FUNDOS",
    "R09_ACCESS_DEFAULT",
    "RUNS_CERTIFICADOS",
    "_mapear_fundo_h01",
    "diagnostico_shares",
    "leer_diario",
    "normalizar_fundo_r09",
    "sha256_archivo",
]
