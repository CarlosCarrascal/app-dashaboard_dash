from __future__ import annotations

import pandas as pd

from analitica.aplicacion.parametros.transiciones_inferidas import (
    construir_transiciones_gaussianas_asof,
)
from analitica.dominio.modelos.hibrido import MacroParams, proyectar_oleadas_horizonte


def _datos() -> tuple[pd.DataFrame, pd.DataFrame]:
    parametros = MacroParams(
        area_ha=1.0,
        plantas=1000,
        fecha_pivote=pd.Timestamp("2025-10-01"),
        ola_1_media_dias=120.0,
        ola_1_desvio_dias=18.0,
        ola_1_multiplicador=180.0,
        ola_2_media_dias=175.0,
        ola_2_desvio_dias=22.0,
        ola_2_multiplicador=110.0,
        ola_3_media_dias=235.0,
        ola_3_desvio_dias=26.0,
        ola_3_multiplicador=60.0,
        peso_1_base_g=4.2,
        peso_1_tasa=-0.0005,
        peso_2_base_g=4.3,
        peso_2_tasa=-0.0005,
        peso_3_base_g=4.4,
        peso_3_tasa=-0.0005,
    )
    reales = proyectar_oleadas_horizonte(parametros, "2026-01-05", semanas=18)
    cosecha = reales.assign(
        campania="C2025",
        fundo="Arena",
        modulo="M01",
        turno="T01",
        lote="L001",
        n_plantas=1000,
        fecha=reales.fecha_objetivo,
        pana=range(1, len(reales) + 1),
        peso=reales.peso_baya_g,
    )[
        [
            "campania",
            "fundo",
            "modulo",
            "turno",
            "lote",
            "n_plantas",
            "fecha",
            "pana",
            "kg",
            "peso",
        ]
    ]
    lotes = pd.DataFrame(
        {
            "campania": ["C2025"],
            "fundo": ["Arena"],
            "modulo": ["M01"],
            "turno": ["T01"],
            "lote": ["L001"],
            "area": [1.0],
            "n_plantas": [1000],
            "fecha_inicio": ["2025-10-01"],
        }
    )
    return lotes, cosecha


def test_construye_transicion_gaussiana_asof_sin_excel():
    lotes, cosecha = _datos()

    salida, metadata = construir_transiciones_gaussianas_asof(
        lotes,
        cosecha,
        ["2026-03-02", "2026-04-06"],
        minimo_observaciones=6,
    )

    assert len(salida) == 1
    assert metadata["fuente"] == "h01_gaussian_asof_inferido"
    assert metadata["inferencia"] is True
    assert metadata["sin_fuga"] is True
    assert salida.transicion_inferida.all()
    assert salida.etiqueta_causal.eq(False).all()
    assert salida.fecha_emision_actual.iloc[0] == pd.Timestamp("2026-04-06")
    assert salida.n_observaciones_anterior.iloc[0] >= 6
    assert salida.n_observaciones_actual.iloc[0] >= salida.n_observaciones_anterior.iloc[0]
    assert salida["X1_anterior"].notna().all()
    assert salida["X1_actual"].notna().all()


def test_no_conserva_transicion_si_un_corte_no_tiene_historia_suficiente():
    lotes, cosecha = _datos()

    salida, metadata = construir_transiciones_gaussianas_asof(
        lotes,
        cosecha,
        ["2026-01-20", "2026-02-03"],
        minimo_observaciones=6,
    )

    assert salida.empty
    assert metadata["transiciones"] == 0
