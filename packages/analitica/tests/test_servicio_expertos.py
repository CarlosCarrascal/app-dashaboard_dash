"""Paridad y contratos públicos del ajuste experto online."""

from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from analitica.scripts import screening_expert_adjustment_online as facade
from analitica.servicios import expertos


def _tabla_contrato() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campania": ["C2026"] * 8,
            "semana_emision": [1, 1, 1, 2, 2, 2, 3, 3],
            "semana_objetivo": [1, 1, 2, 2, 3, 3, 4, 4],
            "fundo_operativo": ["A", "B", "A", "B", "A", "B", "A", "B"],
            "macro_kg": [100.0, 80.0, 110.0, 82.0, 120.0, 85.0, 130.0, 88.0],
            "lagged_kg": [105.0, None, 115.0, 90.0, None, 95.0, 140.0, 90.0],
            "real_kg": [102.0, 79.0, 112.0, 88.0, 119.0, 91.0, 135.0, 92.0],
            "lagged_disponible": [True, False, True, True, False, True, True, True],
            "r09_disponible": [True, False, True, False, True, False, True, True],
            "r09_kg": [101.0, 0.0, 114.0, 0.0, 121.0, 0.0, 136.0, 89.0],
        }
    )


def test_fachada_reexporta_el_contrato_del_servicio() -> None:
    assert facade.Configuracion is expertos.Configuracion
    assert facade.ejecutar is expertos.ejecutar
    assert facade.predecir_online is expertos.predecir_online
    assert facade.metricas is expertos.metricas
    assert facade.cargar_contrato is expertos.cargar_contrato
    assert facade._ajustes is expertos._ajustes
    assert facade._cargar_contrato is expertos._cargar_contrato
    assert facade._keyset_sha256 is expertos._keyset_sha256
    assert facade._metricas is expertos._metricas
    assert facade._minimizar_absoluto is expertos._minimizar_absoluto
    assert facade._minimizar_escala is expertos._minimizar_escala
    assert facade._predecir_online is expertos._predecir_online
    assert facade.leer_macro_h1 is expertos.leer_macro_h1
    assert facade.leer_reales_r09_fundo is expertos.leer_reales_r09_fundo
    assert facade.normalizar_fundo is expertos.normalizar_fundo


def test_prediccion_conserva_la_paridad_del_micro_replay() -> None:
    configuracion = expertos.Configuracion(0.25, 6.0, 8.0, True)
    salida = expertos.predecir_online(_tabla_contrato(), configuracion)
    esperada = _tabla_contrato().sort_values(
        ["semana_objetivo", "fundo_operativo"], kind="stable"
    ).copy()
    esperada["candidate_kg"] = [101.25, 80.0, 111.25, 84.0, 120.0, 87.5, 132.5, 88.5]
    esperada["gamma"] = [0.25, 0.0, 0.25, 0.25, 0.0, 0.25, 0.25, 0.25]
    esperada["escala"] = 1.0
    esperada["n_historia_fundo"] = [0, 0, 1, 0, 0, 1, 2, 2]
    esperada["ruta"] = [
        "ajuste_experto_regularizado",
        "macro_sin_parametros",
        "ajuste_experto_regularizado",
        "ajuste_experto_regularizado",
        "macro_sin_parametros",
        "ajuste_experto_regularizado",
        "ajuste_experto_regularizado",
        "ajuste_experto_regularizado",
    ]
    assert_frame_equal(salida, esperada)


def test_r09_no_es_predictor_del_ajuste_online() -> None:
    configuracion = expertos.Configuracion(0.25, 6.0, 8.0, True)
    original = expertos.predecir_online(_tabla_contrato(), configuracion)
    sin_r09 = _tabla_contrato().assign(
        r09_disponible=False,
        r09_kg=999_999.0,
    )
    alterado = expertos.predecir_online(sin_r09, configuracion)
    columnas_candidato = [
        "semana_objetivo",
        "fundo_operativo",
        "candidate_kg",
        "gamma",
        "escala",
        "n_historia_fundo",
        "ruta",
    ]
    assert_frame_equal(
        original[columnas_candidato].reset_index(drop=True),
        alterado[columnas_candidato].reset_index(drop=True),
    )
