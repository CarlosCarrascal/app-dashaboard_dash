"""Constantes del tablero: qué variables entran, cómo se llaman y dónde está el Excel."""

from __future__ import annotations

from .catalogos import (  # noqa: F401
    AZUL,
    ETIQUETAS,
    ETIQUETAS_ANALITICAS,
    FORMATO_ANALITICO,
    GLOSARIO,
    GLOSARIO_ANALITICO,
    GRIS,
    HOJAS,
    NARANJA,
    PARAMS,
    ROJO,
    VALORES_ANALITICOS,
    VERDE,
    etiqueta,
    glosa,
)

# Variables predictoras.
#
# Las columnas `*_lag` son promedios móviles con ventana configurable calculados en
# `nucleo/datos.py`. Las columnas originales (DPV, Rad, ETo, riego_lt_planta) se
# conservan en el panel para el estudio climático y la auditoría.
#
# `riego_lt_planta` es la única variable que varía entre módulos dentro de una misma
# semana; las climáticas son un dato del fundo, común a todos los módulos.
#
# Se usa `Lt/planta` y no `m3/ha` a propósito: en el archivo vigente esa segunda columna
# viene sumada sobre los turnos de riego y no está al grano del módulo. `nucleo/datos.py`
# lo detecta y lo explica en «Datos y calidad».
FEATURES: tuple[str, ...] = (
    "DPV_lag",
    "riego_lag",
    "Rad_lag",
    "ETo_lag",
    "gdd_lag",
    "TempMax",
    "TempMin",
)

# Las mismas variables SIN desfase — lo que hay antes de suponer ninguna regla temporal.
# «Impacto agronómico» y el resto del análisis descriptivo muestran ESTAS, no las de arriba:
# mostrar un promedio móvil bajo el título «la asociación cruda, antes de cualquier
# modelo» sería contradecir el propio texto de esa sección.
VARIABLES_DESCRIPTIVAS: tuple[str, ...] = (
    "DPV",
    "riego_lt_planta",
    "Rad",
    "ETo",
    "TempMax",
    "TempMin",
)

OBJETIVO = "KgHa"

# Subconjunto climático: lo que se mide una vez por semana para todo el fundo.
CLIMA: tuple[str, ...] = (
    "TempMax",
    "TempMin",
    "VarDia",
    "gdd_semana",
    "gdd_acum",
    "Rad",
    "ETo",
    "DPV",
)

# Frutos (conteo) y Peso (peso medio del fruto): los dos componentes biológicos de los
# que sale el kg/ha, incorporados desde la hoja «Kg Reales». No entran a FEATURES —
# kg/ha ≈ Frutos × Peso × densidad de plantas, así que usarlas para predecir kg/ha sería
# casi tautológico. Sirven para ver si el clima/riego pesa distinto sobre el número de
# frutos que sobre su tamaño (ver «Frutos y peso» en Impacto agronómico).
FRUTOS_PESO: tuple[str, ...] = ("Frutos", "Peso")

# Temperatura base para los grados-día de crecimiento. Por debajo de este umbral la
# planta no acumula desarrollo. 4,4 °C (40 °F) es el valor de referencia para arándano
# en la literatura; se deja como constante y no como parámetro del usuario porque cambiar
# el umbral cambia todas las cifras del tablero y eso debe ser una decisión versionada.
TBASE_GDD = 4.4

# `PARAMS`, `HOJAS` y la paleta viven en `catalogos.py`, que es la única fuente de
# verdad para configuración compartida. Se reexportan arriba para conservar todos los
# imports históricos desde `analitica.config`.
