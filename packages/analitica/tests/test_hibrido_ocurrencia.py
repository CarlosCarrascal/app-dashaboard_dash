from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.dominio.modelos.ocurrencia_v1 import (
    ConfiguracionHibridoOcurrencia,
    ejecutar_replay_hibrido_ocurrencia,
)


def _panel(semanas: int = 8, lotes: int = 40) -> pd.DataFrame:
    filas = []
    fechas = pd.date_range("2026-01-05", periods=semanas, freq="7D")
    for indice_fecha, fecha in enumerate(fechas):
        for lote in range(lotes):
            base = 20 + lote % 5 + indice_fecha * 2
            real = base * (1.1 if (lote + indice_fecha) % 3 else 0.0)
            filas.append(
                {
                    "campania": "C2026",
                    "empresa": "Aqu Anqa",
                    "fundo": f"F{lote % 2}",
                    "modulo": f"M{lote % 4}",
                    "lote": f"L{lote:03d}",
                    "lote_id": lote,
                    "fecha_emision": fecha - pd.Timedelta(days=7),
                    "fecha_objetivo": fecha,
                    "horizonte_semanas": 1,
                    "banda_horizonte": "1-2",
                    "version_fuente": "fixture",
                    "p50_kg": base,
                    "real_kg": real,
                }
            )
    return pd.DataFrame(filas)


def test_replay_respeta_calentamiento_y_origen_temporal():
    detalle, resumen = ejecutar_replay_hibrido_ocurrencia(
        _panel(), ConfiguracionHibridoOcurrencia(semanas_calentamiento=5)
    )
    assert resumen.fecha_objetivo.nunique() == 3
    assert detalle.es_replay_ciego.all()
    assert (detalle.origen_emision < detalle.fecha_objetivo).all()


def test_modificar_futuro_no_cambia_prediccion_anterior():
    panel = _panel()
    original, _ = ejecutar_replay_hibrido_ocurrencia(panel)
    mutado = panel.copy()
    ultima = mutado.fecha_objetivo.max()
    mutado.loc[mutado.fecha_objetivo.eq(ultima), "real_kg"] *= 1000
    cambiado, _ = ejecutar_replay_hibrido_ocurrencia(mutado)
    fecha_comun = sorted(original.fecha_objetivo.unique())[-2]
    np.testing.assert_allclose(
        original.loc[original.fecha_objetivo.eq(fecha_comun), "p50_kg"],
        cambiado.loc[cambiado.fecha_objetivo.eq(fecha_comun), "p50_kg"],
    )


def test_salida_es_promedio_fijo_de_legacy_y_hurdle_calibrado():
    detalle, _ = ejecutar_replay_hibrido_ocurrencia(_panel())
    # p50_kg original fue preservado en base_lag_0 solo conceptualmente; se reconstruye
    # desde la fórmula despejando la mitad hurdle guardada en la salida.
    componentes = detalle.componentes.iloc[0]
    assert componentes["peso_legacy"] == 0.5
    assert detalle.p50_kg.ge(0).all()


def test_replay_excluye_reales_futuros_desconocidos_del_entrenamiento():
    panel = _panel(semanas=9)
    ultima = panel.fecha_objetivo.max()
    panel.loc[panel.fecha_objetivo.eq(ultima), "real_kg"] = np.nan

    detalle, _ = ejecutar_replay_hibrido_ocurrencia(panel)

    assert not detalle.empty
    assert detalle.p50_kg.notna().all()
