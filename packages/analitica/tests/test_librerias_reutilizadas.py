from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from analitica.dominio.evaluacion.reconciliacion import mint_shrink_no_negativo
from analitica.dominio.modelos.challengers import challenger_combinacion, intervalos_enbpi


def test_enbpi_produce_intervalos_ordenados():
    x = np.arange(60, dtype=float).reshape(-1, 1)
    y = 0.5 * x[:, 0] + np.sin(x[:, 0] / 3)
    p50, p10, p90 = intervalos_enbpi(
        RandomForestRegressor(n_estimators=20, random_state=42), x[:50], y[:50], x[50:]
    )
    assert p50.shape == p10.shape == p90.shape == (10,)
    assert np.all(p10 <= p50)
    assert np.all(p50 <= p90)


def test_mint_es_un_wrapper_real_de_hierarchicalforecast():
    codigo = inspect.getsource(mint_shrink_no_negativo)
    assert "HierarchicalReconciliation" in codigo
    assert 'MinTrace(method="mint_shrink", nonnegative=True' in codigo


def test_combinacion_usa_solo_error_pasado_y_pesos_inversos():
    filas = []
    for modelo, error, actual in (("A", 1.0, 10.0), ("B", 2.0, 16.0)):
        for i, emision in enumerate(pd.to_datetime(["2025-12-01", "2025-12-08"])):
            filas.append(
                {
                    "modelo": modelo,
                    "campania": "C2026",
                    "lote_id": 1,
                    "fecha_emision": emision,
                    "fecha_objetivo": emision + pd.Timedelta(days=7),
                    "banda_horizonte": "operativo",
                    "real_kg": 10.0,
                    "p10_kg": 10.0 - error,
                    "p50_kg": 10.0 + (-1 if i == 0 else 1) * error,
                    "p90_kg": 10.0 + error,
                }
            )
        filas.append(
            {
                "modelo": modelo,
                "campania": "C2026",
                "lote_id": 1,
                "fecha_emision": pd.Timestamp("2026-01-05"),
                "fecha_objetivo": pd.Timestamp("2026-01-12"),
                "banda_horizonte": "operativo",
                "real_kg": np.nan,
                "p10_kg": actual - 2,
                "p50_kg": actual,
                "p90_kg": actual + 2,
            }
        )
    resultado = challenger_combinacion(pd.DataFrame(filas), minimo_historial=2)
    actual = resultado[resultado.fecha_emision == pd.Timestamp("2026-01-05")].iloc[0]
    assert actual.p50_kg == 12
    assert actual.p10_kg <= actual.p50_kg <= actual.p90_kg
