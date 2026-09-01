from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from analitica.aplicacion.parametros import (
    proyectar_automatico_oleadas,
    proyectar_universo_automatico_oleadas,
)
from analitica.aplicacion.parametros.oleadas_candidato import proyectar_candidato_oleadas
from analitica.dominio.modelos.hibrido import (
    MacroParams,
    ajustar_oleadas_asof,
    atribuir_cambio_oleadas,
    construir_prior_automatico,
    proyectar_fila_manual_horizonte,
    proyectar_oleadas_horizonte,
)
from analitica.dominio.modelos.hibrido.oleadas_asof import _normalizar_observaciones


def _parametros_base() -> MacroParams:
    return MacroParams(
        area_ha=1.0,
        plantas=1000,
        fecha_pivote=pd.Timestamp("2025-12-01"),
        ola_1_media_dias=40,
        ola_1_desvio_dias=8,
        ola_1_multiplicador=100,
        ola_2_media_dias=75,
        ola_2_desvio_dias=10,
        ola_2_multiplicador=60,
        ola_3_media_dias=115,
        ola_3_desvio_dias=12,
        ola_3_multiplicador=30,
        peso_1_base_g=4.0,
        peso_1_tasa=0.0,
        peso_2_base_g=4.2,
        peso_2_tasa=0.0,
        peso_3_base_g=4.4,
        peso_3_tasa=0.0,
    )


def test_proyecta_seis_semanas_y_conserva_identidad_por_oleada():
    salida = proyectar_oleadas_horizonte(
        _parametros_base(),
        "2026-01-05",
        semanas=6,
    )

    assert len(salida) == 6
    assert salida.horizonte_semanas.tolist() == [1, 2, 3, 4, 5, 6]
    assert salida.fecha_objetivo.iloc[0] == pd.Timestamp("2026-01-12")
    np.testing.assert_allclose(
        salida.kg,
        salida[["kg_ola_1", "kg_ola_2", "kg_ola_3"]].sum(axis=1),
    )
    np.testing.assert_allclose(
        salida.frutos_por_planta,
        salida[["frutos_ola_1", "frutos_ola_2", "frutos_ola_3"]].sum(axis=1),
    )
    assert salida.kg_acumulado.iloc[-1] == pytest.approx(salida.kg.sum())


def test_fila_manual_usa_las_columnas_nombradas_xonab():
    fila = {
        "Area": 1.0,
        "NPlantas": 1000,
        "FPoda": "2025-12-01",
        "X1": 40,
        "O1": 8,
        "N1": 100,
        "X2": 75,
        "O2": 10,
        "N2": 60,
        "X3": 115,
        "O3": 12,
        "N3": 30,
        "A1": 4.0,
        "B1": 0.0,
        "A2": 4.2,
        "B2": 0.0,
        "A3": 4.4,
        "B3": 0.0,
    }
    salida = proyectar_fila_manual_horizonte(fila, "2026-01-05", semanas=6)

    assert len(salida) == 6
    assert salida.plantas.eq(1000).all()
    assert salida.kg.gt(0).any()


def test_ajuste_asof_no_lee_observaciones_posteriores_al_corte():
    base = _parametros_base()
    verdadero = replace(
        base,
        ola_1_media_dias=46,
        ola_2_media_dias=82,
        ola_3_media_dias=124,
        ola_1_multiplicador=125,
        ola_2_multiplicador=70,
    )
    observadas = proyectar_oleadas_horizonte(verdadero, "2026-01-05", semanas=14)
    historicas = observadas.loc[observadas.fecha_objetivo < pd.Timestamp("2026-03-02")].copy()
    futuras = observadas.loc[observadas.fecha_objetivo >= pd.Timestamp("2026-03-02")].copy()
    futuras["frutos_por_planta"] = futuras.frutos_por_planta * 100
    combinadas = pd.concat([historicas, futuras], ignore_index=True)

    solo_historicas = ajustar_oleadas_asof(
        base,
        historicas,
        fecha_corte="2026-03-02",
    )
    con_futuras = ajustar_oleadas_asof(
        base,
        combinadas,
        fecha_corte="2026-03-02",
    )

    assert con_futuras.n_observaciones == len(historicas)
    for campo in (
        "ola_1_media_dias",
        "ola_2_media_dias",
        "ola_3_media_dias",
        "ola_1_multiplicador",
        "ola_2_multiplicador",
        "ola_3_multiplicador",
        "peso_1_base_g",
        "peso_1_tasa",
    ):
        assert getattr(con_futuras.parametros, campo) == pytest.approx(
            getattr(solo_historicas.parametros, campo)
        )


