"""Exportación a un Excel estructurado, generado en memoria.

No es un volcado del DataFrame: es un informe con portada, metodología, calidad de datos
y limitaciones, para que el archivo se sostenga solo cuando alguien lo abra dentro de seis
meses sin tener el tablero delante.

Sin Streamlit: recibe datos y devuelve bytes.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd

ANCHO_MINIMO, ANCHO_MAXIMO = 10, 52


@dataclass
class Hoja:
    """Una hoja del libro, con su título y una nota que la explica."""

    nombre: str
    titulo: str
    nota: str
    datos: pd.DataFrame
    porcentajes: tuple[str, ...] = ()


def _formatos(libro) -> dict:
    return {
        "titulo": libro.add_format({"bold": True, "font_size": 15, "font_color": "#1A2733"}),
        "nota": libro.add_format({"font_size": 10, "font_color": "#5A6472",
                                  "text_wrap": True, "valign": "top"}),
        "cabecera": libro.add_format({
            "bold": True, "font_size": 10, "font_color": "#FFFFFF", "bg_color": "#3B7DD8",
            "border": 1, "border_color": "#2C5FA8", "text_wrap": True, "valign": "vcenter",
        }),
        "texto": libro.add_format({"font_size": 10, "valign": "top", "text_wrap": True}),
        "numero": libro.add_format({"font_size": 10, "num_format": "#,##0.000"}),
        "entero": libro.add_format({"font_size": 10, "num_format": "#,##0"}),
        "porcentaje": libro.add_format({"font_size": 10, "num_format": "0.0%"}),
        "seccion": libro.add_format({"bold": True, "font_size": 11,
                                     "font_color": "#1A2733", "bottom": 2,
                                     "border_color": "#3B7DD8"}),
    }


def _ancho(serie: pd.Series, encabezado: str) -> int:
    # `.astype(str)` en una columna float64 deja los NaN como float, no como texto
    # "nan" — hay que quitarlos antes de medir, no después.
    muestra = serie.head(300).dropna().astype(str)
    largo = max([len(encabezado), *(len(v) for v in muestra)]) + 3
    return max(ANCHO_MINIMO, min(ANCHO_MAXIMO, largo))


def _escribir(hoja_xl, libro, fmt: dict, h: Hoja) -> None:
    """Vuelca una hoja con título, nota, cabecera congelada y autofiltro."""
    hoja_xl.write(0, 0, h.titulo, fmt["titulo"])
    hoja_xl.merge_range(1, 0, 1, max(1, len(h.datos.columns) - 1), h.nota, fmt["nota"])
    hoja_xl.set_row(1, 30)

    fila0 = 3
    for j, col in enumerate(h.datos.columns):
        hoja_xl.write(fila0, j, str(col), fmt["cabecera"])
        serie = h.datos[col]
        if col in h.porcentajes:
            formato = fmt["porcentaje"]
        elif pd.api.types.is_float_dtype(serie):
            formato = fmt["numero"]
        elif pd.api.types.is_integer_dtype(serie):
            formato = fmt["entero"]
        else:
            formato = fmt["texto"]
        hoja_xl.set_column(j, j, _ancho(serie, str(col)), formato)

    for i, (_, fila) in enumerate(h.datos.iterrows(), start=fila0 + 1):
        for j, col in enumerate(h.datos.columns):
            valor = fila[col]
            if pd.isna(valor):
                hoja_xl.write_blank(i, j, None)
            elif isinstance(valor, bool):
                hoja_xl.write(i, j, "sí" if valor else "no")
            else:
                hoja_xl.write(i, j, valor)

    hoja_xl.set_row(fila0, 32)
    hoja_xl.freeze_panes(fila0 + 1, 0)
    if len(h.datos):
        hoja_xl.autofilter(fila0, 0, fila0 + len(h.datos), len(h.datos.columns) - 1)


def _portada(hoja_xl, libro, fmt: dict, meta: list[tuple[str, str]]) -> None:
    hoja_xl.hide_gridlines(2)
    hoja_xl.set_column(0, 0, 30)
    hoja_xl.set_column(1, 1, 88)
    hoja_xl.write(0, 0, "Aqu Anqa · Relación clima-riego / rendimiento", fmt["titulo"])
    hoja_xl.write(1, 0, "Exportación del tablero de análisis", fmt["nota"])
    fila = 3
    for clave, valor in meta:
        if valor is None:
            hoja_xl.write(fila, 0, clave, fmt["seccion"])
            hoja_xl.write(fila, 1, "", fmt["seccion"])
        else:
            hoja_xl.write(fila, 0, clave, fmt["texto"])
            hoja_xl.write(fila, 1, valor, fmt["texto"])
        fila += 1


def construir_libro(hojas: list[Hoja], meta: list[tuple[str, str]]) -> bytes:
    """Arma el .xlsx completo en memoria y devuelve sus bytes."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        libro = writer.book
        fmt = _formatos(libro)

        portada = libro.add_worksheet("Portada")
        _portada(portada, libro, fmt, meta)

        for h in hojas:
            # Excel limita los nombres de hoja a 31 caracteres y prohíbe algunos signos.
            nombre = h.nombre[:31]
            hoja_xl = libro.add_worksheet(nombre)
            _escribir(hoja_xl, libro, fmt, h)

    buffer.seek(0)
    return buffer.getvalue()
