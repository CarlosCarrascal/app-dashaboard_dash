"""Fachada compatible del modelo fenológico por componentes independiente de R09.

La implementación vive en :mod:`analitica.proyeccion.fenologico`. Este módulo
conserva los nombres históricos, incluidos los aliases privados que usan
consumidores y pruebas existentes.
"""

# Esta fachada conserva aliases históricos (incluidos privados) aunque la lógica
# correspondiente esté físicamente en los módulos internos.
# ruff: noqa: F401
from __future__ import annotations

import numpy as np
import pandas as pd

from . import asof as _asof
from . import temporal as _temporal
from .fenologico import ajuste as _ajuste
from .fenologico import especificacion as _especificacion
from .fenologico import evidencia as _evidencia
from .fenologico import metricas as _metricas
from .fenologico import panel as _panel
from .fenologico.contratos import EscenarioFenologico, ResultadoFenologico
from .fenologico.especificacion import (
    FEATURES_CLIMA,
    FEATURES_FENOLOGIA,
    FEATURES_FRUTOS,
    FEATURES_OCURRENCIA,
    FEATURES_PESO,
    FEATURES_RIEGO,
    NOMBRE_MODELO,
)
from .fenologico.incertidumbre import aplicar_escenario_fenologico
from .fenologico.servicio import (
    _predecir_emision,
    backtest_fenologico_v1,
    proyectar_fenologico_v1,
)
from .versiones import banda_horizonte

_normalizar_emisiones = _panel.normalizar_emisiones
cosecha_real_semanal = _panel.cosecha_real_semanal
_campania_mas_reciente = _panel.campania_mas_reciente
_emisiones_historial = _panel.emisiones_historial
_agregar_historial_asof = _panel.agregar_historial_asof
construir_panel_fenologico = _panel.construir_panel_fenologico
auditar_panel_fenologico = _panel.auditar_panel_fenologico
_hipotesis = _evidencia.hipotesis
_correlacion = _evidencia.correlacion
evaluar_evidencia_fold = _evidencia.evaluar_evidencia_fold
FEATURES_CONTROL = _especificacion.FEATURES_CONTROL
FEATURES_PROHIBIDAS = _especificacion.FEATURES_PROHIBIDAS
HIPOTESIS_FEATURE = _especificacion.HIPOTESIS_FEATURE
REFERENCIAS_HIPOTESIS = _especificacion.REFERENCIAS_HIPOTESIS
detectar_fuga = _asof.detectar_fuga
enriquecer_asof = _asof.enriquecer_asof
lunes_semana = _temporal.lunes_semana
ultimo_disponible = _temporal.ultimo_disponible
_ModeloAjustado = _ajuste._ModeloAjustado
_MixedLMFinal = _ajuste._MixedLMFinal
_columnas_modelo = _ajuste.columnas_modelo
_preprocesador = _ajuste.preprocesador
_regresores = _ajuste.regresores
_clasificadores = _ajuste.clasificadores
_corte_temporal = _ajuste.corte_temporal
_pipeline = _ajuste.pipeline
_ajustar_mixedlm = _ajuste.ajustar_mixedlm
_ajustar_regresor = _ajuste.ajustar_regresor
_ajustar_clasificador = _ajuste.ajustar_clasificador
_predecir = _ajuste.predecir
_sensibilidades = _metricas.sensibilidades
_intervalos_validacion = _metricas.intervalos_validacion
_intervalos_volumen_directo = _metricas.intervalos_volumen_directo
_calibrar_factor_volumen = _metricas.calibrar_factor_volumen
