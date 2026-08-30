import numpy as np
import pandas as pd

from analitica.dominio.modelos.ocurrencia_v3 import (
    NOMBRE_MODELO,
    ejecutar_replay_hibrido_ocurrencia_v3,
)


def _panel(semanas: int = 10, lotes: int = 40) -> pd.DataFrame:
    filas = []
    fechas = pd.date_range("2026-01-05", periods=semanas, freq="7D")
    for i, fecha in enumerate(fechas):
        for lote in range(lotes):
            base = 100 + (lote % 7) * 5 + i * 3
            real = base * (1.15 if i >= 5 else 0.9)
            filas.append(
                {
                    "campania": "C2026",
                    "empresa": "Aqu Anqa",
                    "fundo": "Aqu Anqa 1" if lote < lotes / 2 else "Aqu Anqa 2",
                    "modulo": f"M{lote % 4:02d}",
                    "lote": f"L{lote:03d}",
                    "lote_id": str(lote),
                    "fecha_emision": fecha - pd.Timedelta(days=7),
                    "fecha_objetivo": fecha,
                    "p50_kg": base,
                    "real_kg": real,
                    "horizonte_semanas": 1,
                    "banda_horizonte": "operativo",
                }
            )
    return pd.DataFrame(filas)


def test_v3_conserva_universo_y_componentes():
    panel = _panel()
    detalle, resumen = ejecutar_replay_hibrido_ocurrencia_v3(panel)
    assert len(detalle) == len(panel)
    assert len(resumen) == panel.fecha_objetivo.nunique()
    assert detalle.modelo.eq(NOMBRE_MODELO).all()
    assert detalle.emitio_prediccion.all()
    assert detalle.p50_kg.ge(0).all()
    assert detalle.componentes.map(lambda x: x["modelo_base"]).eq("MacroLegacy_v1").all()


def test_v3_no_usa_real_de_la_semana_objetivo():
    panel = _panel()
    original, _ = ejecutar_replay_hibrido_ocurrencia_v3(panel)
    mutado = panel.copy()
    ultima = mutado.fecha_objetivo.max()
    mutado.loc[mutado.fecha_objetivo.eq(ultima), "real_kg"] *= 1000
    cambiado, _ = ejecutar_replay_hibrido_ocurrencia_v3(mutado)
    np.testing.assert_allclose(
        original.loc[original.fecha_objetivo.eq(ultima), "p50_kg"],
        cambiado.loc[cambiado.fecha_objetivo.eq(ultima), "p50_kg"],
    )


def test_v3_rechaza_duplicados():
    panel = _panel()
    duplicado = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)
    try:
        ejecutar_replay_hibrido_ocurrencia_v3(duplicado)
    except ValueError as exc:
        assert "repite" in str(exc)
    else:
        raise AssertionError("El v3 debe rechazar duplicados de lote-semana")
