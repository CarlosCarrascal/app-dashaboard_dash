from __future__ import annotations

import pandas as pd

from analitica.proyeccion.monitoreo import monitorear_llegada_reales


def test_monitoreo_registra_reales_deriva_y_fuera_de_rango():
    emisiones = pd.date_range("2025-01-06", periods=10, freq="W-MON")
    predicciones = pd.DataFrame(
        {
            "modelo": "R09_publicado",
            "fecha_emision": emisiones,
            "fecha_objetivo": emisiones + pd.Timedelta(days=7),
            "campania": ["C2025"] * 5 + ["C2026"] * 5,
            "banda_horizonte": "operativo",
            "real_kg": 100.0,
            "p10_kg": 90.0,
            "p50_kg": 100.0,
            "p90_kg": 110.0,
        }
    )
    emisiones_repetidas = emisiones.repeat(10)
    panel = pd.DataFrame(
        {
            "fecha_emision": emisiones_repetidas,
            "lote_id": list(range(10)) * 10,
            "temp_media_7d": [20.0] * 80 + [40.0] * 20,
            "eto_7d": [10.0] * 80 + [100.0] * 20,
        }
    )
    assert len(emisiones_repetidas) == 100
    controles = monitorear_llegada_reales(predicciones, panel)
    reglas = set(controles.regla)
    assert "monitoreo_reales_disponibles" in reglas
    assert "monitoreo_deriva_variables_psi" in reglas
    assert "monitoreo_lotes_fuera_rango_entrenamiento" in reglas
    deriva = controles[controles.regla == "monitoreo_deriva_variables_psi"].iloc[0]
    assert deriva.estado == "warning"
    assert deriva.afectados == 2
    fuera = controles[controles.regla == "monitoreo_lotes_fuera_rango_entrenamiento"].iloc[0]
    assert fuera.estado == "warning"
    assert fuera.afectados == 20
