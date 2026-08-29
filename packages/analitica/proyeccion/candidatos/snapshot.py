"""Snapshot y aislamiento de datos para el preflight de candidatos."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import Any

import pandas as pd

from ..compartido import identidad as _identidad
from .contratos import DATOS_SNAPSHOT_SCHEMA

json_reproducible = _identidad.json_reproducible


def cargar_o_construir_snapshot_datos(
    raiz_cache: str | Path,
    clave: str,
    constructor: Callable[[], Any],
) -> tuple[Any, dict[str, Any]]:
    """Reutiliza un snapshot Parquet sin consultar otra vez todas las vistas.

    La clave la fija el contrato aprobado y sus releases. El manifiesto se
    escribe al final, de modo que una preparación interrumpida nunca se toma
    como snapshot válido.
    """

    from ..contratos import DatosProyeccion, FuenteInfo

    directorio = Path(raiz_cache) / clave
    manifiesto_ruta = directorio / "manifest.json"
    if manifiesto_ruta.is_file():
        try:
            manifiesto = json.loads(manifiesto_ruta.read_text(encoding="utf-8"))
            if (
                manifiesto.get("schema") == DATOS_SNAPSHOT_SCHEMA
                and manifiesto.get("clave") == clave
            ):
                fuente_datos = manifiesto["fuente"]
                fuente = FuenteInfo(
                    nombre=str(fuente_datos["nombre"]),
                    firma=str(fuente_datos["firma"]),
                    corte=(
                        pd.Timestamp(fuente_datos["corte"]).to_pydatetime()
                        if fuente_datos.get("corte")
                        else None
                    ),
                    fallback=bool(fuente_datos.get("fallback", False)),
                    advertencias=tuple(fuente_datos.get("advertencias", ())),
                    conteos={str(k): int(v) for k, v in fuente_datos.get("conteos", {}).items()},
                )
                tablas = {
                    nombre: pd.read_parquet(directorio / archivo)
                    for nombre, archivo in manifiesto["tablas"].items()
                }
                return DatosProyeccion(fuente=fuente, **tablas), {
                    "cache_hit": True,
                    "clave": clave,
                    "ruta": str(directorio),
                }
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            # Una caché parcial o de otra versión se reconstruye; nunca invalida la corrida.
            pass

    datos = constructor()
    directorio.mkdir(parents=True, exist_ok=True)
    tablas: dict[str, str] = {}
    for campo in fields(datos):
        if campo.name == "fuente":
            continue
        valor = getattr(datos, campo.name)
        if not isinstance(valor, pd.DataFrame):
            continue
        archivo = f"{campo.name}.parquet"
        temporal = directorio / f".{archivo}.tmp"
        valor.to_parquet(temporal, index=False)
        temporal.replace(directorio / archivo)
        tablas[campo.name] = archivo
    fuente = datos.fuente
    manifiesto = {
        "schema": DATOS_SNAPSHOT_SCHEMA,
        "clave": clave,
        "fuente": {
            "nombre": fuente.nombre,
            "firma": fuente.firma,
            "corte": fuente.corte.isoformat() if fuente.corte else None,
            "fallback": fuente.fallback,
            "advertencias": list(fuente.advertencias),
            "conteos": fuente.conteos,
        },
        "tablas": tablas,
    }
    temporal_manifiesto = directorio / ".manifest.json.tmp"
    temporal_manifiesto.write_text(json_reproducible(manifiesto), encoding="utf-8")
    temporal_manifiesto.replace(manifiesto_ruta)
    return datos, {"cache_hit": False, "clave": clave, "ruta": str(directorio)}


def clonar_datos_proyeccion(datos):
    """Clona el contrato y todos sus DataFrames antes de adjuntar priors.

    Algunos calibradores guardan caches privados en el objeto. Esos valores tambien
    se copian para que un challenger no pueda mutar el contenedor que representa al
    baseline de la sesion.
    """

    valores: dict[str, Any] = {}
    for campo in fields(datos):
        valor = getattr(datos, campo.name)
        valores[campo.name] = (
            valor.copy(deep=True) if isinstance(valor, pd.DataFrame) else copy.deepcopy(valor)
        )
    clon = type(datos)(**valores)
    for nombre, valor in vars(datos).items():
        if nombre not in valores:
            setattr(clon, nombre, copy.deepcopy(valor))
    return clon


__all__ = ["cargar_o_construir_snapshot_datos", "clonar_datos_proyeccion"]
