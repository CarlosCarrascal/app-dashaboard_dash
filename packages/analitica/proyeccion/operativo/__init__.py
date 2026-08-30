"""Frontera del caso de uso operativo basado en libros ProySemanal."""

import sys
import types

from ..motor_proyeccion_semanal import (
    LoteParametrosProyeccion,
    RegistroBDProy,
    ajustar_dia_habil,
    calcular_fechas_reingreso,
    ejecutar_proyeccion_semanal_dataframe,
    extraer_fechas_pasadas,
    generar_matriz_resumen_pdi,
    norm_cdf,
    proyectar_lote_pasadas,
    safe_date,
    safe_float,
    semana_iso_21,
)
from .excel import (
    CAMPOS_NUMERICOS,
    CLAVES_CORRIDA,
    FUNDOS_ARCHIVO,
    LIBROS_OPERATIVOS,
    MODELO_OPERATIVO_ACTUAL,
    ResultadoValidacionOperativa,
    datos_proyeccion_operativo,
    leer_libro_operativo,
    seleccionar_libros_operativos,
)
from .modelo import construir_modelo_operativo_excel
from .validacion import validar_libro_operativo, validar_libros_semana

for _nombre in ("contratos", "lectura", "normalizacion", "salida", "seleccion"):
    _excel = sys.modules[f"{__name__}.excel"]
    _compat = types.ModuleType(f"{__name__}.{_nombre}", _excel.__doc__)
    _compat.__package__ = __name__
    _compat.__file__ = _excel.__file__
    _compat.__all__ = _excel.__all__
    _compat.__dict__.update({nombre: getattr(_excel, nombre) for nombre in _excel.__all__})
    sys.modules[_compat.__name__] = _compat
    globals()[_nombre] = _compat

__all__ = [
    "LoteParametrosProyeccion",
    "RegistroBDProy",
    "CAMPOS_NUMERICOS",
    "CLAVES_CORRIDA",
    "FUNDOS_ARCHIVO",
    "LIBROS_OPERATIVOS",
    "MODELO_OPERATIVO_ACTUAL",
    "ResultadoValidacionOperativa",
    "ajustar_dia_habil",
    "calcular_fechas_reingreso",
    "construir_modelo_operativo_excel",
    "datos_proyeccion_operativo",
    "ejecutar_proyeccion_semanal_dataframe",
    "extraer_fechas_pasadas",
    "generar_matriz_resumen_pdi",
    "leer_libro_operativo",
    "norm_cdf",
    "proyectar_lote_pasadas",
    "safe_date",
    "safe_float",
    "seleccionar_libros_operativos",
    "semana_iso_21",
    "validar_libro_operativo",
    "validar_libros_semana",
]
