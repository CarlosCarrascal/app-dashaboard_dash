from __future__ import annotations

import pandas as pd
import pytest

from analitica.aplicacion.procesos.hibrido_parametros_lagged import (
    ConfiguracionHibridoParametrosLagged,
    construir_hibrido_parametros_lagged,
    seleccionar_peso_parametros_asof,
)


def _forecast(horizontes=(1, 2, 3), escala=1.0):
    emision = pd.Timestamp("2026-08-03")
    filas = []
    for horizonte in horizontes:
        for lote, kg in ((1, 60.0), (2, 40.0)):
            filas.append(
                {
                    "campania": "C2026",
                    "fecha_emision": emision,
                    "fecha_objetivo": emision + pd.Timedelta(weeks=horizonte),
                    "horizonte_semanas": horizonte,
                    "lote_id": lote,
                    "p50_kg": kg * escala,
                }
            )
    return pd.DataFrame(filas)


def _naive(kg=80.0, fecha="2026-08-02"):
    return pd.DataFrame(
        [
            {
                "campania": "C2026",
                "fecha_emision": "2026-08-03",
                "fecha_real_referencia": fecha,
                "naive_total_kg": kg,
            }
        ]
    )


def test_h1_mezcla_total_y_conserva_distribucion_lotes():
    salida = construir_hibrido_parametros_lagged(
        _forecast(),
        _forecast(escala=2.0),
        _naive(),
        config=ConfiguracionHibridoParametrosLagged(peso_parametros_h1=0.95),
    )
    h1 = salida[salida.horizonte_semanas.eq(1)]
    assert h1.p50_kg.sum() == pytest.approx(99.0)
    assert h1.sort_values("lote_id").p50_kg.tolist() == pytest.approx([59.4, 39.6])
    assert set(h1.ruta_modelo) == {"parametros_lagged_h1"}


def test_h2_h6_conserva_macro_exactamente():
    macro = _forecast(escala=2.0)
    salida = construir_hibrido_parametros_lagged(_forecast(), macro, _naive())
    esperado = macro[macro.horizonte_semanas.ge(2)].sort_values(["horizonte_semanas", "lote_id"])
    actual = salida[salida.horizonte_semanas.ge(2)].sort_values(["horizonte_semanas", "lote_id"])
    assert actual.p50_kg.tolist() == esperado.p50_kg.tolist()
    assert set(actual.ruta_modelo) == {"macro_congelada_h2_h6"}


def test_rechaza_naive_no_cerrado_antes_de_emision():
    with pytest.raises(ValueError, match="semana cerrada antes"):
        construir_hibrido_parametros_lagged(_forecast(), _forecast(), _naive(fecha="2026-08-03"))


def test_rechaza_emision_contemporanea():
    lagged = _forecast()
    lagged.loc[0, "fecha_emision"] = lagged.loc[0, "fecha_objetivo"]
    with pytest.raises(ValueError, match="contemporánea"):
        construir_hibrido_parametros_lagged(lagged, _forecast(), _naive())


def test_no_necesita_ni_acepta_r09_para_construir_salida():
    lagged = _forecast()
    lagged["r09_kg"] = 999_999_999.0
    salida = construir_hibrido_parametros_lagged(lagged, _forecast(), _naive())
    assert salida.loc[salida.horizonte_semanas.eq(1), "p50_kg"].sum() == pytest.approx(99.0)


def test_rechaza_total_lagged_cero():
    lagged = _forecast()
    lagged.loc[lagged.horizonte_semanas.eq(1), "p50_kg"] = 0.0
    with pytest.raises(ValueError, match="total lagged igual a cero"):
        construir_hibrido_parametros_lagged(lagged, _forecast(), _naive())


def test_seleccion_peso_asof_ignora_resultados_cerrados_despues_de_emision():
    historial = pd.DataFrame(
        {
            "lagged_total_kg": [120.0, 1_000_000.0],
            "naive_total_kg": [80.0, 0.0],
            "real_kg": [100.0, 0.0],
            "fecha_cierre_real": ["2026-08-02", "2026-08-16"],
        }
    )
    peso = seleccionar_peso_parametros_asof(
        historial,
        fecha_emision="2026-08-10",
        config=ConfiguracionHibridoParametrosLagged(
            penalizacion_alejamiento_lagged=0.0,
            paso_busqueda_peso=0.05,
        ),
    )
    assert peso == pytest.approx(0.5)


def test_seleccion_peso_sin_historia_usa_curva_lagged_completa():
    historial = pd.DataFrame(
        columns=["lagged_total_kg", "naive_total_kg", "real_kg", "fecha_cierre_real"]
    )
    assert seleccionar_peso_parametros_asof(historial, fecha_emision="2026-08-10") == pytest.approx(
        1.0
    )
