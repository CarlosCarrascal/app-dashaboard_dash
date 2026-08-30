"""Fachada compatible del screening de deltas expertos Excel de MacroLegacy h1.

La lectura de libros, la normalización, el cálculo y la serialización viven en
módulos internos especializados. Este módulo conserva los nombres históricos y
sus contratos para las fachadas CLI y consumidores existentes.
"""

from __future__ import annotations

import hashlib  # noqa: F401 - alias histórico consumido por la fachada CLI
import re  # noqa: F401 - alias histórico consumido por la fachada CLI
from collections.abc import Iterable, Mapping  # noqa: F401
from dataclasses import asdict, dataclass  # noqa: F401

import numpy as np  # noqa: F401
import pandas as pd  # noqa: F401
from sklearn.linear_model import Ridge  # noqa: F401
from sklearn.preprocessing import StandardScaler  # noqa: F401

from . import excel_parameter_deltas_calculation as _calculation
from . import excel_parameter_deltas_io as _io
from . import excel_parameter_deltas_normalization as _normalization
from . import excel_parameter_deltas_serialization as _serialization
from .small_data import cargar_universo_lote  # noqa: F401 - alias histórico

CAMPANIA_DEFAULT = _calculation.CAMPANIA_DEFAULT
FEATURE_SETS = _calculation.FEATURE_SETS
FEATURES_CRUDAS = _calculation.FEATURES_CRUDAS
ROOT_DEFAULT = _calculation.ROOT_DEFAULT
RUN_ID_DEFAULT = _calculation.RUN_ID_DEFAULT
SEMANA_MAX_DESARROLLO = _calculation.SEMANA_MAX_DESARROLLO
SEMANAS_HOLDOUT = _calculation.SEMANAS_HOLDOUT
Configuracion = _calculation.Configuracion
_ajustar_predecir = _calculation._ajustar_predecir
_evaluar_periodo = _calculation._evaluar_periodo
_keyset = _calculation._keyset
_mediana_finita = _calculation._mediana_finita
_metricas = _calculation._metricas
aplicar_shrinkage_features = _calculation.aplicar_shrinkage_features
calcular_delta_snapshot = _calculation.calcular_delta_snapshot
configuraciones = _calculation.configuraciones
construir_contrato = _calculation.construir_contrato
construir_deltas = _calculation.construir_deltas
ejecutar = _calculation.ejecutar
predecir_temporal = _calculation.predecir_temporal
seleccionar_configuracion = _calculation.seleccionar_configuracion
_tabla_hoja = _io._tabla_hoja
cargar_snapshots = _io.cargar_snapshots
inventariar_libros = _io.inventariar_libros
leer_snapshot_libro = _io.leer_snapshot_libro
sha256_archivo = _io.sha256_archivo
ALIASES_FUNDO = _normalization.ALIASES_FUNDO
FUNDOS = _normalization.FUNDOS
PARAMETROS = _normalization.PARAMETROS
SEMANAS = _normalization.SEMANAS
TOKENS_VARIANTE = _normalization.TOKENS_VARIANTE
_clave_lote = _normalization._clave_lote
_columna = _normalization._columna
_es_variante = _normalization._es_variante
_normalizar_texto = _normalization._normalizar_texto
_json_default = _serialization._json_default
