"""Adaptador de exportaciones planas R09/H01 al contrato analítico.

Las exportaciones CSV disponibles no traen el ``lote_id`` numérico de PostgreSQL y
describen el fundo con catálogos distintos entre R09 y H01. Este módulo no intenta
adivinar una equivalencia de fundo: construye una identidad física explícita con
``módulo + turno + lote`` y conserva ``campania`` como dimensión separada.

La salida es compatible con ``preparar_r09`` y, por tanto, con el torneo, el motor de
proyección y el challenger ``HibridoEstadoOleadas_v1``. Las filas descartadas y la
cobertura del maestro quedan en el manifiesto para que una ejecución con faltantes no
parezca completa.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .backtest import preparar_r09

_CLAVES_FISICAS = ("modulo", "turno", "lote")


def _nombre_columna(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return texto.strip().casefold().replace(" ", "").replace("_", "")


def _aplicar_aliases(tabla: pd.DataFrame, aliases: dict[str, tuple[str, ...]]) -> pd.DataFrame:
    salida = tabla.copy()
    disponibles = {_nombre_columna(columna): columna for columna in salida.columns}
    for canonico, nombres in aliases.items():
        if canonico in salida.columns:
            continue
        original = next(
            (disponibles.get(_nombre_columna(nombre)) for nombre in nombres),
            None,
        )
        if original is not None:
            salida[canonico] = salida[original]
    return salida


def _texto(tabla: pd.DataFrame, columna: str) -> pd.Series:
    salida = tabla[columna].astype("string").str.strip().str.upper()
    vacios = salida.isna() | salida.eq("") | salida.eq("NAN")
    return salida.mask(vacios)


def _identidad_fisica(tabla: pd.DataFrame) -> pd.Series:
    partes = [_texto(tabla, columna) for columna in _CLAVES_FISICAS]
    salida = partes[0].fillna("")
    for parte in partes[1:]:
        salida = salida + "|" + parte.fillna("")
    valido = pd.concat(partes, axis=1).notna().all(axis=1)
    return salida.mask(~valido)


def _exigir(tabla: pd.DataFrame, columnas: tuple[str, ...], nombre: str) -> None:
    faltantes = [columna for columna in columnas if columna not in tabla]
    if faltantes:
        raise ValueError(f"{nombre} no contiene columnas requeridas: {faltantes}")


def _normalizar_forecast(forecast: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    if not isinstance(forecast, pd.DataFrame):
        raise TypeError("forecast debe ser un pandas.DataFrame")
    aliases = {
        "campania": ("campania", "campaña", "campana"),
        "fundo": ("fundo", "fundo_ppto", "fundo_operativo"),
        "modulo": ("modulo", "módulo", "modulo_id"),
        "turno": ("turno", "turno_id"),
        "lote": ("lote", "lote_codigo"),
        "fecha_cos": ("fecha_cos", "fecha_cosecha", "fcos"),
        "frutos_por_planta": ("frutos_por_planta", "frt_cos"),
        "peso_baya": ("peso_baya", "peso"),
        "frutos_total": ("frutos_total", "frutos"),
        "plantas_maestro": ("plantas_maestro", "n_plantas", "nplantas"),
        "area_ha": ("area_ha", "area"),
        "version": ("version", "version_forecast"),
        "kg": ("kg", "kilogramos"),
    }
    salida = _aplicar_aliases(forecast, aliases)
    _exigir(
        salida,
        ("campania", "modulo", "turno", "lote", "fecha_cos", "version", "kg"),
        "forecast",
    )
    salida = salida.copy()
    antes = len(salida)
    salida["lote_id"] = _identidad_fisica(salida)
    salida["campania"] = _texto(salida, "campania")
    salida["modulo"] = _texto(salida, "modulo")
    salida["turno"] = _texto(salida, "turno")
    salida["lote"] = _texto(salida, "lote")
    salida["fecha_cos"] = pd.to_datetime(salida["fecha_cos"], errors="coerce").dt.normalize()
    salida["kg"] = pd.to_numeric(salida["kg"], errors="coerce")
    invalidas = salida[["campania", "lote_id", "fecha_cos", "kg"]].isna().any(axis=1)
    descartadas = int(invalidas.sum())
    if descartadas:
        salida = salida.loc[~invalidas].copy()
    if salida.empty:
        raise ValueError("forecast no contiene filas válidas después de normalizar")
    if "empresa" in salida:
        salida["empresa"] = salida["empresa"].fillna("").astype(str)
    else:
        salida["empresa"] = ""
    salida["fundo"] = (
        salida["fundo"].fillna("").astype(str).str.strip()
        if "fundo" in salida
        else ""
    )
    if "frutos_por_planta" not in salida:
        salida["frutos_por_planta"] = np.nan
    if "peso_baya" not in salida:
        salida["peso_baya"] = np.nan
    if "frutos_total" not in salida:
        salida["frutos_total"] = np.nan
    if "plantas_maestro" not in salida:
        salida["plantas_maestro"] = np.nan
    salida["frutos_por_planta"] = pd.to_numeric(salida["frutos_por_planta"], errors="coerce")
    salida["peso_baya"] = pd.to_numeric(salida["peso_baya"], errors="coerce")
    salida["frutos_total"] = pd.to_numeric(salida["frutos_total"], errors="coerce")
    salida["plantas_maestro"] = pd.to_numeric(salida["plantas_maestro"], errors="coerce")
    return salida, {"filas_entrada": antes, "filas_descartadas": descartadas}


def _normalizar_cosecha(cosecha: pd.DataFrame | None) -> tuple[pd.DataFrame, dict[str, int]]:
    aliases = {
        "campania": ("campania", "campaña", "campana"),
        "modulo": ("modulo", "módulo", "modulo_id"),
        "turno": ("turno", "turno_id"),
        "lote": ("lote", "lote_codigo"),
        "fecha": ("fecha", "fecha_cosecha", "date"),
        "kg": ("kg", "kilogramos"),
        "peso_baya": ("peso_baya", "peso"),
        "plantas_cosechadas": ("plantas_cosechadas", "n_plantas", "nplantas"),
    }
    if cosecha is None:
        vacia = pd.DataFrame(
            columns=[
                "campania",
                "lote_id",
                "fecha",
                "kg",
                "peso_baya",
                "plantas_cosechadas",
            ]
        )
        return vacia, {"filas_entrada": 0, "filas_descartadas": 0}
    if not isinstance(cosecha, pd.DataFrame):
        raise TypeError("cosecha debe ser un pandas.DataFrame o None")
    salida = _aplicar_aliases(cosecha, aliases)
    _exigir(salida, ("campania", "modulo", "turno", "lote", "fecha", "kg"), "cosecha")
    salida = salida.copy()
    antes = len(salida)
    salida["lote_id"] = _identidad_fisica(salida)
    salida["campania"] = _texto(salida, "campania")
    salida["fecha"] = pd.to_datetime(salida["fecha"], errors="coerce").dt.normalize()
    salida["kg"] = pd.to_numeric(salida["kg"], errors="coerce")
    invalidas = salida[["campania", "lote_id", "fecha", "kg"]].isna().any(axis=1)
    descartadas = int(invalidas.sum())
    salida = salida.loc[~invalidas].copy()
    if "peso_baya" not in salida:
        salida["peso_baya"] = np.nan
    if "plantas_cosechadas" not in salida:
        salida["plantas_cosechadas"] = np.nan
    salida["peso_baya"] = pd.to_numeric(salida["peso_baya"], errors="coerce")
    salida["plantas_cosechadas"] = pd.to_numeric(
        salida["plantas_cosechadas"], errors="coerce"
    )
    return salida, {"filas_entrada": antes, "filas_descartadas": descartadas}


def _normalizar_maestro(maestro_lotes: pd.DataFrame | None) -> pd.DataFrame:
    if maestro_lotes is None:
        return pd.DataFrame(columns=["lote_id", "n_plantas", "area_ha"])
    if not isinstance(maestro_lotes, pd.DataFrame):
        raise TypeError("maestro_lotes debe ser un pandas.DataFrame o None")
    aliases = {
        "modulo": ("modulo", "módulo", "modulo_id"),
        "turno": ("turno", "turno_id"),
        "lote": ("lote", "lote_codigo"),
        "n_plantas": ("n_plantas", "nplantas", "plantas"),
        "area_ha": ("area_ha", "area"),
    }
    salida = _aplicar_aliases(maestro_lotes, aliases)
    _exigir(salida, ("modulo", "turno", "lote"), "maestro_lotes")
    salida = salida.copy()
    salida["lote_id"] = _identidad_fisica(salida)
    if "n_plantas" not in salida:
        salida["n_plantas"] = np.nan
    if "area_ha" not in salida:
        salida["area_ha"] = np.nan
    salida["n_plantas"] = pd.to_numeric(salida["n_plantas"], errors="coerce")
    salida["area_ha"] = pd.to_numeric(salida["area_ha"], errors="coerce")
    salida = salida[["lote_id", "n_plantas", "area_ha"]]
    if salida.lote_id.isna().any():
        raise ValueError("maestro_lotes contiene una identidad física incompleta")
    if salida.duplicated("lote_id").any():
        raise ValueError("maestro_lotes repite módulo|turno|lote")
    return salida


def construir_panel_r09_exportado(
    forecast: pd.DataFrame,
    cosecha: pd.DataFrame | None = None,
    maestro_lotes: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Construye el panel R09/H01 desde DataFrames exportados.

    La fecha de emisión se deriva del código ``Sxx`` con la semántica de
    ``preparar_r09``: lunes ISO de la semana de versión. Las semanas objetivo se
    normalizan al lunes y se conservan solo H1--H10, igual que en el backtest oficial.
    """

    f, manifiesto_f = _normalizar_forecast(forecast)
    h, manifiesto_h = _normalizar_cosecha(cosecha)
    maestro = _normalizar_maestro(maestro_lotes)
    n_lotes_entrada = int(f.lote_id.nunique())
    if not maestro.empty:
        f = f.merge(
            maestro,
            on="lote_id",
            how="left",
            suffixes=("", "_maestro"),
            validate="many_to_one",
        )
        f["plantas_maestro"] = f["plantas_maestro"].fillna(f["n_plantas"])
        if "area_ha" in f and "area_ha_maestro" in f:
            f["area_ha"] = f["area_ha"].fillna(f["area_ha_maestro"])
        elif "area_ha_maestro" in f:
            f["area_ha"] = f["area_ha_maestro"]

    panel = preparar_r09(f, h)
    panel["identidad_fisica"] = panel["lote_id"]
    panel["fuente_panel"] = "r09_exportado_csv_h01_exportado"
    n_lotes_con_plantas = int(panel.loc[panel.plantas.notna(), "lote_id"].nunique())
    n_lotes_sin_plantas = int(panel.loc[panel.plantas.isna(), "lote_id"].nunique())
    real_cobertura = panel.assign(tiene_real=panel.real_kg.notna()).groupby(
        "campania", as_index=True
    ).agg(
        filas=("tiene_real", "size"),
        filas_con_real=("tiene_real", "sum"),
        lotes=("lote_id", "nunique"),
    )
    lotes_con_real = (
        panel.loc[panel.real_kg.notna()]
        .groupby("campania")
        .lote_id.nunique()
        .rename("lotes_con_real")
    )
    real_cobertura = real_cobertura.join(lotes_con_real, how="left").fillna(0)
    real_cobertura_dict = {
        str(campania): {str(k): int(v) for k, v in valores.items()}
        for campania, valores in real_cobertura.to_dict(orient="index").items()
    }
    metadata: dict[str, Any] = {
        "fuente": "r09_forecast_semanal.csv + h01_prod_historica.csv",
        "identidad": "campania + modulo + turno + lote",
        "semantica_fecha_emision": "lunes ISO derivado de Sxx",
        "filas_forecast_entrada": manifiesto_f["filas_entrada"],
        "filas_forecast_descartadas": manifiesto_f["filas_descartadas"],
        "filas_cosecha_entrada": manifiesto_h["filas_entrada"],
        "filas_cosecha_descartadas": manifiesto_h["filas_descartadas"],
        "lotes_forecast_entrada": n_lotes_entrada,
        "lotes_maestro": int(maestro.lote_id.nunique()),
        "lotes_con_plantas": n_lotes_con_plantas,
        "lotes_sin_plantas": n_lotes_sin_plantas,
        "real_cobertura": real_cobertura_dict,
        "filas_panel": int(len(panel)),
        "emision_min": panel.fecha_emision.min().isoformat(),
        "emision_max": panel.fecha_emision.max().isoformat(),
        "horizontes": sorted(int(horizonte) for horizonte in panel.horizonte_semanas.unique()),
        "apto_para_replay": True,
        "advertencias": [],
    }
    if n_lotes_sin_plantas:
        metadata["advertencias"].append(
            f"{n_lotes_sin_plantas} lotes no tienen plantas en el maestro; "
            "no son aptos para un modelo que requiera componentes físicos."
        )
    if manifiesto_h["filas_descartadas"]:
        metadata["advertencias"].append(
            f"Se descartaron {manifiesto_h['filas_descartadas']} filas H01 sin identidad, "
            "fecha o kilos válidos."
        )
    return panel, metadata


