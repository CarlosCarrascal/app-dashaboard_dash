from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandera.errors import SchemaError

from analitica.proyeccion.contratos import validar_backtest
from analitica.proyeccion.metricas import (
    bootstrap_diferencia_wape_pareada,
    cobertura,
    interval_score,
    mae,
    pinball,
    porcentaje_series_ganadas,
    sesgo,
    wape,
)
from analitica.proyeccion.versiones import banda_horizonte, parsear_version


@pytest.mark.parametrize(
    ("codigo", "semana", "iteracion", "escenario", "oficial"),
    [
        ("S31", 31, 1, None, True),
        ("S31_v2", 31, 2, None, True),
        ("S31_vDR", 31, None, "DR", False),
        ("invalida", None, None, "no_parseable", False),
    ],
)
def test_versiones_r09_distinguen_iteracion_y_escenario(
    codigo, semana, iteracion, escenario, oficial
):
    resultado = parsear_version(codigo)
    assert (resultado.semana_emision, resultado.iteracion, resultado.escenario) == (
        semana,
        iteracion,
        escenario,
    )
    assert resultado.oficial is oficial


def test_bandas_de_horizonte():
    assert [banda_horizonte(i) for i in (1, 2, 3, 6, 7, 10)] == [
        "operativo",
        "operativo",
        "planificacion",
        "planificacion",
        "escenario",
        "escenario",
    ]


def test_formulas_de_error_e_intervalos():
    real = np.array([10.0, 20.0])
    pred = np.array([8.0, 24.0])
    assert mae(real, pred) == pytest.approx(3.0)
    assert wape(real, pred) == pytest.approx(0.2)
    assert sesgo(real, pred) == pytest.approx(2 / 30)
    assert pinball(real, pred, 0.5) == pytest.approx(1.5)
    assert cobertura(real, [7, 19], [11, 25]) == 1
    assert interval_score(real, [7, 19], [11, 25]) == pytest.approx(5)


def test_contrato_rechaza_p50_negativo():
    tabla = pd.DataFrame(
        {
            "campania": ["C2026"],
            "lote_id": [1],
            "lote": ["L001"],
            "fundo": ["F1"],
            "modulo": ["M01"],
            "fecha_emision": [pd.Timestamp("2026-01-05")],
            "fecha_objetivo": [pd.Timestamp("2026-01-12")],
            "horizonte_semanas": [1],
            "banda_horizonte": ["operativo"],
            "version_fuente": ["S02"],
            "modelo": ["R09_publicado"],
            "p10_kg": [0.0],
            "p50_kg": [-1.0],
            "p90_kg": [2.0],
            "real_kg": [1.0],
        }
    )
    with pytest.raises(SchemaError):
        validar_backtest(tabla)


def test_bootstrap_pareado_y_porcentaje_de_lotes_reportan_ventaja():
    fechas = pd.date_range("2026-01-05", periods=10, freq="W-MON")
    base = pd.DataFrame(
        {
            "campania": "C2026",
            "lote_id": 1,
            "fecha_emision": fechas,
            "fecha_objetivo": fechas + pd.Timedelta(days=7),
            "modelo": "R09_publicado",
            "real_kg": np.arange(100.0, 110.0),
            "p50_kg": np.arange(120.0, 130.0),
        }
    )
    candidato = base.copy()
    candidato["modelo"] = "challenger"
    candidato["p50_kg"] = candidato.real_kg
    tabla = pd.concat([base, candidato], ignore_index=True)
    inferior, superior = bootstrap_diferencia_wape_pareada(tabla, "challenger", repeticiones=100)
    assert inferior < 0
    assert superior < 0
    assert porcentaje_series_ganadas(tabla, "challenger") == 1.0
