from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.aplicacion.procesos.gauss_estado_integrado import (
    NOMBRE_MODELO,
    construir_lotes_gauss_estado,
    proyectar_gauss_estado_asof,
    replay_gauss_estado_asof,
)
from analitica.aplicacion.procesos.torneo import ejecutar_torneo
from analitica.dominio.modelos.hibrido import MacroParams, proyectar_oleadas_horizonte


def _entradas() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    historia = proyectar_oleadas_horizonte(parametros, "2026-01-05", semanas=16)
    cosecha = historia.assign(
        campania="C2026",
        fundo="ARENA",
        modulo="M01",
        turno="T01",
        lote="L001",
        n_plantas=1000,
        fecha=historia.fecha_objetivo,
        pana=range(1, len(historia) + 1),
        peso=historia.peso_baya_g,
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
    emision = pd.Timestamp("2026-03-30")
    r09 = proyectar_oleadas_horizonte(parametros, emision, semanas=5).assign(
        campania="C2026",
        fundo="ARENA",
        modulo="M01",
        turno="T01",
        lote="L001",
        lote_id="M01|T01|L001",
        p10_kg=lambda tabla: tabla.kg * 0.5,
        p50_kg=lambda tabla: tabla.kg * 1.3,
        p90_kg=lambda tabla: tabla.kg * 1.7,
        real_kg=np.nan,
    )
    r09 = r09[
        [
            "campania",
            "lote_id",
            "fundo",
            "modulo",
            "turno",
            "lote",
            "fecha_emision",
            "fecha_objetivo",
            "horizonte_semanas",
            "p10_kg",
            "p50_kg",
            "p90_kg",
            "real_kg",
        ]
    ]
    lotes = pd.DataFrame(
        {
            "campania": ["C2026"],
            "fundo": ["ARENA"],
            "modulo": ["M01"],
            "turno": ["T01"],
            "lote": ["L001"],
            "area": [1.0],
            "n_plantas": [1000],
            "fecha_inicio": ["2025-10-01"],
        }
    )
    return r09, lotes, cosecha


def test_integra_nivel_r09_forma_gaussiana_y_extiende_h6():
    panel, lotes, cosecha = _entradas()

    salida, metadata = proyectar_gauss_estado_asof(
        panel,
        lotes,
        cosecha,
        "2026-03-30",
        peso_forma_gaussiana=1.0,
    )

    assert len(salida) == 6
    assert salida.modelo.eq(NOMBRE_MODELO).all()
    assert salida.horizonte_extendido.iloc[-1]
    assert salida.forma_gaussiana_asof.all()
    assert salida.tiene_descomposicion_oleadas.all()
    np.testing.assert_allclose(
        salida[[f"kg_ola_{indice}_ajustada" for indice in range(1, 4)]].sum(axis=1),
        salida.p50_kg,
    )
    assert metadata["usa_excel_para_calcular"] is False
    assert metadata["filas_h6_extendido"] == 1
    assert metadata["sin_fuga"] is True


def test_la_forma_gaussiana_no_lee_cosecha_posterior_a_la_emision():
    panel, lotes, cosecha = _entradas()
    futuro = cosecha.copy()
    futuro.loc[futuro.fecha.ge("2026-03-30"), "kg"] = 999999.0

    original, _ = proyectar_gauss_estado_asof(panel, lotes, cosecha, "2026-03-30")
    mutado, _ = proyectar_gauss_estado_asof(panel, lotes, futuro, "2026-03-30")

    np.testing.assert_allclose(original.p50_kg, mutado.p50_kg)
    np.testing.assert_allclose(original.kg_ola_1_ajustada, mutado.kg_ola_1_ajustada)


def test_la_forma_manual_tiene_prioridad_y_gaussiana_cubre_los_horizontes_faltantes():
    panel, lotes, cosecha = _entradas()
    manual = panel.assign(
        kg=lambda tabla: tabla.p50_kg * 2.0,
        kg_ola_1=lambda tabla: tabla.p50_kg * 0.20,
        kg_ola_2=lambda tabla: tabla.p50_kg * 0.50,
        kg_ola_3=lambda tabla: tabla.p50_kg * 0.30,
    )[
        [
            "campania",
            "modulo",
            "turno",
            "lote",
            "fecha_emision",
            "fecha_objetivo",
            "horizonte_semanas",
            "kg",
            "kg_ola_1",
            "kg_ola_2",
            "kg_ola_3",
        ]
    ]

    salida, metadata = proyectar_gauss_estado_asof(
        panel,
        lotes,
        cosecha,
        "2026-03-30",
        panel_oleadas_manual=manual,
    )

    assert salida.forma_fuente.iloc[:5].eq("manual_excel_asof").all()
    assert salida.forma_fuente.iloc[-1] == "gaussiana_asof"
    assert metadata["usa_forma_manual"] is True
    assert metadata["forma"]["filas_con_forma_manual"] == 5


def test_reconstruye_lotes_desde_maestro_y_poda_sin_turno():
    panel, lotes, _ = _entradas()
    maestro = lotes.drop(columns=["fecha_inicio"]).rename(
        columns={"n_plantas": "plantas"}
    )
    poda = pd.DataFrame(
        {
            "campania": ["C2026"],
            "modulo": ["M01"],
            "lote": ["L001"],
            "fecha_inicio": ["2025-10-01"],
        }
    )

    salida, metadata = construir_lotes_gauss_estado(
        panel,
        maestro_lotes=maestro,
        poda=poda,
    )

    assert len(salida) == 1
    assert salida.iloc[0].fecha_inicio == pd.Timestamp("2025-10-01")
    assert salida.iloc[0].plantas == 1000
    assert metadata["lotes_validos"] == 1


def test_replay_integrado_devuelve_metricas_y_comparacion_con_r09():
    panel, lotes, cosecha = _entradas()

    predicciones, metadata = replay_gauss_estado_asof(
        panel,
        lotes,
        cosecha,
        ["2026-03-30"],
    )

    assert predicciones.fecha_emision.nunique() == 1
    assert predicciones.modelo.eq(NOMBRE_MODELO).all()
    assert set(metadata["comparacion_r09"]) >= {"integrado", "r09"}
    assert metadata["sin_fuga"] is True
    assert metadata["publicable"] is False


def test_el_integrado_se_puede_encender_como_challenger_del_torneo():
    panel, lotes, cosecha = _entradas()
    panel["modelo"] = "R09_publicado"
    panel["kg_componentes"] = panel["p50_kg"]

    resultado = ejecutar_torneo(
        panel,
        cosecha,
        incluir_ml=False,
        incluir_statsforecast=False,
        incluir_componentes=False,
        incluir_fenologico_v1=False,
        incluir_macro_legacy=False,
        incluir_hibrido_legacy=False,
        incluir_gauss_estado=True,
        lotes_gauss_estado=lotes,
    )

    assert NOMBRE_MODELO in set(resultado.predicciones.modelo)