def test_normaliza_h01_consolida_filas_diarias_de_una_misma_pasada():
    observaciones = pd.DataFrame(
        {
            "campania": ["C2026"] * 3,
            "fundo": ["Arena"] * 3,
            "modulo": ["M01"] * 3,
            "turno": ["T01"] * 3,
            "lote": ["L001"] * 3,
            "pana": [1, 1, 2],
            "fecha": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-20"]),
            "kg": [100.0, 150.0, 200.0],
            "peso": [4.0, 4.2, 4.1],
            "n_plantas": [1000] * 3,
        }
    )

    salida, advertencias = _normalizar_observaciones(
        observaciones,
        _parametros_base(),
        fecha_corte="2026-02-01",
        intervalo_dias=7,
    )

    assert len(salida) == 2
    assert "observaciones_agrupadas_por_pasada_sin_intervalos_solapados" in advertencias
    assert salida.t_fin.tolist() == [36.0, 50.0]
    assert salida.t_inicio.tolist() == [29.0, 36.0]
    peso_conservativo = 250 / (100 / 4.0 + 150 / 4.2)
    assert salida.peso_obs.iloc[0] == pytest.approx(peso_conservativo)
    assert salida.frutos_obs.iloc[0] == pytest.approx(250 / peso_conservativo)


def test_normaliza_h01_no_mezcla_lotes_con_la_misma_pasada():
    observaciones = pd.DataFrame(
        {
            "campania": ["C2026"] * 4,
            "fundo": ["Arena"] * 4,
            "modulo": ["M01"] * 4,
            "turno": ["T01"] * 4,
            "lote": ["L001", "L001", "L002", "L002"],
            "pana": [1, 1, 1, 1],
            "fecha": pd.to_datetime(
                ["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06"]
            ),
            "kg": [100.0, 150.0, 300.0, 300.0],
            "peso": [4.0, 4.0, 5.0, 5.0],
            "n_plantas": [1000] * 4,
        }
    )

    salida, _ = _normalizar_observaciones(
        observaciones,
        _parametros_base(),
        fecha_corte="2026-02-01",
        intervalo_dias=7,
    )

    assert len(salida) == 2
    assert sorted(salida.peso_obs.tolist()) == [4.0, 5.0]


def test_normaliza_no_reagrupa_si_el_llamador_entrega_intervalos_explicitos():
    observaciones = pd.DataFrame(
        {
            "lote": ["L001", "L001"],
            "pana": [1, 1],
            "fecha": pd.to_datetime(["2026-01-12", "2026-01-19"]),
            "t_inicio": [35.0, 42.0],
            "t_fin": [42.0, 49.0],
            "frutos_por_planta": [10.0, 12.0],
            "peso": [4.0, 4.1],
        }
    )

    salida, advertencias = _normalizar_observaciones(
        observaciones,
        _parametros_base(),
        fecha_corte="2026-02-01",
        intervalo_dias=7,
    )

    assert len(salida) == 2
    assert "observaciones_agrupadas_por_pasada_sin_intervalos_solapados" not in advertencias
    assert salida.t_inicio.tolist() == [35.0, 42.0]


def test_normaliza_aplica_corte_estricto_antes_de_agrupar_una_pasada():
    observaciones = pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "fundo": ["Arena", "Arena"],
            "modulo": ["M01", "M01"],
            "turno": ["T01", "T01"],
            "lote": ["L001", "L001"],
            "pana": [1, 1],
            "fecha": pd.to_datetime(["2026-01-05", "2026-02-01"]),
            "kg": [100.0, 1000.0],
            "peso": [4.0, 4.0],
            "n_plantas": [1000, 1000],
        }
    )

    salida, _ = _normalizar_observaciones(
        observaciones,
        _parametros_base(),
        fecha_corte="2026-02-01",
        intervalo_dias=7,
    )

    assert len(salida) == 1
    assert salida.frutos_obs.iloc[0] == pytest.approx(25.0)


def test_ajuste_asof_reporta_soporte_bajo_sin_fallar():
    base = _parametros_base()
    observaciones = proyectar_oleadas_horizonte(base, "2026-01-05", semanas=3)

    resultado = ajustar_oleadas_asof(
        base,
        observaciones,
        fecha_corte="2026-02-01",
    )

    assert resultado.n_observaciones == 3
    assert "pocas_observaciones_para_identificar_tres_oleadas" in resultado.advertencias


def test_atribucion_identifica_que_el_cambio_vino_de_la_carga_de_ola_2():
    base = _parametros_base()
    final = replace(base, ola_2_multiplicador=120)
    detalle = atribuir_cambio_oleadas(base, final, "2026-01-05", semanas=6)

    por_bloque = detalle.groupby("bloque", as_index=True).delta_kg.sum()
    assert por_bloque["amplitud_carga"] > 0
    for bloque in ("timing", "dispersion", "calibre", "merma"):
        assert por_bloque[bloque] == pytest.approx(0.0)
    assert detalle.interpretacion.str.contains("no evidencia causal").all()


