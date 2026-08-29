"""Fachada compatible del screening candidate-only de Turno + reingreso.

La implementación está físicamente separada por responsabilidad en los
módulos ``turno_reingreso_*`` vecinos. Este módulo conserva las rutas históricas
y sus aliases, incluidos los privados usados por scripts y notebooks.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from analitica.proyeccion.candidate_turno_temporal import (
    ConfiguracionTurnoTemporal,
    aplicar_turno_reingreso_candidate,
    normalizar_forecast_candidate,
)
from analitica.settings import postgres_dsn

from .turno_reingreso_configuracion import (
    aplicar_configuracion,
    auditar_paridad_funcion_pura,
    rejilla_configuraciones,
)
from .turno_reingreso_contexto import (
    _mediana_grupo,
    _preparar_h01,
    derivar_contexto_asof,
    enriquecer_macro,
)
from .turno_reingreso_fuentes import (
    CAMPANIA,
    CIERRE_CERTIFICADO,
    CLAVE,
    CONTRACT_ID,
    GRUPO_CURVA,
    HORIZONTE_MAX,
    HORIZONTE_MIN,
    MAPEO_FUNDO,
    RUN_ID,
    SEMANA_DESARROLLO_FINAL,
    SEMANA_FINAL,
    SEMANA_INICIAL,
    _normalizar_fundo,
    leer_fuentes,
    preparar_macro,
    preparar_r09,
)
from .turno_reingreso_metricas import (
    _alinear_candidato,
    _banda_horizonte,
    _cobertura_r09,
    _cobertura_r09_bandas,
    _hash_claves,
    _metricas,
    _metricas_bandas,
    _score_desarrollo,
    _semanas_ganadas,
    comparar_r09_despues,
    seleccionar_configuracion,
)
from .turno_reingreso_reporte import evaluar_panel

__all__ = [
    "Any",
    "CAMPANIA",
    "CIERRE_CERTIFICADO",
    "CLAVE",
    "CONTRACT_ID",
    "ConfiguracionTurnoTemporal",
    "GRUPO_CURVA",
    "HORIZONTE_MAX",
    "HORIZONTE_MIN",
    "Iterable",
    "MAPEO_FUNDO",
    "RUN_ID",
    "SEMANA_DESARROLLO_FINAL",
    "SEMANA_FINAL",
    "SEMANA_INICIAL",
    "_alinear_candidato",
    "_banda_horizonte",
    "_cobertura_r09",
    "_cobertura_r09_bandas",
    "_hash_claves",
    "_mediana_grupo",
    "_metricas",
    "_metricas_bandas",
    "_normalizar_fundo",
    "_preparar_h01",
    "_score_desarrollo",
    "_semanas_ganadas",
    "aplicar_configuracion",
    "aplicar_turno_reingreso_candidate",
    "asdict",
    "auditar_paridad_funcion_pura",
    "comparar_r09_despues",
    "derivar_contexto_asof",
    "enriquecer_macro",
    "evaluar_panel",
    "hashlib",
    "leer_fuentes",
    "normalizar_forecast_candidate",
    "np",
    "pd",
    "preparar_macro",
    "preparar_r09",
    "postgres_dsn",
    "psycopg",
    "rejilla_configuraciones",
    "seleccionar_configuracion",
]
