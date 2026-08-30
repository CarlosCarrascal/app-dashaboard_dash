"""Fachada histórica del adaptador operativo basado en libros ProySemanal.

La implementación vive en ``proyeccion.operativo``. Este módulo conserva las
rutas antiguas y los aliases que consumen el dashboard, los comandos y los
scripts. La lectura opcional de Excel permanece lazy en ``operativo.lectura``.
"""

from __future__ import annotations

from .compartido import sha256_archivo
from .contratos import DatosProyeccion, FuenteInfo
from .motor_proyeccion_semanal import ejecutar_proyeccion_semanal_dataframe
from .operativo.excel import (  # noqa: F401 - aliases históricos
    FUNDOS_ARCHIVO,
    LIBROS_OPERATIVOS,
    MODELO_OPERATIVO_ACTUAL,
    VARIANTES_NO_PROMOVIDAS,
    _fecha,
    _firma_manifest,
    datos_proyeccion_operativo,
    leer_libro_operativo,
    seleccionar_libros_operativos,
)
from .operativo.modelo import construir_modelo_operativo_excel
from .parametros_automaticos import (
    calibrar_universo_operativo,
    reemplazar_parametros_excel_por_db,
)
from .versiones import banda_horizonte

__all__ = [
    "DatosProyeccion",
    "FuenteInfo",
    "FUNDOS_ARCHIVO",
    "LIBROS_OPERATIVOS",
    "MODELO_OPERATIVO_ACTUAL",
    "VARIANTES_NO_PROMOVIDAS",
    "banda_horizonte",
    "calibrar_universo_operativo",
    "construir_modelo_operativo_excel",
    "datos_proyeccion_operativo",
    "ejecutar_proyeccion_semanal_dataframe",
    "leer_libro_operativo",
    "reemplazar_parametros_excel_por_db",
    "seleccionar_libros_operativos",
    "sha256_archivo",
]
