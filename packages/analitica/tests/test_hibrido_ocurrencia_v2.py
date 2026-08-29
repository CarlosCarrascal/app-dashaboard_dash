import numpy as np
import pandas as pd

from analitica.proyeccion.hibrido_ocurrencia import ConfiguracionHibridoOcurrencia
from analitica.proyeccion.hibrido_ocurrencia_v2 import (
    NOMBRE_MODELO,
    ejecutar_replay_hibrido_ocurrencia_v2,
)
from analitica.proyeccion.metricas import metricas_cobertura_operacional


def _panel(semanas: int = 8, lotes: int = 40) -> pd.DataFrame:
    filas = []
    fechas = pd.date_range("2026-01-05", periods=semanas, freq="7D")
    for i, fecha in enumerate(fechas):
        for lote in range(lotes):
            base = 8.0 + (lote % 5) + i
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
                    "real_kg": base * (1.1 if i % 2 else 0.9),
                    "horizonte_semanas": 1,
                    "banda_horizonte": "operativo",
                }
            )
    return pd.DataFrame(filas)


def test_v2_conserva_toda_la_rejilla_y_el_calentamiento():
    panel = _panel()
    detalle, resumen = ejecutar_replay_hibrido_ocurrencia_v2(
        panel, ConfiguracionHibridoOcurrencia(semanas_calentamiento=5)
    )
    assert len(detalle) == len(panel)
    assert detalle.modelo.eq(NOMBRE_MODELO).all()
    assert detalle.emitio_prediccion.all()
    assert len(resumen) == panel.fecha_objetivo.nunique()
    estados = detalle.componentes.map(lambda x: x["estado_correccion"])
    assert (estados == "calentamiento_base").sum() == 5 * 40
    assert (estados == "ocurrencia_online").any()


def test_v2_no_lee_el_real_de_la_semana_objetivo():
    panel = _panel()
    original, _ = ejecutar_replay_hibrido_ocurrencia_v2(panel)
    alterado = panel.copy()
    ultima = alterado.fecha_objetivo.max()
    alterado.loc[alterado.fecha_objetivo.eq(ultima), "real_kg"] *= 1000
    nuevo, _ = ejecutar_replay_hibrido_ocurrencia_v2(alterado)
    a = original.loc[original.fecha_objetivo.eq(ultima), "p50_kg"].to_numpy()
    b = nuevo.loc[nuevo.fecha_objetivo.eq(ultima), "p50_kg"].to_numpy()
    assert np.allclose(a, b)


def test_metricas_separan_cobertura_y_precision():
    tabla = pd.DataFrame(
        {
            "lote_id": [1, 2],
            "real_kg": [100.0, 100.0],
            "p50_kg": [100.0, 0.0],
            "emitio_prediccion": [True, False],
        }
    )
    metricas = metricas_cobertura_operacional(tabla)
    assert metricas["wape_operacional"] == 0.5
    assert metricas["wape_condicionado"] == 0.0
    assert metricas["cobertura_lotes"] == 0.5
    assert metricas["cobertura_volumen"] == 0.5
