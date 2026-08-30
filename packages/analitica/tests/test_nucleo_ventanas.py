import pandas as pd
import pytest

from analitica.dominio.nucleo import datos as modulo_datos
from analitica.dominio.nucleo.contratos import Hallazgo
from analitica.dominio.nucleo.datos import diagnostico_ventanas as diagnostico_compat
from analitica.dominio.nucleo.ventanas import (
    _agregar_lags,
    _rolling_climatico,
    _rolling_por_modulo,
    _rolling_semanal,
    diagnostico_ventanas,
)


def test_rolling_semanal_cuenta_los_huecos_de_calendario():
    serie = pd.Series([10.0, 20.0], index=[1, 3])

    resultado = _rolling_semanal(serie, ventana=2)

    assert pd.isna(resultado.loc[2])
    assert pd.isna(resultado.loc[3])


def test_datos_conserva_aliases_privados_de_ventanas():
    assert modulo_datos._rolling_semanal is _rolling_semanal
    assert modulo_datos._rolling_climatico is _rolling_climatico
    assert modulo_datos._rolling_por_modulo is _rolling_por_modulo


def test_rolling_climatico_se_calcula_una_vez_por_semana():
    tabla = pd.DataFrame(
        {
            "nsem": [1, 1, 2, 2, 3, 3],
            "DPV": [10.0, 10.0, 20.0, 20.0, 30.0, 30.0],
        }
    )

    resultado = _rolling_climatico(tabla, "DPV", ventana=2)

    assert pd.isna(resultado.iloc[0])
    assert resultado.iloc[2] == pytest.approx(15.0)
    assert resultado.iloc[3] == pytest.approx(15.0)


def test_rolling_por_modulo_no_mezcla_fundos_y_respeta_huecos():
    tabla = pd.DataFrame(
        {
            "Fundo": ["A", "A", "A", "B", "B", "B"],
            "Modulo": ["M01"] * 3 + ["M01"] * 3,
            "nsem": [1, 2, 4, 1, 2, 3],
            "riego": [10.0, 20.0, 40.0, 100.0, 200.0, 300.0],
        }
    )

    resultado = _rolling_por_modulo(tabla, "riego", ventana=2)

    assert resultado.iloc[1] == pytest.approx(15.0)
    assert pd.isna(resultado.iloc[2])
    assert resultado.iloc[5] == pytest.approx(250.0)


def test_agregar_lags_conserva_hallazgo_y_diagnostico_compatible():
    tabla = pd.DataFrame(
        {
            "Fundo": ["A"] * 3,
            "Modulo": ["M01"] * 3,
            "nsem": [1, 2, 3],
            "DPV": [10.0, 20.0, 30.0],
            "Rad": [100.0, 110.0, 120.0],
            "ETo": [4.0, 5.0, 6.0],
            "gdd_semana": [20.0, 30.0, 40.0],
            "riego_lt_planta": [1.0, 2.0, 3.0],
            "TempMax": [25.0, 26.0, 27.0],
            "TempMin": [15.0, 16.0, 17.0],
        }
    )
    hallazgos: list[Hallazgo] = []

    salida = _agregar_lags(
        tabla.copy(),
        {"riego": 2, "Rad": 2, "ETo": 2, "DPV": 2, "gdd": 2},
        hallazgos,
    )

    assert {"DPV_lag", "riego_lag", "Rad_lag", "ETo_lag", "gdd_lag"} <= set(salida)
    assert any(h.clave == "lags_ventana_incompleta" for h in hallazgos)
    esperado = diagnostico_ventanas(salida, {"riego": 2, "Rad": 2, "ETo": 2, "DPV": 2, "gdd": 2})
    compatible = diagnostico_compat(salida, {"riego": 2, "Rad": 2, "ETo": 2, "DPV": 2, "gdd": 2})
    pd.testing.assert_frame_equal(esperado, compatible)
