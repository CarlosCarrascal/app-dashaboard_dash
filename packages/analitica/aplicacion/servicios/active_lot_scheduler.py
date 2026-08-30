"""Screening candidate-only de auto-scheduler de lotes para MacroLegacy h1.

El candidato usa exclusivamente cosechas H01 anteriores a cada emision para
derivar Turno, ultimo ingreso y dias de reingreso.  No usa R09 ni calendarios
Excel como predictor.  R09 se incorpora solamente despues de congelar la
configuracion seleccionada, como referencia de evaluacion.

El scheduler no aplica gates binarios. Redistribuye continuamente el total
Macro de cada fundo entre lotes mediante una mezcla de participacion Macro y
actividad esperada. Opcionalmente escala el total con residuos historicos
cerrados anteriores a la emision. No escribe en PostgreSQL ni publica nada.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from analitica.aplicacion.servicios.cross_campaign import (
    R09_ACCESS_DEFAULT,
    leer_r09_access,
    normalizar_fundo,
)
from analitica.settings import postgres_dsn

from .active_lot_scheduler_contratos import (
    CAMPANIAS,
    CIERRE_C2026,
    FUNDOS,
    RUN_ID,
    RUTA_SALIDA,
    SEMANA_DESARROLLO_FINAL,
    SEMANAS_HOLDOUT,
    ConfiguracionScheduler,
    configuraciones,
)
from .active_lot_scheduler_fuentes import (
    _distancia_periodica,
    _intervalo_mediano,
    _normalizar_fechas,
    derivar_contexto_asof,
    leer_fuentes,
)
from .active_lot_scheduler_metricas import (
    _cobertura_y_ceros,
    _metricas,
    anexar_r09,
    bootstrap_pareado,
    resumir,
    resumir_con_r09,
    seleccionar_configuracion,
)
from .active_lot_scheduler_prediccion import (
    _actividad,
    _escala_online,
    construir_verdad,
    predecir_scheduler,
)
from .active_lot_scheduler_salida import (
    _json_default,
    _keyset_sha256,
    ejecutar,
    escribir_resultado,
)

__all__ = [
    "Any",
    "CAMPANIAS",
    "CIERRE_C2026",
    "ConfiguracionScheduler",
    "FUNDOS",
    "Iterable",
    "Path",
    "R09_ACCESS_DEFAULT",
    "RUN_ID",
    "RUTA_SALIDA",
    "SEMANA_DESARROLLO_FINAL",
    "SEMANAS_HOLDOUT",
    "_actividad",
    "_cobertura_y_ceros",
    "_distancia_periodica",
    "_escala_online",
    "_intervalo_mediano",
    "_json_default",
    "_keyset_sha256",
    "_metricas",
    "_normalizar_fechas",
    "anexar_r09",
    "asdict",
    "bootstrap_pareado",
    "configuraciones",
    "construir_verdad",
    "dataclass",
    "derivar_contexto_asof",
    "ejecutar",
    "escribir_resultado",
    "hashlib",
    "json",
    "leer_fuentes",
    "leer_r09_access",
    "math",
    "normalizar_fundo",
    "np",
    "pd",
    "postgres_dsn",
    "predecir_scheduler",
    "psycopg",
    "resumir",
    "resumir_con_r09",
    "seleccionar_configuracion",
]
