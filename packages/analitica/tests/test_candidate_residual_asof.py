from __future__ import annotations

import pandas as pd
import pytest

from analitica.proyeccion.candidate_residual_asof import (
    ConfiguracionResidualAsOf,
    aplicar_calibracion_residual_asof,
)


def _panel() -> pd.DataFrame:
    filas = []
    for semana, real in enumerate((100.0, 120.0, 140.0, 160.0), start=1):
        objetivo = pd.Timestamp("2026-01-05") + pd.to_timedelta(semana - 1, unit="W")
        emision = objetivo - pd.to_timedelta(1, unit="W")
        filas.append(
            {
                "campania": "C2026",
                "fecha_emision": emision,
                "fecha_objetivo": objetivo,
                "horizonte_semanas": 1,
                "lote_id": 1,
                "fundo": "Arena",
                "modulo": "M01",
                "p50_kg": real / 2,
                "real_kg": real,
            }
        )
    return pd.DataFrame(filas)


def test_calibracion_solo_aprende_de_semanas_cerradas_antes_de_emision():
    config = ConfiguracionResidualAsOf(nivel="global", ventana=8, regularizacion=0, factor_max=2.0)
    base = _panel()
    primero = aplicar_calibracion_residual_asof(base, config)
    mutado = base.copy()
    mutado.loc[mutado.fecha_objetivo.eq(pd.Timestamp("2026-01-26")), "real_kg"] = 999999
    segundo = aplicar_calibracion_residual_asof(mutado, config)

    # La prediccion de la misma semana se emite antes de conocer su resultado.
    assert primero.loc[3, "p50_kg"] == pytest.approx(segundo.loc[3, "p50_kg"])
    assert primero.loc[0, "factor_residual_asof"] == 1.0
    assert primero.loc[2, "factor_residual_asof"] > 1.0


def test_calibracion_no_cambia_el_universo_ni_produce_negativos():
    base = _panel()
    salida = aplicar_calibracion_residual_asof(base)

    assert len(salida) == len(base)
    assert set(salida.lote_id) == set(base.lote_id)
    assert salida.p50_kg.ge(0).all()
    assert salida.modelo.eq("CandidateResidualAsOf_v1").all()


def test_rechaza_emision_contemporanea():
    base = _panel()
    base.loc[0, "fecha_emision"] = base.loc[0, "fecha_objetivo"]
    with pytest.raises(ValueError, match="contemporanea"):
        aplicar_calibracion_residual_asof(base)
