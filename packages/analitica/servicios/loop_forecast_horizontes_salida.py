"""Orquestación y salida JSON del loop candidate-only por horizontes."""

from __future__ import annotations

from typing import Any

import pandas as pd

from analitica.proyeccion.horizonte import seleccionar_vintage_coherente

from . import loop_forecast_horizontes_configuracion as _configuracion
from .loop_forecast_horizontes_evaluacion import (
    _comparar_r09,
    _metricas_por_horizonte,
    _resumen_nowcast_vs_v2,
)
from .loop_forecast_horizontes_lectura import _leer_nowcast, _panel_base
from .loop_forecast_horizontes_prediccion import _aplicar_mejores, ejecutar_loop_por_horizonte

CIERRES = _configuracion.CIERRES
HORIZONTES_LARGOS = _configuracion.HORIZONTES_LARGOS
RUN_H1_APROBADO = _configuracion.RUN_H1_APROBADO
RUN_MACRO_MULTI = _configuracion.RUN_MACRO_MULTI
RUN_NOWCAST = _configuracion.RUN_NOWCAST
RUN_R09_MULTI = _configuracion.RUN_R09_MULTI
configuraciones_loop = _configuracion.configuraciones_loop


def ejecutar(campania: str = "C2026", desarrollo_hasta: str | None = None) -> dict[str, Any]:
    if campania not in CIERRES:
        raise ValueError(f"Campaña no soportada: {campania}")
    base, r09, v2 = _panel_base(campania)
    # H1 conserva el híbrido aprobado. La hipótesis nueva se prueba únicamente
    # en H2-H6 y aprende un factor común usando las curvas Macro de esos
    # horizontes; no mezcla la evidencia intra-semanal del nowcast.
    base_largos = base[base["horizonte_semanas"].isin(HORIZONTES_LARGOS)].copy()
    fecha_desarrollo = (
        pd.Timestamp(desarrollo_hasta)
        if desarrollo_hasta
        else CIERRES[campania] - pd.Timedelta(days=49)
    )
    loop = ejecutar_loop_por_horizonte(
        base_largos.drop(columns="macro_kg"),
        horizontes=HORIZONTES_LARGOS,
        fecha_desarrollo_hasta=fecha_desarrollo,
        configuraciones=configuraciones_loop(),
    )
    candidato_largos = _aplicar_mejores(
        base_largos.drop(columns="macro_kg"),
        loop,
        panel_historial=base_largos.drop(columns="macro_kg"),
    )
    h1 = base[base["horizonte_semanas"].eq(1)].copy()
    h1["pred_kg"] = h1["p50_kg"]
    candidato = pd.concat([h1, candidato_largos], ignore_index=True)
    vintage_candidato = seleccionar_vintage_coherente(candidato)
    vintage_base = seleccionar_vintage_coherente(base)
    vintage_base["pred_kg"] = vintage_base["macro_kg"]
    metricas = {
        "candidato": _metricas_por_horizonte(vintage_candidato, "pred_kg"),
        "macro": _metricas_por_horizonte(vintage_base, "pred_kg"),
    }
    largos_macro = [metricas["macro"][str(h)] for h in HORIZONTES_LARGOS]
    largos_candidato = [metricas["candidato"][str(h)] for h in HORIZONTES_LARGOS]
    denominador_largo = sum(fila["real_kg"] for fila in largos_macro)
    wape_macro_largo = (
        sum(fila["wape"] * fila["real_kg"] for fila in largos_macro) / denominador_largo
        if denominador_largo
        else None
    )
    wape_candidato_largo = (
        sum(fila["wape"] * fila["real_kg"] for fila in largos_candidato) / denominador_largo
        if denominador_largo
        else None
    )
    mejora_largo = (
        (wape_macro_largo - wape_candidato_largo) / wape_macro_largo
        if wape_macro_largo and wape_candidato_largo is not None
        else None
    )
    deterioros_largo = {
        str(h): metricas["candidato"][str(h)]["wape"] - metricas["macro"][str(h)]["wape"]
        for h in HORIZONTES_LARGOS
    }
    decision = {
        "estado": (
            "promover_candidato"
            if mejora_largo is not None and mejora_largo > 0.05
            else "descartado"
        ),
        "mejora_wape_h2_h6_relativa": mejora_largo,
        "diferencia_wape_pp_por_horizonte": {
            h: delta * 100 for h, delta in deterioros_largo.items()
        },
        "criterio": (
            "promover solo si H2-H6 mejora WAPE agregado al menos 5%; "
            "H1 no participa porque pertenece al híbrido aprobado"
        ),
        "publicable": False,
        "motivo": (
            "La corrección candidate-only no se integra automáticamente; "
            "si no mejora H2-H6 queda descartada"
        ),
    }
    # R09 es una referencia externa. La comparación se restringe a sus
    # emisiones comunes y su cobertura queda explicitada.
    r09_ref = _comparar_r09(vintage_candidato, r09)
    nowcast = _leer_nowcast(campania)
    return {
        "schema": "loop-forecast-horizontes-v1",
        "campania": campania,
        "objetivo": "mejorar el forecast previo de H2-H6 contra kilos reales",
        "corte_real_cerrado": str(CIERRES[campania].date()),
        "desarrollo_hasta": str(fecha_desarrollo.date()),
        "fuentes": {
            "macro_run_id": RUN_MACRO_MULTI[campania],
            "v2_aprobado_run_id": RUN_H1_APROBADO[campania],
            "r09_run_id": RUN_R09_MULTI[campania],
            "nowcast_run_id": RUN_NOWCAST.get(campania),
            "usa_panel_excel": False,
            "usa_clima_futuro": False,
            "usa_estacionalidad": False,
            "usa_r09_como_predictor": False,
        },
        "preflight": {
            "filas_base": int(len(base)),
            "cobertura_candidato": 1.0,
            "objetivos_cerrados": bool(
                (base["fecha_objetivo"] + pd.Timedelta(days=6) <= CIERRES[campania]).all()
            ),
            "emisiones_previas": bool((base["fecha_emision"] < base["fecha_objetivo"]).all()),
            "real_desconocido_tratado_como_cero": False,
        },
        "comparacion_v2_vs_nowcast": _resumen_nowcast_vs_v2(v2, nowcast, campania),
        "metricas_por_horizonte": metricas,
        "r09_mismo_vintage": r09_ref,
        "loop": loop,
        "modelo_candidato": "ForecastResidualAsOfHorizonteAgnostico_v1",
        "alcance_correccion": "H2-H6; H1 conserva HibridoOcurrenciaOnline_v2",
        "persistible": False,
        "publicable": False,
        "decision": decision,
    }


__all__ = ["ejecutar"]
