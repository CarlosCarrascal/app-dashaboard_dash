"""Orquestación y reporte del screening run73."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from .turno_reingreso_configuracion import (
    aplicar_configuracion,
    auditar_paridad_funcion_pura,
    rejilla_configuraciones,
)
from .turno_reingreso_contexto import derivar_contexto_asof, enriquecer_macro
from .turno_reingreso_fuentes import (
    CAMPANIA,
    CIERRE_CERTIFICADO,
    CONTRACT_ID,
    GRUPO_CURVA,
    HORIZONTE_MAX,
    HORIZONTE_MIN,
    RUN_ID,
    preparar_macro,
    preparar_r09,
)
from .turno_reingreso_metricas import (
    _hash_claves,
    _metricas_bandas,
    _semanas_ganadas,
    comparar_r09_despues,
    seleccionar_configuracion,
)


def evaluar_panel(
    macro: pd.DataFrame,
    r09: pd.DataFrame,
    h01: pd.DataFrame,
) -> dict[str, Any]:
    base = preparar_macro(macro)
    referencia = preparar_r09(r09)
    contexto = derivar_contexto_asof(base, h01)
    curva = enriquecer_macro(base, contexto)
    candidatos = [
        (config, aplicar_configuracion(curva, config)) for config in rejilla_configuraciones()
    ]
    config, seleccionado, screening = seleccionar_configuracion(curva, candidatos)
    candidato_seleccionado = next(
        candidato for config_candidato, candidato in candidatos if config_candidato == config
    )
    paridad_pura = auditar_paridad_funcion_pura(curva, config, candidato_seleccionado)
    if not paridad_pura["paridad"]:
        raise ValueError("La ruta vectorizada no coincide con la funcion pura")

    desarrollo = seleccionado[seleccionado.split.eq("desarrollo_s13_s30")].copy()
    holdout = seleccionado[seleccionado.split.eq("holdout_s31_s33")].copy()
    metricas = {
        "desarrollo_s13_s30": {
            "macro": _metricas_bandas(desarrollo, "macro_kg"),
            "candidate": _metricas_bandas(desarrollo, "candidate_kg"),
            "semanas_ganadas_empresa_vs_macro": _semanas_ganadas(
                desarrollo, "candidate_kg", "macro_kg"
            ),
            "semanas_ganadas_fundo_vs_macro": _semanas_ganadas(
                desarrollo, "candidate_kg", "macro_kg", por_fundo=True
            ),
        },
        "holdout_s31_s33": {
            "macro": _metricas_bandas(holdout, "macro_kg"),
            "candidate": _metricas_bandas(holdout, "candidate_kg"),
            "semanas_ganadas_empresa_vs_macro": _semanas_ganadas(
                holdout, "candidate_kg", "macro_kg"
            ),
            "semanas_ganadas_fundo_vs_macro": _semanas_ganadas(
                holdout, "candidate_kg", "macro_kg", por_fundo=True
            ),
        },
    }
    r09_resultado = comparar_r09_despues(seleccionado, referencia)
    grupos = curva.groupby(GRUPO_CURVA).size()
    feature = curva.drop_duplicates(GRUPO_CURVA)
    disponible = feature.fecha_ultima_cosecha_asof.notna() & feature.dias_reingreso.notna()
    aplicado = seleccionado.estado_candidate.eq("calendario_reingreso_aplicado")
    total_base = curva.groupby(GRUPO_CURVA).p50_kg.sum()
    total_cand = seleccionado.groupby(GRUPO_CURVA).candidate_kg.sum()
    return {
        "schema": "screening-turno-reingreso-multihorizon-v1",
        "candidate_only": True,
        "persistencia_postgresql": False,
        "publicado": False,
        "run_base": RUN_ID,
        "campania": CAMPANIA,
        "evaluation_contract": {
            "id": CONTRACT_ID,
            "horizontes": [HORIZONTE_MIN, HORIZONTE_MAX],
            "seleccion": "S13-S30",
            "holdout": "S31-S33",
            "cierre_certificado": CIERRE_CERTIFICADO.date().isoformat(),
            "filas_h1_h6": int(len(curva)),
            "curvas_emision_lote": int(len(grupos)),
            "min_filas_por_curva": int(grupos.min()),
            "max_filas_por_curva": int(grupos.max()),
            "lotes": int(curva.lote_id.nunique()),
            "emisiones": int(curva.fecha_emision.nunique()),
            "keyset_sha256": _hash_claves(curva),
        },
        "feature_asof": {
            "curvas_con_turno_reingreso": int(disponible.sum()),
            "curvas_totales": int(len(feature)),
            "cobertura_curvas": float(disponible.mean()),
            "niveles_reingreso": feature.nivel_reingreso.value_counts().to_dict(),
            "regla": (
                "ultimo H01 positivo y Turno anteriores a emision; mediana de "
                "intervalos 5-21 dias con jerarquia lote -> modulo+turno -> "
                "fundo+turno -> turno -> modulo -> fundo -> global"
            ),
        },
        "seleccion": {
            "configuracion": asdict(config),
            "criterio": (
                "0.45*WAPE empresa h1 + 0.30*WAPE empresa h2-h6 + "
                "0.25*WAPE fundo h1-h6, calculado solo en S13-S30"
            ),
            "n_configuraciones": int(len(screening)),
            "screening": screening,
        },
        "conservacion_h1_h6": {
            "cambio_max_abs_kg_por_emision_lote": float((total_cand - total_base).abs().max()),
            "conserva_total": bool(np.allclose(total_cand, total_base)),
            "filas_con_calendario_aplicado": int(aplicado.sum()),
            "filas_totales": int(len(seleccionado)),
            "paridad_funcion_pura": paridad_pura,
        },
        "metricas_vs_macro": metricas,
        "comparacion_r09_posterior": r09_resultado,
        "veredicto": {
            "mejora_macro_holdout": bool(
                metricas["holdout_s31_s33"]["candidate"]["h1_h6"]["empresa_semana"]["wape"]
                < metricas["holdout_s31_s33"]["macro"]["h1_h6"]["empresa_semana"]["wape"]
            ),
            "supera_r09_condicionado_holdout": r09_resultado["veredicto_holdout"][
                "supera_r09_condicionado"
            ],
        },
    }
