from __future__ import annotations

import pandas as pd
import pytest

from analitica.proyeccion.hibrido.macro import MacroParams, parametros_desde_fila, proyectar_macro


def test_la_macro_legacy_reconstruye_la_identidad_de_kilos():
    params = MacroParams(
        area_ha=1.5,
        plantas=1000,
        fecha_pivote=pd.Timestamp("2026-01-01"),
        ola_1_media_dias=30,
        ola_1_desvio_dias=10,
        ola_1_multiplicador=100,
        ola_2_media_dias=45,
        ola_2_desvio_dias=10,
        ola_2_multiplicador=50,
        ola_3_media_dias=60,
        ola_3_desvio_dias=10,
        ola_3_multiplicador=25,
        peso_1_base_g=3.0,
        peso_1_tasa=0.0,
        peso_2_base_g=3.0,
        peso_2_tasa=0.0,
        peso_3_base_g=3.0,
        peso_3_tasa=0.0,
    )
    salida = proyectar_macro(
        params,
        pd.DataFrame(
            {
                "pasada": [1],
                "fecha_inicio": ["2026-01-01"],
                "fecha_objetivo": ["2026-02-15"],
            }
        ),
    )
    fila = salida.iloc[0]
    assert fila.frutos_por_planta > 0
    assert fila.peso_baya_g == pytest.approx(3.0)
    assert fila.kg == pytest.approx(fila.plantas * fila.frutos_por_planta * fila.peso_baya_g / 1000)


def test_los_parametros_se_leen_por_nombre_y_no_por_indice():
    params = parametros_desde_fila(
        {
            "Area": 1.0,
            "NPlantas": 100,
            "FPoda": "2026-01-01",
            "X1": 10,
            "O1": 2,
            "N1": 4,
            "X2": 20,
            "O2": 2,
            "N2": 3,
            "X3": 30,
            "O3": 2,
            "N3": 2,
            "A1": 3,
            "B1": 0,
            "A2": 3,
            "B2": 0,
            "A3": 3,
            "B3": 0,
        }
    )
    assert params.plantas == 100
    assert params.ola_2_multiplicador == 3
    assert params.peso_3_base_g == 3
