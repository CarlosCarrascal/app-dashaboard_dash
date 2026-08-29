"""Catálogo científico versionado y validado."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analitica import settings

RUTA_CATALOGO = settings._RAIZ_REPOSITORIO / "docs" / "cientifico" / "catalogo_evidencia.json"
CAMPOS_MINIMOS = {
    "id",
    "titulo",
    "anio",
    "url",
    "cultivo_variedad",
    "metodo",
    "limitaciones",
    "transferibilidad",
    "uso_en_plataforma",
}


def cargar_catalogo(ruta: Path | None = None) -> dict:
    ruta = Path(ruta or RUTA_CATALOGO)
    catalogo = json.loads(ruta.read_text(encoding="utf-8"))
    ids = set()
    for i, estudio in enumerate(catalogo.get("estudios", [])):
        faltan = CAMPOS_MINIMOS - estudio.keys()
        if faltan:
            raise ValueError(f"Estudio {i} sin campos: {sorted(faltan)}")
        if estudio["id"] in ids:
            raise ValueError(f"ID científico duplicado: {estudio['id']}")
        ids.add(estudio["id"])
    return catalogo


def matriz_transferibilidad(ruta: Path | None = None) -> pd.DataFrame:
    estudios = cargar_catalogo(ruta)["estudios"]
    columnas = [
        "id",
        "titulo",
        "anio",
        "doi",
        "cultivo_variedad",
        "ubicacion",
        "muestra",
        "metodo",
        "resultados",
        "limitaciones",
        "transferibilidad",
        "uso_en_plataforma",
        "url",
    ]
    filas = []
    for estudio in estudios:
        fila = {c: estudio.get(c) for c in columnas}
        fila["limitaciones"] = "; ".join(estudio.get("limitaciones", []))
        filas.append(fila)
    return pd.DataFrame(filas, columns=columnas)
