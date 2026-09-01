from __future__ import annotations

import pandas as pd
import pytest

from analitica.aplicacion.procesos.r09_exportado import (
    cargar_panel_r09_csv,
    construir_panel_r09_exportado,
)


def _forecast() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "campania": "C2026",
                "fundo": "Aqu Anqa 1",
                "modulo": "M01",
                "turno": "T01",
                "lote": "L001",
                "fecha_cos": "2026-03-16",
                "version": "S10_v2",
                "kg": 10.0,
                "frt_cos": 20.0,
                "peso": 4.0,
                "frutos_total": 1000.0,
            },
            {
                "campania": "C2026",
                "fundo": "Aqu Anqa 1",
                "modulo": "M01",
                "turno": "T01",
                "lote": "L001",
                "fecha_cos": "2026-03-23",
                "version": "S10_v2",
                "kg": 12.0,
                "frt_cos": 21.0,
                "peso": 4.1,
                "frutos_total": 1100.0,
            },
            {
                "campania": "C2026",
                "fundo": "Aqu Anqa 1",
                "modulo": "M01",
                "turno": "T02",
                "lote": "L002",
                "fecha_cos": "2026-03-16",
                "version": "S10",
                "kg": 30.0,
                "frt_cos": 25.0,
                "peso": 4.2,
                "frutos_total": 2500.0,
            },
            # La variante numérica más alta es la oficial para la semana S10.
            {
                "campania": "C2026",
                "fundo": "Aqu Anqa 1",
                "modulo": "M01",
                "turno": "T02",
                "lote": "L002",
                "fecha_cos": "2026-03-16",
                "version": "S10_v2",
                "kg": 35.0,
                "frt_cos": 26.0,
                "peso": 4.3,
                "frutos_total": 2600.0,
            },
        ]
    )


def _cosecha() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "campania": "C2026",
                "fundo": "Aqu Anqa",
                "modulo": "M01",
                "turno": "T01",
                "lote": "L001",
                "fecha": "2026-03-16",
                "kg": 8.0,
                "peso": 3.9,
                "n_plantas": 100,
            },
            # Fila de exportación vacía: se descarta y queda reportada.
            {
                "campania": None,
                "fundo": None,
                "modulo": None,
                "turno": None,
                "lote": None,
                "fecha": None,
                "kg": None,
            },
        ]
    )


def test_construye_panel_con_identidad_fisica_y_no_mezcla_fundos():
    panel, metadata = construir_panel_r09_exportado(
        _forecast(),
        _cosecha(),
        pd.DataFrame(
            {
                "Modulo": ["M01", "M01"],
                "Turno": ["T01", "T02"],
                "Lote": ["L001", "L002"],
                "NPlantas": [100, 200],
                "Area": [1.0, 2.0],
            }
        ),
    )

    assert set(panel.lote_id) == {"M01|T01|L001", "M01|T02|L002"}
    reales_l001 = panel.loc[panel.lote_id.eq("M01|T01|L001"), "real_kg"].dropna()
    assert reales_l001.eq(8.0).all()
    assert panel.loc[panel.lote_id.eq("M01|T02|L002"), "p50_kg"].eq(35.0).all()
    assert panel.loc[panel.lote_id.eq("M01|T01|L001"), "plantas"].eq(100).all()
    assert metadata["identidad"] == "campania + modulo + turno + lote"
    assert metadata["filas_cosecha_descartadas"] == 1
    assert metadata["lotes_sin_plantas"] == 0


def test_rechaza_maestro_ambiguo():
    maestro = pd.DataFrame(
        {
            "modulo": ["M01", "M01"],
            "turno": ["T01", "T01"],
            "lote": ["L001", "L001"],
            "n_plantas": [100, 101],
        }
    )
    with pytest.raises(ValueError, match="repite módulo\\|turno\\|lote"):
        construir_panel_r09_exportado(_forecast(), _cosecha(), maestro)


def test_carga_los_tres_csv_y_deja_las_rutas_en_manifest(tmp_path):
    forecast = tmp_path / "r09.csv"
    cosecha = tmp_path / "h01.csv"
    maestro = tmp_path / "m_lotes.csv"
    _forecast().to_csv(forecast, index=False)
    _cosecha().to_csv(cosecha, index=False)
    pd.DataFrame(
        {
            "modulo": ["M01", "M01"],
            "turno": ["T01", "T02"],
            "lote": ["L001", "L002"],
            "n_plantas": [100, 200],
        }
    ).to_csv(maestro, index=False)

    panel, metadata = cargar_panel_r09_csv(forecast, cosecha, maestro)

    assert not panel.empty
    assert metadata["archivo_forecast"] == str(forecast)
    assert metadata["archivo_cosecha"] == str(cosecha)
    assert metadata["archivo_maestro"] == str(maestro)
