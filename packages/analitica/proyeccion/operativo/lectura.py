"""Lectura lazy de las hojas requeridas de un libro operativo."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..compartido.hashes import sha256_archivo


def leer_libro_operativo(ruta: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Lee las tres hojas necesarias sin abrir Excel ni modificar el libro."""
    try:
        from python_calamine import CalamineWorkbook
    except ImportError as exc:  # pragma: no cover - depende del entorno de ejecución
        raise RuntimeError("python-calamine es necesario para validar libros xlsm") from exc

    workbook = CalamineWorkbook.from_path(str(ruta))
    parametros = workbook.get_sheet_by_name("Parametros").to_python()
    panel = workbook.get_sheet_by_name("Panel").to_python()
    bdproy = workbook.get_sheet_by_name("BDProy").to_python()

    return (
        pd.DataFrame(parametros[1:], columns=parametros[0]),
        pd.DataFrame(panel[2:], columns=panel[1]),
        pd.DataFrame(bdproy[1:], columns=bdproy[0]),
    )


__all__ = ["leer_libro_operativo", "sha256_archivo"]
