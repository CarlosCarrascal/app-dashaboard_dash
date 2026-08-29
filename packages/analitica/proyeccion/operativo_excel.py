"""Fachada histórica del adaptador operativo basado en libros ProySemanal.

La implementación vive en ``proyeccion.operativo``. Este módulo conserva las
rutas antiguas y los aliases que consumen el dashboard, los comandos y los
scripts. La lectura opcional de Excel permanece lazy en ``operativo.lectura``.
"""

from __future__ import annotations

from .compartido.hashes import sha256_archivo
from .contratos import DatosProyeccion, FuenteInfo
from .motor_proyeccion_semanal import ejecutar_proyeccion_semanal_dataframe
from .operativo.contratos import MODELO_OPERATIVO_ACTUAL
from .operativo.lectura import leer_libro_operativo
from .operativo.modelo import construir_modelo_operativo_excel
from .operativo.normalizacion import _fecha  # noqa: F401 - alias histórico
from .operativo.salida import (  # noqa: F401 - alias histórico
    _firma_manifest,
    datos_proyeccion_operativo,
)
from .operativo.seleccion import (
    FUNDOS_ARCHIVO,
    LIBROS_OPERATIVOS,
    VARIANTES_NO_PROMOVIDAS,
    seleccionar_libros_operativos,
)
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
