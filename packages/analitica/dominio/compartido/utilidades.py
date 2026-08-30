"""Utilidades puras compartidas por las familias de proyección.

Este módulo concentra las operaciones pequeñas que antes estaban repartidas en
cinco archivos: fechas as-of, huellas, identidad reproducible, normalización y
serialización. Las fachadas de submódulo se registran en ``compartido`` para no
romper imports históricos mientras se reduce la superficie física del paquete.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Fechas as-of ---------------------------------------------------------------

def lunes_semana(valores: pd.Series | pd.Timestamp) -> pd.Series | pd.Timestamp:
    """Normaliza fechas al lunes de su semana calendario."""
    if not isinstance(valores, pd.Series):
        fecha = pd.Timestamp(valores).normalize()
        return fecha - pd.to_timedelta(fecha.weekday(), unit="D")
    fechas = pd.to_datetime(valores, errors="coerce").astype("datetime64[ns]").dt.normalize()
    return fechas - pd.to_timedelta(fechas.dt.weekday, unit="D")


def ultimo_disponible(
    objetivos: pd.DataFrame,
    observaciones: pd.DataFrame,
    columnas: list[str],
    *,
    entidad: str | list[str] = "lote_id",
    fecha_observacion: str = "fecha",
    fecha_corte: str = "fecha_emision",
) -> pd.DataFrame:
    """Une la última observación ``<= fecha_corte`` dentro de cada entidad."""
    if objetivos.empty:
        return objetivos.copy()
    salida = objetivos.copy()
    entidades = [entidad] if isinstance(entidad, str) else list(entidad)
    if (
        observaciones.empty
        or not set(entidades) <= set(observaciones)
        or not set(entidades) <= set(salida)
    ):
        for columna in columnas:
            salida[columna] = np.nan
        salida[f"{fecha_observacion}_observada"] = pd.NaT
        return salida

    izq = salida.copy()
    izq[fecha_corte] = pd.to_datetime(izq[fecha_corte]).dt.normalize()
    izq["__orden"] = np.arange(len(izq))
    der = observaciones[[*entidades, fecha_observacion, *columnas]].copy()
    der[fecha_observacion] = pd.to_datetime(der[fecha_observacion]).dt.normalize()
    der = der.dropna(subset=[*entidades, fecha_observacion])
    der = der.rename(columns={fecha_observacion: f"{fecha_observacion}_observada"})
    fecha_der = f"{fecha_observacion}_observada"
    unido = pd.merge_asof(
        izq.sort_values([fecha_corte, *entidades]),
        der.sort_values([fecha_der, *entidades]),
        left_on=fecha_corte,
        right_on=fecha_der,
        by=entidades,
        direction="backward",
        allow_exact_matches=True,
    )
    unido = unido.sort_values("__orden").drop(columns="__orden")
    if (unido[fecha_der] > unido[fecha_corte]).fillna(False).any():
        raise AssertionError("Fuga temporal: una observación posterior entró al panel as-of.")
    return unido


# Huellas e identidad --------------------------------------------------------

def sha256_archivo(ruta: str | Path) -> str:
    """Calcula la huella SHA-256 leyendo el archivo por bloques."""
    digest = sha256()
    with Path(ruta).open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _limpio_json(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {str(k): _limpio_json(v) for k, v in sorted(valor.items(), key=lambda x: str(x[0]))}
    if isinstance(valor, (list, tuple)):
        return [_limpio_json(v) for v in valor]
    if isinstance(valor, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(valor).isoformat()
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, (np.floating, float)):
        return None if not np.isfinite(valor) else round(float(valor), 12)
    if isinstance(valor, np.bool_):
        return bool(valor)
    if pd.isna(valor) if not isinstance(valor, (str, bytes)) else False:
        return None
    return valor


def json_reproducible(valor: Any) -> str:
    """Produce JSON estable para comparar configuraciones y manifiestos."""
    return json.dumps(
        _limpio_json(valor), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def sha256_dataframe(tabla: pd.DataFrame, columnas: tuple[str, ...] | list[str]) -> str:
    """Calcula una huella estable independiente del orden de las filas."""
    disponibles = [c for c in columnas if c in tabla]
    if not disponibles:
        return sha256(b"[]").hexdigest()
    t = tabla[disponibles].copy()
    for columna in t:
        if pd.api.types.is_datetime64_any_dtype(t[columna]):
            t[columna] = pd.to_datetime(t[columna], errors="coerce").dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_numeric_dtype(t[columna]):
            t[columna] = pd.to_numeric(t[columna], errors="coerce").round(10)
        else:
            t[columna] = t[columna].map(
                lambda v: json_reproducible(v) if isinstance(v, (dict, list, tuple)) else v
            )
    t = t.sort_values(disponibles, kind="mergesort", na_position="first").reset_index(drop=True)
    payload = t.to_json(orient="records", date_format="iso", double_precision=10)
    return sha256(payload.encode("utf-8")).hexdigest()


# Normalización --------------------------------------------------------------

CLAVE_RESIDUAL = [
    "campania",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "lote_id",
]

CLAVE_FORECAST = [
    "evaluation_contract_id",
    "campania",
    "modelo",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "lote_id",
]


def normalizar_panel(tabla: pd.DataFrame) -> pd.DataFrame:
    """Normaliza un panel de residual sin alterar su contrato de columnas."""
    requeridas = set(CLAVE_RESIDUAL + ["fundo", "modulo", "p50_kg", "real_kg"])
    faltantes = sorted(requeridas.difference(tabla.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas para calibracion residual: {faltantes}")
    t = tabla.copy()
    t["fecha_emision"] = pd.to_datetime(t.fecha_emision, errors="raise").dt.normalize()
    t["fecha_objetivo"] = pd.to_datetime(t.fecha_objetivo, errors="raise").dt.normalize()
    t["horizonte_semanas"] = pd.to_numeric(t.horizonte_semanas, errors="raise").astype(int)
    t["p50_kg"] = pd.to_numeric(t.p50_kg, errors="coerce")
    t["real_kg"] = pd.to_numeric(t.real_kg, errors="coerce")
    if t.duplicated(CLAVE_RESIDUAL).any():
        raise ValueError("El panel repite una clave lote-emision-objetivo")
    if (t.fecha_emision >= t.fecha_objetivo).any():
        raise ValueError("El panel contiene una emision contemporanea o futura")
    if t.p50_kg.isna().any() or t.p50_kg.lt(0).any():
        raise ValueError("p50_kg debe ser conocido y no negativo")
    t["semana_fin"] = t.fecha_objetivo + pd.to_timedelta(6, unit="D")
    return t.sort_values(["campania", "fecha_emision", "fecha_objetivo", "lote_id"])


def normalizar_forecast_candidate(tabla: pd.DataFrame) -> pd.DataFrame:
    """Normaliza y rechaza un panel que no sea forecast as-of coherente."""
    requeridas = set(CLAVE_FORECAST + ["p50_kg"])
    faltantes = sorted(requeridas.difference(tabla.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas candidate-only: {faltantes}")

    t = tabla.copy()
    t["fecha_emision"] = pd.to_datetime(t.fecha_emision, errors="raise").dt.normalize()
    t["fecha_objetivo"] = pd.to_datetime(t.fecha_objetivo, errors="raise").dt.normalize()
    t["horizonte_semanas"] = pd.to_numeric(t.horizonte_semanas, errors="raise").astype(int)
    t["p50_kg"] = pd.to_numeric(t.p50_kg, errors="coerce")
    if t[CLAVE_FORECAST].isna().any().any():
        raise ValueError("La clave candidate-only contiene nulos")
    if t.p50_kg.isna().any() or t.p50_kg.lt(0).any():
        raise ValueError("p50_kg debe ser conocido y no negativo")
    if (t.fecha_objetivo != lunes_semana(t.fecha_objetivo)).any():
        raise ValueError("fecha_objetivo debe ser el lunes de la semana objetivo")
    if (t.fecha_emision >= t.fecha_objetivo).any():
        raise ValueError("El forecast contiene una emisión contemporánea o futura")
    if t.duplicated(CLAVE_FORECAST).any():
        raise ValueError("El forecast repite una clave contractual completa")

    semana_emision = lunes_semana(t.fecha_emision)
    horizonte_calculado = ((t.fecha_objetivo - semana_emision).dt.days // 7).astype(int)
    if horizonte_calculado.ne(t.horizonte_semanas).any():
        raise ValueError("El horizonte declarado no coincide con emisión y objetivo")

    grano_semana = [
        "evaluation_contract_id",
        "campania",
        "modelo",
        "fecha_objetivo",
        "horizonte_semanas",
    ]
    emisiones = t.groupby(grano_semana, dropna=False).fecha_emision.nunique()
    if emisiones.gt(1).any():
        raise ValueError("Una semana objetivo mezcla emisiones entre lotes")
    return t.sort_values(["campania", "fecha_emision", "lote_id", "fecha_objetivo"]).reset_index(
        drop=True
    )


# Serialización --------------------------------------------------------------

def serializar_json(valor: object) -> str:
    """Serializa metadatos sin dejar ``NaN`` inválidos en columnas JSONB."""

    def limpiar(obj):
        if isinstance(obj, dict):
            return {str(clave): limpiar(valor) for clave, valor in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [limpiar(valor) for valor in obj]
        if isinstance(obj, np.generic):
            obj = obj.item()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, float) and not np.isfinite(obj):
            return None
        if obj is None:
            return None
        try:
            perdido = pd.isna(obj)
            if isinstance(perdido, (bool, np.bool_)) and perdido:
                return None
        except (TypeError, ValueError):
            pass
        return obj

    return json.dumps(limpiar(valor), ensure_ascii=False, default=str, allow_nan=False)


def serializar_jsonb(valor: object) -> str:
    """Serializa una columna JSONB sin envolver dos veces JSON ya generado."""
    if isinstance(valor, str):
        try:
            decodificado = json.loads(valor)
        except (TypeError, ValueError):
            pass
        else:
            if isinstance(decodificado, (dict, list)):
                valor = decodificado
    return serializar_json(valor)


def limpiar_valor(valor: object) -> object:
    """Convierte valores pandas/numpy en valores aceptables para psycopg."""
    if isinstance(valor, dict):
        return {str(clave): limpiar_valor(elemento) for clave, elemento in valor.items()}
    if isinstance(valor, np.ndarray):
        return [limpiar_valor(elemento) for elemento in valor.tolist()]
    if isinstance(valor, list):
        return [limpiar_valor(elemento) for elemento in valor]
    if isinstance(valor, tuple):
        return tuple(limpiar_valor(elemento) for elemento in valor)
    if isinstance(valor, np.generic):
        valor = valor.item()
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()
    ausente = pd.isna(valor)
    if isinstance(ausente, (bool, np.bool_)) and ausente:
        return None
    if isinstance(valor, float) and not np.isfinite(valor):
        return None
    return valor


__all__ = [
    "CLAVE_FORECAST",
    "CLAVE_RESIDUAL",
    "json_reproducible",
    "limpiar_valor",
    "lunes_semana",
    "normalizar_forecast_candidate",
    "normalizar_panel",
    "serializar_json",
    "serializar_jsonb",
    "sha256_archivo",
    "sha256_dataframe",
    "ultimo_disponible",
]
