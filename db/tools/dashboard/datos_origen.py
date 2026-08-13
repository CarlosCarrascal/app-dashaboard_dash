"""Selección del Excel de campaña: archivo subido o la copia del repositorio.

Vive fuera de `vistas/` porque no es una sección del tablero: es el control que decide
qué datos entran, y lo consume `app.py` antes de saber qué sección mostrar.

El caso normal es usar la copia del repositorio, así que ése es el estado por omisión y
subir un archivo queda detrás de un desplegable. Antes el cargador estaba siempre a la
vista y ocupaba más espacio que la navegación entera.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import streamlit as st

from config import ICONO


def elegir_origen(
    xlsx_repo: Path, leer_archivo: Callable[[str, float], bytes]
) -> tuple[bytes, str] | None:
    """Devuelve (contenido, nombre) del Excel elegido, o None si todavía no hay ninguno.

    `leer_archivo` se recibe por parámetro en vez de importarse para que este módulo no
    dependa de `servicios`: así el sentido de las dependencias sigue siendo uno solo.
    """
    hay_repo = xlsx_repo.is_file()

    with st.expander(f"{ICONO['datos']}  Origen de los datos", expanded=not hay_repo):
        archivo = st.file_uploader(
            "Subir otro Excel",
            type=["xlsx", "xlsm"],
            help="Hojas requeridas: KgHa, Temp Max-Min, Rad y ET, Riego y DPV.",
        )
        if hay_repo and archivo is None:
            st.caption(
                f"Usando `{xlsx_repo.name}` del repositorio. Subí un archivo acá para "
                "reemplazarlo."
            )

    if archivo is not None:
        return archivo.getvalue(), archivo.name
    if hay_repo:
        # Cacheado por (ruta, mtime): sin eso se releería el archivo entero en cada
        # interacción, porque Streamlit reejecuta el script de arriba a abajo.
        return leer_archivo(str(xlsx_repo), xlsx_repo.stat().st_mtime), str(xlsx_repo)
    return None
