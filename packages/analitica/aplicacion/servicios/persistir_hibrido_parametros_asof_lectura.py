"""Lectura de contratos, snapshots, baselines y emisiones as-of."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd


def serializar_json(valor: Any, *, json_reproducible: Callable[[Any], str]) -> str:
    """Usa el serializador histórico como única representación estable."""

    return json_reproducible(valor)


def hash_json(
    valor: Any,
    *,
    serializar: Callable[[Any], str],
) -> str:
    return sha256(serializar(valor).encode("utf-8")).hexdigest()


def firma_directorio(
    raiz: str | None,
    *,
    hash_json_fn: Callable[[Any], str],
) -> str | None:
    """Calcula la firma histórica de archivos Excel sin abrirlos."""

    if not raiz:
        return None
    base = Path(raiz)
    if not base.exists():
        return "ruta_inexistente"
    registros = [
        (
            str(ruta.relative_to(base)).replace("\\", "/"),
            ruta.stat().st_size,
            ruta.stat().st_mtime_ns,
        )
        for ruta in sorted(base.rglob("*.xls*"))
        if ruta.is_file()
    ]
    return hash_json_fn(registros)


def consultar_contrato_baselines(
    dsn: str,
    referencias: Mapping[str, int],
    campania: str,
    *,
    loader: Callable[..., Any],
) -> Any:
    """Resuelve el contrato aprobado sin construir ni modificar baselines."""

    return loader(dsn, referencias, campania)


def consultar_snapshot_fuente(
    fuente_clave: str,
    *,
    cache_root: Path,
    snapshot_loader: Callable[..., Any],
    data_loader: Callable[..., Any],
) -> Any:
    """Carga un snapshot de fuente o lo construye una sola vez."""

    return snapshot_loader(
        cache_root,
        fuente_clave,
        lambda: data_loader("postgres"),
    )


def consultar_baselines(
    dsn: str,
    referencias: Mapping[str, int],
    campania: str,
    *,
    cerrado_hasta: Any,
    fechas_emision: Any = None,
    horizontes: tuple[int, ...],
    loader: Callable[..., Any],
) -> dict[str, pd.DataFrame]:
    """Carga baselines publicados por ``run_id`` bajo el corte temporal."""

    return loader(
        dsn,
        referencias,
        campania,
        horizontes=horizontes,
        cerrado_hasta=cerrado_hasta,
        fechas_emision=fechas_emision,
    )


def emisiones_desde_forecast(
    datos: Any,
    campania: str,
    *,
    seleccionar_versiones: Callable[[pd.DataFrame], pd.DataFrame],
    lunes_semana: Callable[[Any], Any],
    fecha_emision_desde_objetivo: Callable[[Any, int], Any],
) -> pd.DataFrame:
    """Extrae cortes oficiales de la fuente, sin construir predicciones R09."""

    forecast = seleccionar_versiones(datos.forecast)
    forecast = forecast[forecast.campania.astype(str).eq(str(campania))].copy()
    if forecast.empty:
        raise ValueError(f"No existen emisiones versionadas para {campania}.")
    forecast["fecha_objetivo"] = lunes_semana(forecast.fecha_cos)
    forecast["fecha_emision"] = [
        fecha_emision_desde_objetivo(objetivo, int(semana))
        for objetivo, semana in zip(
            forecast.fecha_objetivo,
            forecast.semana_emision,
            strict=True,
        )
    ]
    emisiones = forecast[["campania", "fecha_emision"]].drop_duplicates()
    return emisiones.sort_values("fecha_emision").reset_index(drop=True)


__all__ = [
    "consultar_baselines",
    "consultar_contrato_baselines",
    "consultar_snapshot_fuente",
    "emisiones_desde_forecast",
    "firma_directorio",
    "hash_json",
    "serializar_json",
]
