"""Orquestación y serialización del resultado del scheduler."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analitica.servicios.cross_campaign import R09_ACCESS_DEFAULT, leer_r09_access

from .active_lot_scheduler_contratos import CIERRE_C2026, RUN_ID, SEMANAS_HOLDOUT
from .active_lot_scheduler_fuentes import derivar_contexto_asof, leer_fuentes
from .active_lot_scheduler_metricas import (
    anexar_r09,
    resumir,
    resumir_con_r09,
    seleccionar_configuracion,
)
from .active_lot_scheduler_prediccion import construir_verdad, predecir_scheduler


def _keyset_sha256(tabla: pd.DataFrame) -> str:
    columnas = ["campania", "fecha_emision", "fecha_objetivo", "lote_id"]
    disponibles = [c for c in columnas if c in tabla]
    texto = (
        tabla[disponibles]
        .drop_duplicates()
        .sort_values(disponibles, kind="stable")
        .astype(str)
        .agg("|".join, axis=1)
        .str.cat(sep="\n")
    )
    return hashlib.sha256(texto.encode()).hexdigest()


def ejecutar(run_id: int = RUN_ID, r09_access: Path = R09_ACCESS_DEFAULT) -> dict[str, Any]:
    macro, h01 = leer_fuentes(run_id)
    verdad = construir_verdad(h01)
    contexto = derivar_contexto_asof(macro, h01)
    c2026 = contexto.loc[contexto.campania.eq("C2026") & contexto.semana_iso.le(33)].copy()
    verdad26 = verdad.loc[verdad.campania.eq("C2026")].copy()
    ganador, pred26, ranking = seleccionar_configuracion(c2026, verdad26)
    pred26 = pred26.loc[pred26.semana_iso.le(33)].copy()
    r09 = leer_r09_access(r09_access)
    anexar_r09(pred26, r09)

    dev = pred26.loc[pred26.semana_iso.le(30)].copy()
    holdout = pred26.loc[pred26.semana_iso.isin(SEMANAS_HOLDOUT)].copy()
    metricas: dict[str, Any] = {
        "c2026_desarrollo_hasta_s30": {
            **resumir(dev),
            "r09_mismo_universo": resumir_con_r09(anexar_r09(dev, r09)),
        },
        "c2026_holdout_s31_s33": {
            **resumir(holdout),
            "r09_mismo_universo": resumir_con_r09(anexar_r09(holdout, r09)),
        },
    }

    externos: dict[str, Any] = {}
    for campania in ("C2024", "C2025"):
        contexto_ext = contexto.loc[contexto.campania.eq(campania)].copy()
        verdad_ext = verdad.loc[verdad.campania.eq(campania)].copy()
        if contexto_ext.empty or verdad_ext.empty:
            externos[campania] = {"estado": "sin_claves_comparables"}
            continue
        pred_ext = predecir_scheduler(contexto_ext, verdad_ext, ganador)
        externos[campania] = {
            "estado": "evaluado",
            **resumir(pred_ext),
            "r09_mismo_universo": resumir_con_r09(anexar_r09(pred_ext, r09)),
        }
    metricas["validacion_externa"] = externos

    hold_c = metricas["c2026_holdout_s31_s33"]["empresa"]["candidate"]
    hold_m = metricas["c2026_holdout_s31_s33"]["empresa"]["macro"]
    mejora_macro = float(hold_c["wape"]) < float(hold_m["wape"])
    falsos_c = metricas["c2026_holdout_s31_s33"]["cobertura_candidate"]
    falsos_m = metricas["c2026_holdout_s31_s33"]["cobertura_macro"]
    no_empeora_ceros = float(falsos_c["falsos_ceros_volumen_pct"]) <= float(
        falsos_m["falsos_ceros_volumen_pct"]
    )
    r09_hold = metricas["c2026_holdout_s31_s33"]["r09_mismo_universo"]
    mejora_r09 = False
    if isinstance(r09_hold, dict):
        mejora_r09 = float(r09_hold["empresa"]["candidate"]["wape"]) < float(
            r09_hold["empresa"]["r09"]["wape"]
        )
    aceptado = bool(mejora_macro and no_empeora_ceros)
    return {
        "schema": "screening-active-lot-scheduler-v1",
        "candidate_only": True,
        "persistido": False,
        "publicado": False,
        "usa_r09_como_predictor": False,
        "usa_excel_contemporaneo_como_predictor": False,
        "run_macro": run_id,
        "seleccion": "solo C2026 hasta S30; S31-S33 holdout",
        "configuracion_ganadora": asdict(ganador),
        "configuracion_id": ganador.id,
        "ranking_desarrollo": ranking.head(20).to_dict("records"),
        "evaluation_contract": {
            "keyset_sha256": _keyset_sha256(c2026),
            "cierre_c2026": str(CIERRE_C2026.date()),
            "semanas_desarrollo": "S13-S30",
            "semanas_holdout": "S31-S33",
            "regla_features": "H01.fecha < fecha_emision",
            "regla_r09": "se incorpora solo despues de seleccionar la configuracion",
        },
        "metricas": metricas,
        "veredicto": {
            "mejora_macro_holdout": bool(mejora_macro),
            "mejora_r09_holdout": bool(mejora_r09),
            "no_empeora_falsos_ceros": bool(no_empeora_ceros),
            "aceptado_screening": aceptado,
            "decision": (
                "ACEPTAR PARA SIGUIENTE GATE; NO PERSISTIR"
                if aceptado
                else "RECHAZAR: no mejora Macro holdout o empeora falsos ceros"
            ),
        },
    }


def _json_default(valor: object) -> object:
    if isinstance(valor, (pd.Timestamp, Path)):
        return str(valor)
    if isinstance(valor, np.generic):
        return valor.item()
    if pd.isna(valor):
        return None
    raise TypeError(type(valor).__name__)


def escribir_resultado(resultado: dict[str, Any], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
