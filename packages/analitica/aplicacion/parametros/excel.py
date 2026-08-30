"""Ingesta explícita y versionada de parámetros de los libros ProySemanal.

Los libros se leen durante una corrida de ingestión, nunca desde un callback del
dashboard. El selector usa únicamente las carpetas ``ProyeccionSemanal_NN`` sin
sufijo y excluye variantes no promovidas. Los faltantes quedan en el manifiesto;
no se convierten en una predicción cero.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from analitica.aplicacion.parametros.normalizacion import normalizar_parametros_excel
from analitica.dominio.compartido import sha256_archivo

FUNDOS = {
    "Arena": ("arena",),
    "Ayllu": ("ayllu",),
    "Kawsay": ("kawsay",),
    "Quri": ("quri", "qury"),
}
VARIANTES_NO_PROMOVIDAS = ("edi", "v2", "v3", "oli", "copia", "copy", "vdr", "eangulo")


def _normalizar_nombre(valor: object) -> str:
    return " ".join(str(valor or "").casefold().replace("_", " ").split())


def _es_variante(nombre: str) -> bool:
    normalizado = _normalizar_nombre(Path(nombre).stem)
    return any(
        re.search(rf"(?:^|[ _-]){re.escape(variante)}(?:$|[ _-])", normalizado)
        or normalizado.endswith(variante)
        for variante in VARIANTES_NO_PROMOVIDAS
    )


def seleccionar_libros_parametros(
    root: str | Path,
    *,
    semanas: tuple[int, ...] | list[int] | None = None,
    promociones: Mapping[tuple[int, str], str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Selecciona como máximo un libro por emisión y fundo.

    Devuelve ``(manifest, faltantes)``. Un libro alternativo solo entra mediante
    ``promociones[(semana, fundo)] = nombre``; esto evita sumar ``v2``/``EDI``/copias
    como si fueran emisiones distintas.
    """

    raiz = Path(root).expanduser().resolve()
    if not raiz.is_dir():
        raise FileNotFoundError(raiz)
    dirs = []
    for carpeta in raiz.iterdir():
        if (
            not carpeta.is_dir()
            or re.fullmatch(r"ProyeccionSemanal_\d+", carpeta.name, re.I) is None
        ):
            continue
        numero = int(re.search(r"(\d+)$", carpeta.name).group(1))
        dirs.append((numero, carpeta))
    solicitadas = set(int(x) for x in semanas) if semanas is not None else None
    promociones = promociones or {}
    filas: list[dict[str, object]] = []
    faltantes: list[dict[str, object]] = []

    for semana, carpeta in sorted(dirs):
        if solicitadas is not None and semana not in solicitadas:
            continue
        archivos = list(carpeta.glob("*.xlsm"))
        for fundo, aliases in FUNDOS.items():
            promovido = promociones.get((semana, fundo))
            if promovido:
                candidatos = [carpeta / promovido]
                if not candidatos[0].is_file():
                    raise FileNotFoundError(candidatos[0])
            else:
                candidatos = []
                for archivo in archivos:
                    nombre = _normalizar_nombre(archivo.stem)
                    if not re.match(rf"^proy ?semanal[ _-]*0*{semana}(?:\D|$)", nombre):
                        continue
                    if not any(alias in nombre for alias in aliases):
                        continue
                    if _es_variante(archivo.name):
                        continue
                    candidatos.append(archivo)
            if len(candidatos) > 1:
                raise ValueError(
                    f"Más de un libro base para S{semana:02d}/{fundo}: "
                    + ", ".join(x.name for x in candidatos)
                )
            if not candidatos:
                faltantes.append({"semana_emision": semana, "fundo": fundo, "estado": "sin_datos"})
                continue
            archivo = candidatos[0]
            filas.append(
                {
                    "semana_emision": semana,
                    "fundo_operativo": fundo,
                    "archivo_fuente": archivo.name,
                    "ruta_fuente": str(archivo),
                    "sha256_fuente": sha256_archivo(archivo),
                    "variante": "promovida" if promovido else "base",
                }
            )
    return pd.DataFrame(filas), pd.DataFrame(faltantes)


def cargar_parametros_libro(ruta: str | Path, *, manifest: Mapping[str, object]) -> pd.DataFrame:
    """Lee únicamente ``Parametros`` y agrega la identidad del manifiesto."""

    try:
        from python_calamine import CalamineWorkbook
    except ImportError as exc:  # pragma: no cover - dependencia de ejecución
        raise RuntimeError("python-calamine es necesario para leer parámetros xlsm") from exc
    workbook = CalamineWorkbook.from_path(str(ruta))
    crudo = workbook.get_sheet_by_name("Parametros").to_python()
    if not crudo or not crudo[0]:
        return pd.DataFrame()
    tabla = pd.DataFrame(crudo[1:], columns=crudo[0])
    tabla = normalizar_parametros_excel(
        tabla,
        fuente="excel_proysemanal",
        archivo_fuente=str(manifest.get("archivo_fuente")),
        sha256_fuente=str(manifest.get("sha256_fuente")),
    )
    tabla["semana_emision"] = int(manifest["semana_emision"])
    tabla["fundo_operativo"] = str(manifest["fundo_operativo"])
    tabla["variante"] = str(manifest.get("variante", "base"))
    return tabla


def cargar_parametros_historicos(
    root: str | Path,
    *,
    semanas: tuple[int, ...] | list[int] | None = None,
    fechas_emision: Mapping[int, object] | None = None,
    promociones: Mapping[tuple[int, str], str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carga parámetros y manifiesto para el replay, sin cargar kilos publicados.

    ``fechas_emision`` debe provenir del historial R09/Access. Si una emisión no tiene
    fecha verificable, queda con fecha nula y el replay as-of la excluye del prior.
    """

    manifest, faltantes = seleccionar_libros_parametros(
        root, semanas=semanas, promociones=promociones
    )
    fechas_emision = fechas_emision or {}
    partes = []
    for fila in manifest.to_dict("records"):
        tabla = cargar_parametros_libro(fila["ruta_fuente"], manifest=fila)
        if tabla.empty:
            continue
        tabla["fecha_emision"] = pd.to_datetime(
            fechas_emision.get(int(fila["semana_emision"])), errors="coerce"
        )
        tabla["fecha_vigencia"] = tabla["fecha_emision"]
        partes.append(tabla)
    parametros = pd.concat(partes, ignore_index=True, sort=False) if partes else pd.DataFrame()
    if not parametros.empty:
        parametros["lote"] = (
            parametros.get("Lote", parametros.get("lote", pd.Series(dtype=object)))
            .astype(str)
            .str.strip()
        )
        parametros["modulo"] = (
            parametros.get("Modulo", parametros.get("modulo", pd.Series(dtype=object)))
            .astype(str)
            .str.strip()
        )
    return parametros, manifest, faltantes


__all__ = [
    "FUNDOS",
    "seleccionar_libros_parametros",
    "cargar_parametros_libro",
    "cargar_parametros_historicos",
]
