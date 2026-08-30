"""Lógica central del screening honesto de clima y fenología.

Este servicio conserva el contrato candidate-only del script histórico: no
inserta predicciones, no crea ``forecast_run`` y no modifica releases. Prueba
si señales conocidas antes de la emisión permiten desplazar —nunca escalar—
la curva h1-h6 de ``MacroLegacy_v1``.

La selección se realiza con semanas objetivo S13-S30 de C2026 y S31-S33 queda
congelado como holdout. R09 no se consulta ni se usa como feature. Cuando una
fuente no cubre una emisión, el desplazamiento vuelve a cero y la carencia
queda cuantificada en el resultado.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from analitica.aplicacion.procesos.candidatos import sha256_dataframe
from analitica.settings import postgres_dsn

from .fenologia_honest_contratos import (
    CAMPANIA,
    CIERRE_CERTIFICADO,
    FUNDOS,
    HORIZONTES,
    MAPEO_FUNDO,
    RUN_ID,
    RUNS_EXTERNOS,
    SEMANA_DESARROLLO_FINAL,
    SEMANA_INICIAL,
    SEMANAS_HOLDOUT,
    SQL_CLIMA,
    SQL_ESTADOS,
    SQL_FLORES,
    SQL_MACRO,
    TBASES,
    VENTANAS,
    Configuracion,
)
from .fenologia_honest_evaluacion import (
    _cobertura_fuentes,
    _configuraciones,
    _evaluar_externa,
    _filtro_scope,
    _resumen_config,
    evaluar,
    evaluar_gates,
    metricas,
    metricas_por_fundo,
    seleccionar_configuracion,
)
from .fenologia_honest_fuentes import (
    _leer_dataframe,
    _normalizar_fundo,
    _preparar_estados,
    _preparar_flores,
    agregar_curvas_fundo,
    construir_clima_asof,
    construir_fenologia_asof,
    leer_fuentes,
    preparar_clima,
    preparar_macro,
)
from .fenologia_honest_modelo import (
    _columna_clima,
    _escalar_entrenamiento,
    aplicar_desplazamientos,
    calcular_desplazamientos,
    construir_panel_features,
    redistribuir_curva,
)
from .fenologia_honest_salida import _json_limpio

__all__ = [
    "Any",
    "CAMPANIA",
    "CIERRE_CERTIFICADO",
    "Configuracion",
    "FUNDOS",
    "HORIZONTES",
    "Iterable",
    "MAPEO_FUNDO",
    "RUN_ID",
    "RUNS_EXTERNOS",
    "SEMANA_DESARROLLO_FINAL",
    "SEMANA_INICIAL",
    "SEMANAS_HOLDOUT",
    "SQL_CLIMA",
    "SQL_ESTADOS",
    "SQL_FLORES",
    "SQL_MACRO",
    "TBASES",
    "VENTANAS",
    "_cobertura_fuentes",
    "_columna_clima",
    "_configuraciones",
    "_escalar_entrenamiento",
    "_evaluar_externa",
    "_filtro_scope",
    "_json_limpio",
    "_leer_dataframe",
    "_normalizar_fundo",
    "_preparar_estados",
    "_preparar_flores",
    "_resumen_config",
    "agregar_curvas_fundo",
    "aplicar_desplazamientos",
    "asdict",
    "calcular_desplazamientos",
    "construir_clima_asof",
    "construir_fenologia_asof",
    "construir_panel_features",
    "dataclass",
    "evaluar",
    "evaluar_gates",
    "leer_fuentes",
    "metricas",
    "metricas_por_fundo",
    "np",
    "pd",
    "postgres_dsn",
    "preparar_clima",
    "preparar_macro",
    "psycopg",
    "redistribuir_curva",
    "seleccionar_configuracion",
    "sha256_dataframe",
]