def cargar_panel_r09_csv(
    ruta_forecast: str | Path,
    ruta_cosecha: str | Path | None = None,
    ruta_maestro: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Lee los tres CSV y delega la construcción al adaptador en memoria."""

    ruta_forecast = Path(ruta_forecast)
    if not ruta_forecast.is_file():
        raise FileNotFoundError(ruta_forecast)
    forecast = pd.read_csv(ruta_forecast, low_memory=False)
    cosecha = None
    if ruta_cosecha is not None:
        ruta_cosecha = Path(ruta_cosecha)
        if not ruta_cosecha.is_file():
            raise FileNotFoundError(ruta_cosecha)
        cosecha = pd.read_csv(ruta_cosecha, low_memory=False)
    maestro = None
    if ruta_maestro is not None:
        ruta_maestro = Path(ruta_maestro)
        if not ruta_maestro.is_file():
            raise FileNotFoundError(ruta_maestro)
        maestro = pd.read_csv(ruta_maestro, low_memory=False)
    panel, metadata = construir_panel_r09_exportado(forecast, cosecha, maestro)
    metadata["archivo_forecast"] = str(ruta_forecast)
    metadata["archivo_cosecha"] = str(ruta_cosecha) if ruta_cosecha else None
    metadata["archivo_maestro"] = str(ruta_maestro) if ruta_maestro else None
    return panel, metadata


__all__ = ["cargar_panel_r09_csv", "construir_panel_r09_exportado"]
