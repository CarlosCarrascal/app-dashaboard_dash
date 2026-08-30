from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

from analitica.aplicacion.servicios import nowcast as SERVICIO

SCRIPTS = Path(__file__).parents[1] / "interfaces" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "screening_intraweek_nowcast.py"
SPEC = importlib.util.spec_from_file_location("screening_intraweek_nowcast_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULO = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULO
SPEC.loader.exec_module(MODULO)


def _semanas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campania": ["C2026"] * 5,
            "semana_objetivo": [20, 21, 22, 23, 24],
            "real_kg": [100.0, 120.0, 150.0, 180.0, 210.0],
            "montue_kg": [40.0, 48.0, 60.0, 72.0, 84.0],
            "macro_kg": [90.0, 105.0, 140.0, 170.0, 195.0],
            "candidate_kg": [98.0, 116.0, 145.0, 174.0, 202.0],
            "r09_previo_kg": [95.0, 130.0, 140.0, 190.0, 205.0],
            "r09_misma_semana_kg": [101.0, 121.0, 148.0, 179.0, 208.0],
        }
    )


def _semanas_por_fundo() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "semana_objetivo": [20, 21, 22, 23, 24],
            "fundo_operativo": ["Arena"] * 5,
            "real_kg": [100.0, 120.0, 150.0, 180.0, 210.0],
            "montue_kg": [40.0, 48.0, 60.0, 72.0, 84.0],
            "fecha_max": pd.date_range("2026-05-17", periods=5, freq="7D"),
        }
    )


def test_fachada_intraweek_reexporta_la_implementacion_del_servicio() -> None:
    assert MODULO.Configuracion is SERVICIO.Configuracion
    assert MODULO._predecir is SERVICIO._predecir
    assert MODULO._calibrar_residuo_online is SERVICIO._calibrar_residuo_online
    assert MODULO._comparacion_pareada is SERVICIO._comparacion_pareada
    assert MODULO.ejecutar is SERVICIO.ejecutar_intraweek


def test_calibracion_residual_no_usa_el_real_de_su_propia_semana() -> None:
    original = MODULO._calibrar_residuo_online(_semanas(), lookback=2, shrink=8.0)
    mutado = _semanas()
    mutado.loc[mutado.semana_objetivo.eq(24), "real_kg"] = 9_999_999.0
    repetido = MODULO._calibrar_residuo_online(mutado, lookback=2, shrink=8.0)

    assert repetido.loc[4, "candidate_kg"] == pytest.approx(original.loc[4, "candidate_kg"])
    assert repetido.loc[4, "escala_residual"] == pytest.approx(original.loc[4, "escala_residual"])


def test_mutar_el_futuro_no_cambia_predicciones_anteriores() -> None:
    original = MODULO._calibrar_residuo_online(_semanas(), lookback=2, shrink=8.0)
    mutado = _semanas()
    mutado.loc[mutado.semana_objetivo.ge(23), "real_kg"] *= 100.0
    repetido = MODULO._calibrar_residuo_online(mutado, lookback=2, shrink=8.0)

    pd.testing.assert_series_equal(
        original.loc[original.semana_objetivo.le(23), "candidate_kg"].reset_index(drop=True),
        repetido.loc[repetido.semana_objetivo.le(23), "candidate_kg"].reset_index(drop=True),
    )


def test_predecir_no_usa_datos_de_semanas_posteriores() -> None:
    contrato = _semanas()[
        ["campania", "semana_objetivo", "real_kg", "montue_kg", "macro_kg"]
    ].copy()
    diario = _semanas_por_fundo()
    cfg = MODULO.Configuracion(
        lookback=0,
        shrink_fundo=4.0,
        peso_ritmo=0.85,
        piso_share=0.15,
        techo_share=0.60,
    )
    original = MODULO._predecir(contrato, diario, cfg)
    mutado = diario.copy()
    mutado.loc[mutado.semana_objetivo.ge(23), ["real_kg", "montue_kg"]] *= 100.0
    repetido = MODULO._predecir(contrato, mutado, cfg)

    columnas = ["pace_kg", "candidate_kg", "share_global", "n_historia"]
    pd.testing.assert_frame_equal(
        original.loc[original.semana_objetivo.le(22), columnas].reset_index(drop=True),
        repetido.loc[repetido.semana_objetivo.le(22), columnas].reset_index(drop=True),
    )


def test_comparacion_pareada_usa_solo_semanas_comunes() -> None:
    tabla = _semanas()
    tabla.loc[1, "r09_misma_semana_kg"] = None
    resultado = MODULO._comparacion_pareada(
        tabla,
        "r09_misma_semana_kg",
        repeticiones=200,
    )

    assert resultado is not None
    assert resultado["n_semanas_comunes"] == 4
    assert resultado["candidato"]["n"] == resultado["referencia"]["n"] == 4
    assert len(resultado["bootstrap_diferencia_wape_pp_ic95"]) == 2


def test_r09_no_es_predictor_del_nowcast() -> None:
    contrato = _semanas()[
        ["campania", "semana_objetivo", "real_kg", "montue_kg", "macro_kg"]
    ].copy()
    diario = _semanas_por_fundo()
    cfg = MODULO.Configuracion(
        lookback=0,
        shrink_fundo=4.0,
        peso_ritmo=0.85,
        piso_share=0.15,
        techo_share=0.60,
    )
    base = contrato.assign(r09_previo_kg=1.0, r09_misma_semana_kg=2.0)
    mutado = contrato.assign(r09_previo_kg=999_999.0, r09_misma_semana_kg=888_888.0)
    original = MODULO._predecir(base, diario, cfg)
    repetido = MODULO._predecir(mutado, diario, cfg)

    columnas = ["pace_kg", "candidate_kg", "share_global", "n_historia"]
    pd.testing.assert_frame_equal(original[columnas], repetido[columnas])
    assert "r09_" not in SERVICIO._predecir.__code__.co_names
