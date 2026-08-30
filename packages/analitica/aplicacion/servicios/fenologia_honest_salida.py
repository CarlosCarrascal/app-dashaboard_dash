"""Construcción y serialización de la salida del screening."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analitica.aplicacion.procesos.candidatos import sha256_dataframe

from .fenologia_honest_contratos import CAMPANIA, HORIZONTES, RUN_ID


def construir_resultado(
    base: pd.DataFrame,
    diario: pd.DataFrame,
    fen_asof: pd.DataFrame,
    estados: pd.DataFrame,
    flores: pd.DataFrame,
    cobertura: dict[str, Any],
    salidas_scope: dict[str, Any],
) -> dict[str, Any]:
    clima_max = diario.fecha.max() if len(diario) else pd.NaT
    resultado = {
        "experimento": "screening_gdd_fenologia_honest_v1",
        "contrato": {
            "campania": CAMPANIA,
            "run_id_macro": RUN_ID,
            "seleccion": "semanas objetivo S13-S30",
            "holdout": "S31-S33; cierre certificado 16/08/2026",
            "horizontes": list(HORIZONTES),
            "regla_asof": "fecha_observacion < fecha_emision",
            "transformacion": "solo desplazamiento temporal conservando kg h1-h6",
            "r09_como_feature": False,
        },
        "fuentes": {
            "postgres": True,
            "datos_mes_xlsx_usado": False,
            "motivo_no_usar_excel": (
                "VarClima del libro termina el 26/07/2026, igual que PostgreSQL; "
                "EvFlores termina el 07/01/2026 y no amplía C2026."
            ),
            "clima_min": diario.fecha.min(),
            "clima_max": clima_max,
            "filas_clima_diario": int(len(diario)),
            "filas_estados": int(len(estados)),
            "filas_flores": int(len(flores)),
        },
        "cobertura": cobertura,
        "hashes": {
            "macro": sha256_dataframe(
                base,
                [
                    "campania",
                    "fecha_emision",
                    "fecha_objetivo",
                    "lote_id",
                    "p50_kg",
                    "real_kg",
                ],
            ),
            "clima": sha256_dataframe(diario, list(diario.columns)),
            "fenologia": sha256_dataframe(
                fen_asof,
                [
                    "fecha_emision",
                    "fundo_operativo",
                    "indice_estado",
                    "prop_e45",
                    "flores_por_planta",
                    "tasa_cuajo",
                ],
            ),
        },
        "resultados": salidas_scope,
        "decision": {
            "incorporar_gdd_fenologia": any(
                valor["admitido_para_modelo"] for valor in salidas_scope.values()
            ),
            "persistir": False,
            "publicar": False,
        },
    }
    return resultado


def _json_limpio(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {str(k): _json_limpio(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json_limpio(v) for v in valor]
    if isinstance(valor, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(valor).isoformat()
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (float, np.floating)):
        return None if not np.isfinite(valor) else float(valor)
    if isinstance(valor, (np.bool_,)):
        return bool(valor)
    return valor
