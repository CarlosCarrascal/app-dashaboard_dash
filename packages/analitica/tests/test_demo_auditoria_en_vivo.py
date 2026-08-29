from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from analitica.scripts import demo_auditoria_en_vivo as cli
from analitica.servicios import demo_auditoria_en_vivo as demo


def test_demo_reutilizable_preserva_datos_formulas_y_llamadas(monkeypatch, capsys):
    llamadas: list[dict] = []

    def ajustar_lote_falso(**kwargs):
        llamadas.append(kwargs)
        return SimpleNamespace(
            mu1=210.71 if len(llamadas) != 2 else 230.71,
            sigma1=25.0,
            N1=kwargs["N1"],
            peso_a=9.05,
        )

    monkeypatch.setattr(demo, "ajustar_lote", ajustar_lote_falso)

    demo.auditar_lote_en_vivo()

    salida = capsys.readouterr().out
    assert len(llamadas) == 3
    np.testing.assert_array_equal(llamadas[0]["t_dias"], [195.0, 215.0, 235.0])
    np.testing.assert_array_equal(llamadas[1]["t_dias"], [215.0, 235.0, 255.0])
    np.testing.assert_array_equal(llamadas[2]["t_dias"], [195.0, 215.0, 235.0])
    np.testing.assert_array_equal(llamadas[0]["frutos_obs"], [120.0, 480.0, 150.0])
    np.testing.assert_array_equal(llamadas[2]["frutos_obs"], [240.0, 960.0, 300.0])
    for llamada in llamadas:
        np.testing.assert_array_equal(llamada["peso_obs"], [4.5, 4.2, 3.9])
        assert llamada["lote"] == "LOTE_TEST"
        assert llamada["campania"] == "C2026"
        assert llamada["fundo"] == "Arena"
        assert llamada["modulo"] == "M01"
        assert llamada["turno"] == "T01"
        assert llamada["fecha_poda"].isoformat() == "2026-01-15T00:00:00"
        assert llamada["n_plantas"] == 5000
    assert [llamada["N1"] for llamada in llamadas] == [750.0, 750.0, 1500.0]
    assert [llamada["N2"] for llamada in llamadas] == [300.0, 300.0, 600.0]
    assert [llamada["N3"] for llamada in llamadas] == [100.0, 100.0, 200.0]
    assert all(llamada["sigma_min"] == 25.0 for llamada in llamadas)
    assert "Cambio exactamente +20 dias" in salida
    assert "Se duplico exactamente" in salida


def test_la_fachada_conserva_los_imports_historicos():
    assert cli.auditar_lote_en_vivo is demo.auditar_lote_en_vivo
    assert cli.ajustar_lote is demo.ajustar_lote


def test_demo_con_motor_real_conserva_resultados_matematicos(capsys):
    demo.auditar_lote_en_vivo()

    salida = capsys.readouterr().out
    assert "Pico de cosecha (X1): 210.71 dias" in salida
    assert "Pico de cosecha (X1): 230.71 dias" in salida
    assert "Carga Frutal (N1):   1500.00 frutos/planta" in salida
    assert "Peso Estimado:       9.05 g" in salida
