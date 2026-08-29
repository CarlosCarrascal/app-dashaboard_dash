"""Fachada compatible del screening candidate-only de Turno + reingreso H1.

La implementación está físicamente separada por responsabilidad en los
módulos ``turno_reingreso_h1_*`` vecinos. Este módulo conserva las rutas
históricas y sus aliases, incluidos los privados usados por scripts y
notebooks.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from analitica.proyeccion.candidate_preflight import (
    escribir_json_reproducible as _escribir_json_reproducible,
)
from analitica.proyeccion.candidate_turno_temporal import (
    ConfiguracionTurnoTemporal,
    aplicar_turno_reingreso_candidate,
)
from analitica.settings import postgres_dsn

from .turno_reingreso_h1_configuracion import _rejilla_configuraciones, demostrar_noop_h1
from .turno_reingreso_h1_contexto import derivar_turno_reingreso_asof
from .turno_reingreso_h1_fuentes import (
    CAMPANIA,
    CIERRE_CERTIFICADO,
    CLAVE_LOTE,
    CONTRACT_ID,
    MAPEO_FUNDO,
    RUN_ID,
    SEMANA_DESARROLLO_FINAL,
    SEMANA_FINAL,
    SEMANA_INICIAL,
    _emitio_r09,
    _normalizar_fundo,
    leer_fuentes,
    preparar_contrato,
)
from .turno_reingreso_h1_metricas import (
    _cobertura,
    _evaluar_split,
    _keyset_sha256,
    _metricas_agregadas,
    auditar_aplicabilidad_h1,
)
from .turno_reingreso_h1_reporte import ejecutar, evaluar_panel

escribir_json_reproducible = _escribir_json_reproducible

__all__ = [
    "Any",
    "CAMPANIA",
    "CIERRE_CERTIFICADO",
    "CLAVE_LOTE",
    "CONTRACT_ID",
    "ConfiguracionTurnoTemporal",
    "Iterable",
    "MAPEO_FUNDO",
    "RUN_ID",
    "SEMANA_DESARROLLO_FINAL",
    "SEMANA_FINAL",
    "SEMANA_INICIAL",
    "_cobertura",
    "_emitio_r09",
    "_evaluar_split",
    "_keyset_sha256",
    "_metricas_agregadas",
    "_normalizar_fundo",
    "_rejilla_configuraciones",
    "aplicar_turno_reingreso_candidate",
    "asdict",
    "auditar_aplicabilidad_h1",
    "derivar_turno_reingreso_asof",
    "demostrar_noop_h1",
    "ejecutar",
    "evaluar_panel",
    "escribir_json_reproducible",
    "hashlib",
    "json",
    "leer_fuentes",
    "np",
    "pd",
    "preparar_contrato",
    "postgres_dsn",
    "psycopg",
]
