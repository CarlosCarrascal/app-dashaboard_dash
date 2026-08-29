from __future__ import annotations

import pandas as pd

from analitica.proyeccion.ocurrencia import (
    OccurrenceConfig,
    construir_rejilla_ocurrencia,
    estimar_ocurrencia,
)


def _r09() -> pd.DataFrame:
    filas = []
    emisiones = pd.date_range("2026-01-05", periods=7, freq="W-MON")
    for indice, emision in enumerate(emisiones):
        for lote in (1, 2):
            objetivo = emision + pd.Timedelta(weeks=1)
            filas.append(
                {
                    "modelo": "R09_publicado",
                    "campania": "C2026",
                    "lote_id": lote,
                    "lote": f"L{lote}",
                    "fundo": "F1",
                    "modulo": "M1",
                    "fecha_emision": emision,
                    "fecha_objetivo": objetivo,
                    "horizonte_semanas": 1,
                    "banda_horizonte": "operativo",
                    "p50_kg": 100.0,
                    "p10_kg": 80.0,
                    "p90_kg": 120.0,
                    "real_kg": (
                        100.0
                        if indice % 2 == 0 and objetivo <= pd.Timestamp("2026-02-02")
                        else None
                    ),
                    "plantas": 1000.0,
                }
            )
    return pd.DataFrame(filas)


def test_la_rejilla_agrega_semanas_sin_cosecha_como_ceros():
    entrenamiento, futuro = construir_rejilla_ocurrencia(
        _r09(), emision=pd.Timestamp("2026-02-09"), horizonte=4
    )
    assert not entrenamiento.empty
    assert not futuro.empty
    assert (entrenamiento.real_kg == 0).any()
    assert futuro.real_kg.isna().all()
    assert futuro.horizonte_semanas.nunique() == 4


def test_la_ocurrencia_publica_probabilidad_y_gate():
    entrenamiento, futuro = construir_rejilla_ocurrencia(
        _r09(), emision=pd.Timestamp("2026-02-09"), horizonte=4
    )
    salida = estimar_ocurrencia(
        entrenamiento,
        futuro,
        config=OccurrenceConfig(umbral=0.5, minimo_entrenamiento=20),
    )
    assert salida.probabilidad_cosecha.between(0, 1).all()
    assert salida.ocurrencia_gate.dtype == bool
    assert len(salida) == len(futuro)
