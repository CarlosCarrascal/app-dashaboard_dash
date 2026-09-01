from __future__ import annotations

import pandas as pd

from analitica.aplicacion.procesos.replay_oleadas_automatico import (
    replay_automatico_oleadas_asof,
)


def test_replay_solo_mide_semanas_cerradas_y_conserva_futuras_fuera_del_denominador():
    lotes = pd.DataFrame(
        {
            "campania": ["C2026"],
            "fundo": ["Arena"],
            "modulo": ["M01"],
            "turno": ["T01"],
            "lote": ["L001"],
            "area": [1.0],
            "n_plantas": [1000],
            "fecha_inicio": ["2025-01-01"],
        }
    )
    cosecha = pd.DataFrame(
        {
            "campania": ["C2026"] * 3,
            "fundo": ["Arena"] * 3,
            "modulo": ["M01"] * 3,
            "turno": ["T01"] * 3,
            "lote": ["L001"] * 3,
            "fecha": ["2026-01-12", "2026-01-19", "2026-01-26"],
            "kg": [100.0, 0.0, 50.0],
        }
    )

    predicciones, metadata = replay_automatico_oleadas_asof(
        lotes,
        cosecha,
        ["2026-01-05"],
        semanas=6,
    )

    assert len(predicciones) == 6
    assert predicciones.incluye_en_metricas.tolist() == [True, True, False, False, False, False]
    assert predicciones.real_kg.iloc[0] == 100.0
    assert predicciones.real_kg.iloc[1] == 0.0
    assert pd.isna(predicciones.real_kg.iloc[2])
    assert metadata["fecha_cierre_real"] == "2026-01-26"
    assert metadata["ultima_semana_completa"] == "2026-01-19"
    assert metadata["filas_evaluables"] == 2
    assert metadata["metricas"]["real_kg"] == 100.0
    assert metadata["sin_fuga"] is True
