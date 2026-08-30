"""Orquestación y serialización de la salida de small data H1."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from . import small_data_h1_configuracion as _configuracion
from .small_data_h1_evaluacion import _resumen_periodo, seleccionar_configuracion
from .small_data_h1_lectura import cargar_universo_lote
from .small_data_h1_prediccion import (
    aplicar_candidato_a_lotes,
    construir_panel_fundo,
    predecir_rolling,
)

CAMPANIA_DEFAULT = _configuracion.CAMPANIA_DEFAULT
FEATURE_SETS = _configuracion.FEATURE_SETS
RUN_ID_DEFAULT = _configuracion.RUN_ID_DEFAULT
SEMANA_MAX_SELECCION = _configuracion.SEMANA_MAX_SELECCION
SEMANAS_HOLDOUT = _configuracion.SEMANAS_HOLDOUT
ULTIMO_CIERRE_DEFAULT = _configuracion.ULTIMO_CIERRE_DEFAULT
Configuracion = _configuracion.Configuracion


def ejecutar(
    *,
    run_id: int = RUN_ID_DEFAULT,
    campania: str = CAMPANIA_DEFAULT,
    ultimo_cierre: pd.Timestamp = ULTIMO_CIERRE_DEFAULT,
) -> dict[str, object]:
    universo = cargar_universo_lote(
        run_id=run_id,
        campania=campania,
        ultimo_cierre=ultimo_cierre,
    )
    panel = construir_panel_fundo(universo)
    ganador, ranking = seleccionar_configuracion(panel)
    pred = predecir_rolling(panel, ganador)
    lotes = aplicar_candidato_a_lotes(universo, pred)

    desarrollo_panel = pred.semana_objetivo.le(SEMANA_MAX_SELECCION)
    holdout_panel = pred.semana_objetivo.isin(SEMANAS_HOLDOUT)
    desarrollo_lotes = lotes.semana_objetivo.le(SEMANA_MAX_SELECCION)
    holdout_lotes = lotes.semana_objetivo.isin(SEMANAS_HOLDOUT)
    resumen_holdout = _resumen_periodo(pred, lotes, holdout_panel, holdout_lotes)

    r09_holdout = resumen_holdout["r09_condicionado_mismo_universo"]["empresa"]
    candidato_holdout = r09_holdout["candidato"]
    referencia_holdout = r09_holdout["r09"]
    supera_r09 = bool(
        candidato_holdout["wape"] < referencia_holdout["wape"]
        and abs(candidato_holdout["sesgo"]) <= abs(referencia_holdout["sesgo"])
    )
    return {
        "schema": "screening-small-data-h1-v1",
        "campania": campania,
        "run_macro_congelada": run_id,
        "seleccion": "hiperparametros y features solo con semanas objetivo <= S30",
        "holdout": "S31-S33; rolling-origin, hiperparametros congelados",
        "configuracion_ganadora": asdict(ganador),
        "features_usadas": list(FEATURE_SETS[ganador.feature_set]),
        "features_descartadas": {
            "clima": (
                "No se usó: los componentes agregados no conservan para cada fila un "
                "snapshot meteorológico/versionado que demuestre completamente su "
                "disponibilidad as-of."
            ),
            "fenologia": (
                "No se usó: aunque existen fechas parciales, la cobertura y la vigencia del "
                "snapshot no están demostradas de forma homogénea para el contrato h1."
            ),
            "r09": "Referencia posterior a la predicción; nunca predictor ni selector.",
        },
        "contrato": {
            "ultima_semana_cerrada": str(pd.Timestamp(ultimo_cierre).date()),
            "semanas": sorted(map(int, pred.semana_objetivo.unique())),
            "n_fundo_semana": int(len(pred)),
            "n_lote_semana": int(len(lotes)),
            "n_lotes": int(lotes.lote_id.nunique()),
            "fundo_operativo": sorted(pred.fundo_operativo.unique()),
            "regla_asof": "semana_fin_historia < fecha_emision_objetivo",
            "r09_como_predictor": False,
        },
        "desarrollo_hasta_s30": _resumen_periodo(pred, lotes, desarrollo_panel, desarrollo_lotes),
        "holdout_s31_s33": resumen_holdout,
        "contrato_completo": _resumen_periodo(
            pred,
            lotes,
            pd.Series(True, index=pred.index),
            pd.Series(True, index=lotes.index),
        ),
        "ranking_desarrollo": [
            {
                key: (asdict(value) if isinstance(value, Configuracion) else value)
                for key, value in fila.items()
            }
            for fila in ranking.head(10).to_dict("records")
        ],
        "veredicto_holdout": {
            "supera_r09_condicionado": supera_r09,
            "publicable": False,
            "nota": (
                "Screening aislado: aun si mejora el holdout, requiere campañas externas, "
                "bootstrap y preflight antes de persistir o publicar."
            ),
        },
    }


def _json_default(valor: object) -> object:
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.floating,)):
        return float(valor)
    if isinstance(valor, (pd.Timestamp,)):
        return valor.isoformat()
    raise TypeError(f"No serializable: {type(valor)!r}")


__all__ = ["_json_default", "ejecutar"]