def test_orquestador_conecta_delta_excel_con_proyeccion_h6():
    fila = {
        "Area": 1.0,
        "NPlantas": 1000,
        "FPoda": "2025-12-01",
        "X1": 40,
        "O1": 8,
        "N1": 100,
        "X2": 75,
        "O2": 10,
        "N2": 60,
        "X3": 115,
        "O3": 12,
        "N3": 30,
        "A1": 4.0,
        "B1": 0.0,
        "A2": 4.2,
        "B2": 0.0,
        "A3": 4.4,
        "B3": 0.0,
    }

    class DeltaFalso:
        def predict(self, _previos, _contexto):
            return {
                "parametros": {"N2": 120},
                "nivel_calibracion": "modulo",
                "n_observaciones": 4,
                "detalle_calibracion": {"N2": {"delta_aplicado": 60}},
            }

    salida, metadata = proyectar_candidato_oleadas(
        fila,
        "2026-01-05",
        modelo_deltas=DeltaFalso(),
        contexto={"fundo": "Arena", "modulo": "M01", "lote": "L001"},
    )

    assert len(salida) == 6
    assert set(salida.modelo) == {"HibridoOleadasAsOf_v1"}
    assert metadata["fuente_parametros"] == "excel_delta_asof"
    assert metadata["n_transiciones_delta"] == 4


def test_prior_automatico_proyecta_h6_sin_excel():
    verdadero = replace(
        _parametros_base(),
        ola_1_media_dias=46,
        ola_2_media_dias=82,
        ola_3_media_dias=124,
    )
    historia = proyectar_oleadas_horizonte(verdadero, "2026-01-05", semanas=12)
    historia = historia[["fecha_objetivo", "frutos_por_planta", "peso_baya_g"]]

    salida, metadata = proyectar_automatico_oleadas(
        "2026-03-02",
        fecha_pivote="2025-12-01",
        plantas=1000,
        area_ha=1.0,
        observaciones=historia,
    )

    assert len(salida) == 6
    assert salida.kg.ge(0).all()
    assert metadata["fuente_parametros"] == "prior_automatico_oleadas_asof"
    assert metadata["ajuste_oleadas"]["n_observaciones"] > 0


def test_prior_automatico_puede_recibir_una_campana_historica():
    historico = replace(_parametros_base(), ola_2_multiplicador=140)
    resultado = construir_prior_automatico(
        fecha_pivote="2026-01-01",
        plantas=2000,
        area_ha=2.0,
        prior=historico,
        observaciones=pd.DataFrame(),
    )
    trasladado = resultado.parametros
    assert trasladado.ola_2_multiplicador == pytest.approx(140)
    assert trasladado.plantas == 2000
    assert trasladado.area_ha == pytest.approx(2.0)
    assert resultado.fuente == "historico_prior_sin_observaciones_asof"


def test_ajuste_sin_historia_conserva_el_prior_y_avisa():
    historico = replace(_parametros_base(), ola_2_multiplicador=140)
    resultado = ajustar_oleadas_asof(
        historico,
        pd.DataFrame(),
        fecha_corte="2026-03-02",
        fuente_prior="historico",
    )
    trasladado = resultado.parametros
    assert trasladado.ola_2_multiplicador == pytest.approx(140)
    assert "sin_historia_utilizable_asof" in resultado.advertencias


def test_orquestador_universo_emite_h6_sin_excel_y_corta_historia_futura():
    lotes = pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "fundo": ["Arena", "Arena"],
            "modulo": ["M01", "M01"],
            "turno": ["T01", "T02"],
            "lote": ["L001", "L002"],
            "area": [1.0, 1.2],
            "n_plantas": [1000, 1200],
            "fecha_inicio": ["2025-12-01", "2025-12-01"],
        }
    )
    cosecha = pd.DataFrame(
        {
            "campania": ["C2026", "C2026", "C2026"],
            "fundo": ["Arena"] * 3,
            "modulo": ["M01"] * 3,
            "turno": ["T01", "T01", "T01"],
            "lote": ["L001"] * 3,
            "fecha": pd.to_datetime(["2026-01-12", "2026-02-02", "2026-03-09"]),
            "kg": [100.0, 160.0, 900.0],
            "peso": [4.0, 3.9, 3.8],
            "n_plantas": [1000] * 3,
        }
    )

    salida, metadata = proyectar_universo_automatico_oleadas(
        lotes,
        cosecha,
        "2026-03-02",
    )

    assert len(salida) == 12
    assert salida.groupby("lote").size().to_dict() == {"L001": 6, "L002": 6}
    assert salida.loc[salida.lote.eq("L001"), "tiene_historia_asof"].all()
    assert not salida.loc[salida.lote.eq("L002"), "tiene_historia_asof"].any()
    assert salida.loc[salida.lote.eq("L001"), "n_observaciones_oleadas_asof"].eq(2).all()
    assert metadata["n_lotes"] == 2
    assert metadata["n_filas"] == 12
    assert metadata["lotes_con_historia_asof"] == 1
    assert metadata["fecha_corte"] == "2026-03-02"


def test_orquestador_universo_rechaza_un_horizonte_menor_a_seis():
    lotes = pd.DataFrame(
        {
            "campania": ["C2026"],
            "fundo": ["Arena"],
            "modulo": ["M01"],
            "turno": ["T01"],
            "lote": ["L001"],
            "area": [1.0],
            "n_plantas": [1000],
            "fecha_inicio": ["2025-12-01"],
        }
    )
    with pytest.raises(ValueError, match="entre 6 y 52"):
        proyectar_universo_automatico_oleadas(lotes, None, "2026-03-02", semanas=5)
