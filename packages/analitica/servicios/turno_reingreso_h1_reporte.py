"""Orquestación y reporte del screening run76 H1."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .turno_reingreso_h1_configuracion import demostrar_noop_h1
from .turno_reingreso_h1_contexto import derivar_turno_reingreso_asof
from .turno_reingreso_h1_fuentes import (
    CAMPANIA,
    CIERRE_CERTIFICADO,
    CONTRACT_ID,
    RUN_ID,
    SEMANA_DESARROLLO_FINAL,
    SEMANA_FINAL,
    SEMANA_INICIAL,
    leer_fuentes,
    preparar_contrato,
)
from .turno_reingreso_h1_metricas import (
    _cobertura,
    _evaluar_split,
    _keyset_sha256,
    auditar_aplicabilidad_h1,
)


def evaluar_panel(
    macro: pd.DataFrame,
    r09: pd.DataFrame,
    h01: pd.DataFrame,
) -> dict[str, Any]:
    contrato = preparar_contrato(macro, r09)
    enriquecido = derivar_turno_reingreso_asof(contrato, h01)
    historia_funcion = h01.copy()
    historia_funcion["fecha"] = pd.to_datetime(
        historia_funcion.fecha, errors="raise"
    ).dt.normalize()
    historia_funcion["kg"] = pd.to_numeric(historia_funcion.kg, errors="coerce").fillna(0.0)
    aplicabilidad = auditar_aplicabilidad_h1(enriquecido)
    demostracion = demostrar_noop_h1(
        enriquecido,
        historia_funcion[["campania", "lote_id", "fecha", "kg"]].copy(),
    )
    feature_disponible = enriquecido.turno.notna() & enriquecido.dias_reingreso.notna()
    cobertura_feature = _cobertura(enriquecido, feature_disponible)

    desarrollo = enriquecido[enriquecido.split.eq("desarrollo_s13_s30")].copy()
    holdout = enriquecido[enriquecido.split.eq("holdout_s31_s33")].copy()
    completo = _evaluar_split(enriquecido)
    desarrollo_m = _evaluar_split(desarrollo)
    holdout_m = _evaluar_split(holdout)
    return {
        "schema": "screening-turno-reingreso-h1-v1",
        "candidate_only": True,
        "persistencia_postgresql": False,
        "run_base": RUN_ID,
        "campania": CAMPANIA,
        "evaluation_contract": {
            "id": CONTRACT_ID,
            "semanas_cerradas": f"S{SEMANA_INICIAL}-S{SEMANA_FINAL}",
            "seleccion_configuraciones": f"S{SEMANA_INICIAL}-S{SEMANA_DESARROLLO_FINAL}",
            "holdout": f"S{SEMANA_DESARROLLO_FINAL + 1}-S{SEMANA_FINAL}",
            "cierre_certificado": CIERRE_CERTIFICADO.date().isoformat(),
            "filas_lote_semana": int(len(enriquecido)),
            "lotes": int(enriquecido.lote_id.nunique()),
            "semanas": int(enriquecido.fecha_objetivo.nunique()),
            "fundos": sorted(enriquecido.fundo.unique().tolist()),
            "keyset_sha256": _keyset_sha256(enriquecido),
            "real_kg": float(enriquecido.real_kg.sum()),
        },
        "feature_turno_reingreso_asof": {
            **cobertura_feature,
            "filas_con_turno": int(enriquecido.turno.notna().sum()),
            "filas_con_reingreso": int(enriquecido.dias_reingreso.notna().sum()),
            "regla": (
                "turno de la última cosecha H01 anterior a emisión; reingreso = mediana "
                "de los últimos cinco intervalos H01 de 5–21 días anteriores a emisión"
            ),
        },
        "aplicabilidad": aplicabilidad,
        "seleccion": {
            "estado": "bloqueada_por_contrato_h1"
            if not aplicabilidad["aplicable"]
            else "ejecutada",
            "configuracion_seleccionada": None,
            "razon": aplicabilidad["razon_bloqueo"],
            "demostracion_funcion_pura": demostracion,
        },
        "metricas": {
            "completo_s13_s33": completo,
            "desarrollo_s13_s30": desarrollo_m,
            "holdout_s31_s33": holdout_m,
        },
        "veredicto": (
            "BLOQUEADO: run76 h1 no permite redistribuir volumen por Turno/reingreso. "
            "Se requieren al menos h1-h2 contiguos del mismo snapshot por emisión-lote; "
            "usar otra emisión como si fuera h2 mezclaría vintages y violaría el replay."
            if not aplicabilidad["aplicable"]
            else "EVALUADO"
        ),
    }


def ejecutar() -> dict[str, Any]:
    macro, r09, h01 = leer_fuentes()
    return evaluar_panel(macro, r09, h01)
