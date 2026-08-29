"""I/O y snapshots de los libros del screening de parámetros Excel."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from .excel_parameter_deltas_normalization import (
    ALIASES_FUNDO,
    PARAMETROS,
    SEMANAS,
    _clave_lote,
    _columna,
    _es_variante,
    _normalizar_texto,
)


def sha256_archivo(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def inventariar_libros(
    root: str | Path,
    *,
    semanas: Iterable[int] = SEMANAS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Selecciona una base inequívoca por emisión/fundo y audita lo excluido."""

    raiz = Path(root).expanduser().resolve()
    if not raiz.is_dir():
        raise FileNotFoundError(raiz)
    filas: list[dict[str, object]] = []
    incidencias: list[dict[str, object]] = []
    for semana in sorted(set(map(int, semanas))):
        carpeta = raiz / f"ProyeccionSemanal_{semana:02d}"
        directos = sorted(carpeta.glob("*.xlsm")) if carpeta.is_dir() else []
        alternativos = sorted(
            p
            for p in raiz.glob(f"ProyeccionSemanal_{semana:02d}*")
            if p.is_dir() and p.resolve() != carpeta.resolve()
            for p in p.glob("*.xlsm")
        )
        for fundo, aliases in ALIASES_FUNDO.items():
            coinciden_fundo = [
                p for p in directos if any(alias in _normalizar_texto(p.stem) for alias in aliases)
            ]
            exactos = []
            for ruta in coinciden_fundo:
                nombre = _normalizar_texto(ruta.stem)
                declara_semana = re.match(
                    rf"^proy ?semanal[ -]*0*{semana}(?:\D|$)", nombre
                )
                if declara_semana and not _es_variante(ruta.name):
                    exactos.append(ruta)
            if len(exactos) == 1:
                ruta = exactos[0]
                filas.append(
                    {
                        "semana_emision": semana,
                        "fundo_operativo": fundo,
                        "ruta_fuente": str(ruta),
                        "archivo_fuente": ruta.name,
                        "sha256_fuente": sha256_archivo(ruta),
                        "estado_trazabilidad": "canonico",
                    }
                )
            else:
                razon = "sin_archivo_base" if not exactos else "multiples_bases"
                incidencias.append(
                    {
                        "semana_emision": semana,
                        "fundo_operativo": fundo,
                        "estado": razon,
                        "archivos_directos_fundo": [p.name for p in coinciden_fundo],
                        "alternativas_no_promovidas": [
                            str(p.relative_to(raiz))
                            for p in alternativos
                            if any(alias in _normalizar_texto(p.stem) for alias in aliases)
                        ],
                    }
                )
    manifest = pd.DataFrame(filas)
    problemas = pd.DataFrame(incidencias)
    if not manifest.empty and manifest.duplicated(["semana_emision", "fundo_operativo"]).any():
        raise AssertionError("El inventario seleccionó más de una base por emisión/fundo")
    return manifest, problemas


def _tabla_hoja(ruta: Path, hoja: str, *, fila_cabecera: int) -> pd.DataFrame:
    try:
        from python_calamine import CalamineWorkbook
    except ImportError as exc:  # pragma: no cover - dependencia opcional de ejecución
        raise RuntimeError("python-calamine es necesario para leer los xlsm") from exc
    crudo = CalamineWorkbook.from_path(str(ruta)).get_sheet_by_name(hoja).to_python()
    if len(crudo) <= fila_cabecera:
        return pd.DataFrame()
    cabecera = [str(x).strip() for x in crudo[fila_cabecera]]
    ancho = len(cabecera)
    columnas = []
    usados: dict[str, int] = {}
    for indice, nombre in enumerate(cabecera):
        base = nombre or f"__vacia_{indice}"
        usados[base] = usados.get(base, 0) + 1
        columnas.append(base if usados[base] == 1 else f"{base}__{usados[base]}")
    filas = [
        list(fila[:ancho]) + [None] * max(0, ancho - len(fila))
        for fila in crudo[fila_cabecera + 1 :]
    ]
    return pd.DataFrame([fila[:ancho] for fila in filas], columns=columnas)


def leer_snapshot_libro(ruta: str | Path) -> pd.DataFrame:
    """Devuelve una fila por lote con parámetros y calendario, sin leer BDProy."""

    path = Path(ruta)
    parametros = _tabla_hoja(path, "Parametros", fila_cabecera=0)
    panel = _tabla_hoja(path, "Panel", fila_cabecera=1)
    if parametros.empty or panel.empty:
        raise ValueError(f"{path.name}: Parametros o Panel vacíos")
    parametros["clave_lote"] = _clave_lote(parametros)
    panel["clave_lote"] = _clave_lote(panel)
    parametros = parametros.loc[~parametros.clave_lote.eq("|")].copy()
    panel = panel.loc[~panel.clave_lote.eq("|")].copy()
    if parametros.clave_lote.duplicated().any() or panel.clave_lote.duplicated().any():
        raise ValueError(f"{path.name}: lotes duplicados en Parametros o Panel")
    salida = parametros[["clave_lote"]].copy()
    for parametro in PARAMETROS:
        original = _columna(parametros, parametro)
        salida[parametro] = (
            pd.to_numeric(parametros[original], errors="coerce") if original else np.nan
        )
    original = _columna(parametros, "Turno")
    if original:
        salida["Turno"] = parametros[original].map(_normalizar_texto)
    calendario = panel[["clave_lote"]].copy()
    columnas_fepas = []
    for columna in panel.columns:
        match = re.fullmatch(r"FePas(\d+)", str(columna).strip(), re.I)
        if match:
            canonico = f"FePas{int(match.group(1))}"
            calendario[canonico] = pd.to_datetime(panel[columna], errors="coerce")
            columnas_fepas.append(canonico)
    if not columnas_fepas:
        raise ValueError(f"{path.name}: Panel sin columnas FePas")
    salida = salida.merge(calendario, on="clave_lote", how="outer", validate="one_to_one")
    salida["en_parametros"] = salida.clave_lote.isin(parametros.clave_lote)
    salida["en_panel"] = salida.clave_lote.isin(panel.clave_lote)
    return salida.sort_values("clave_lote", kind="stable").reset_index(drop=True)


def cargar_snapshots(
    manifest: pd.DataFrame,
) -> dict[tuple[int, str], pd.DataFrame]:
    snapshots: dict[tuple[int, str], pd.DataFrame] = {}
    for fila in manifest.itertuples(index=False):
        snapshots[(int(fila.semana_emision), str(fila.fundo_operativo))] = leer_snapshot_libro(
            fila.ruta_fuente
        )
    return snapshots

__all__ = [
    "_tabla_hoja",
    "cargar_snapshots",
    "inventariar_libros",
    "leer_snapshot_libro",
    "sha256_archivo",
]
