"""Paridad y seguridad temporal de los micro-replays de estado experto."""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from analitica.aplicacion.servicios import estado_expertos
from analitica.interfaces.scripts import (
    screening_expert_override_state as override,
)
from analitica.interfaces.scripts import screening_residual_state_online as residual


def _contrato_sintetico() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "campania": "C2026",
                "semana_emision": 1,
                "semana_objetivo": 1,
                "fundo_operativo": "A",
                "macro_kg": 100.0,
                "real_kg": 120.0,
                "lagged_kg": 80.0,
                "lagged_disponible": True,
                "r09_kg": 110.0,
                "r09_disponible": True,
            },
            {
                "campania": "C2026",
                "semana_emision": 2,
                "semana_objetivo": 2,
                "fundo_operativo": "A",
                "macro_kg": 110.0,
                "real_kg": 100.0,
                "lagged_kg": 90.0,
                "lagged_disponible": True,
                "r09_kg": 888.0,
                "r09_disponible": True,
            },
        ]
    )


def test_scripts_son_fachadas_y_conservan_aliases() -> None:
    assert override.Configuracion is estado_expertos.ConfiguracionOverride
    assert override._predecir is estado_expertos.predecir_override
    assert override._actualizar is estado_expertos._actualizar_override
    assert override.ejecutar is estado_expertos.ejecutar_override
    assert residual.Configuracion is estado_expertos.ConfiguracionResidual
    assert residual._predecir_online is estado_expertos.predecir_residual_online
    assert residual._base is estado_expertos._base_residual
    assert residual._actualizar_estado is estado_expertos._actualizar_residual
    assert residual.ejecutar is estado_expertos.ejecutar_residual

    for nombre in ("screening_expert_override_state.py", "screening_residual_state_online.py"):
        ruta = Path(__file__).parents[1] / "interfaces" / "scripts" / nombre
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        assert {n.name for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)} == {"main"}


def test_override_conserva_paridad_de_fachada_en_fixture_sintetico() -> None:
    tabla = _contrato_sintetico()
    cfg = override.Configuracion(0.4, 0.3, 0.75, 4.0, 0.6)
    servicio = estado_expertos.predecir_override(tabla, cfg)
    fachada = override._predecir(tabla, cfg)
    assert_frame_equal(fachada, servicio)
    assert servicio.loc[0, "candidate_kg"] == 100.0
    assert servicio.loc[1, "candidate_kg"] != servicio.loc[1, "macro_kg"]


def test_residual_conserva_paridad_y_base_del_fixture_sintetico() -> None:
    tabla = _contrato_sintetico()
    cfg = residual.Configuracion(0.5, 0.5, 0.5, 4.0, 0.6)
    servicio = estado_expertos.predecir_residual_online(tabla, cfg)
    fachada = residual._predecir_online(tabla, cfg)
    assert_frame_equal(fachada, servicio)
    assert servicio.loc[0, "base_kg"] == 90.0
    assert servicio.loc[0, "candidate_kg"] == 90.0


def test_r09_contemporaneo_no_es_predictor_del_override() -> None:
    tabla = _contrato_sintetico()
    cfg = override.Configuracion(0.4, 0.3, 0.75, 4.0, 0.6)
    mutado = tabla.copy()
    mutado.loc[1, "r09_kg"] = 999_999.0
    original = estado_expertos.predecir_override(tabla, cfg)
    alterado = estado_expertos.predecir_override(mutado, cfg)
    assert alterado.loc[1, "candidate_kg"] == original.loc[1, "candidate_kg"]


def test_r09_no_es_predictor_de_la_correccion_residual() -> None:
    tabla = _contrato_sintetico()
    cfg = residual.Configuracion(0.5, 0.5, 0.5, 4.0, 0.6)
    mutado = tabla.copy()
    mutado["r09_kg"] = [1.0, 999_999.0]
    original = estado_expertos.predecir_residual_online(tabla, cfg)
    alterado = estado_expertos.predecir_residual_online(mutado, cfg)
    assert_frame_equal(
        original[["candidate_kg", "base_kg", "estado_global_log", "estado_fundo_log"]],
        alterado[["candidate_kg", "base_kg", "estado_global_log", "estado_fundo_log"]],
    )
