"""Pruebas unitarias para el motor de descomposición de Bhattacharya."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analitica.aplicacion.parametros.automaticos import reemplazar_parametros_excel_por_db
from analitica.aplicacion.servicios.servicio_bhattacharya import (
    calibrar_todos_los_lotes,
    generar_proyeccion_empresa,
)
from analitica.dominio.nucleo.bhattacharya import (
    ParametrosBhattacharya,
    ajustar_lote,
    ajustar_lote_automatico,
    cdf_interval,
    proyectar_curva_oleadas,
    simular_escenario,
)


def test_ajuste_bhattacharya_lote_sintetico():
    """Verifica que el optimizador recupere los parámetros con precisión."""
    t_dias = np.array([168.0, 180.0, 199.0, 212.0, 224.0, 236.0])
    frutos_obs = np.array([15.0, 35.0, 85.0, 115.0, 105.0, 75.0])
    peso_obs = np.array([4.6, 4.4, 4.2, 4.0, 3.8, 3.7])

    params = ajustar_lote(
        t_dias=t_dias,
        frutos_obs=frutos_obs,
        peso_obs=peso_obs,
        N1=600.0,
        N2=300.0,
        N3=100.0,
        lote="L_TEST",
        campania="C2026",
    )

    assert isinstance(params, ParametrosBhattacharya)
    assert 200.0 <= params.mu1 <= 240.0
    assert 15.0 <= params.sigma1 <= 40.0
    assert params.mu2 == pytest.approx(params.mu1 + 70.0, abs=0.1)
    assert params.mu3 == pytest.approx(params.mu2 + 63.0, abs=0.1)
    assert 3.5 <= params.peso_a <= 10.0
    # Peso estimado en t=200d debe estar entre 3.0g y 5.0g
    peso_200 = params.peso_a * np.exp(params.peso_b * 200.0)
    assert 3.0 <= peso_200 <= 5.0
    assert params.peso_b < 0.0  # Decaimiento negativo


def test_proyeccion_curva_oleadas_suma_identidad():
    """Verifica que la suma de P1 + P2 + P3 sea idéntica a TotalEst en cada punto temporal."""
    params = ParametrosBhattacharya(
        lote="L224",
        campania="C2026",
        mu1=224.8,
        sigma1=23.7,
        N1=646.0,
        mu2=294.8,
        sigma2=32.4,
        N2=399.0,
        mu3=357.8,
        sigma3=32.2,
        N3=208.0,
        peso_a=4.63,
        peso_b=-0.0021,
    )

    df_curva = proyectar_curva_oleadas(params, t_start=150, t_end=420, step_days=7)

    assert not df_curva.empty
    assert "DDP" in df_curva.columns
    assert "FrtEst_p1" in df_curva.columns
    assert "FrtEst_p2" in df_curva.columns
    assert "FrtEst_p3" in df_curva.columns
    assert "TotalEst" in df_curva.columns

    # Validar que TotalEst == P1 + P2 + P3 dentro de 0.05 de tolerancia por redondeo
    suma_pob = df_curva["FrtEst_p1"] + df_curva["FrtEst_p2"] + df_curva["FrtEst_p3"]
    np.testing.assert_allclose(df_curva["TotalEst"].values, suma_pob.values, atol=0.1)


def test_proyeccion_curva_usa_peso_distinto_por_oleada():
    """La réplica conserva A1/B1, A2/B2 y A3/B3 del libro Excel."""
    params = ParametrosBhattacharya(
        lote="L_WEIGHT",
        campania="C2026",
        mu1=180.0,
        sigma1=20.0,
        N1=300.0,
        mu2=220.0,
        sigma2=20.0,
        N2=300.0,
        mu3=260.0,
        sigma3=20.0,
        N3=300.0,
        peso_a=3.0,
        peso_b=0.0,
        peso_a2=4.0,
        peso_b2=0.0,
        peso_a3=5.0,
        peso_b3=0.0,
        n_plantas=1000,
    )
    curva = proyectar_curva_oleadas(params, t_start=180, t_end=260, step_days=7)
    fila = curva[(curva.FrtEst_p1 > 0) & (curva.FrtEst_p2 > 0) & (curva.FrtEst_p3 > 0)].iloc[0]
    assert fila.PesoMedio_g == pytest.approx(
        (fila.FrtEst_p1 * 3 + fila.FrtEst_p2 * 4 + fila.FrtEst_p3 * 5) / fila.TotalEst,
        abs=0.02,
    )


def test_simulacion_what_if():
    """Verifica que simular_escenario aplique los deltas y factores correctamente."""
    params_base = ParametrosBhattacharya(
        lote="L042",
        campania="C2026",
        mu1=220.0,
        N1=500.0,
        mu2=290.0,
        N2=300.0,
    )

    params_ajustado = simular_escenario(
        params_base,
        delta_mu1=5.0,
        delta_mu2=10.0,
        factor_N2=0.8,
        nuevo_peso_a=5.0,
    )

    assert params_ajustado.mu1 == 225.0
    assert params_ajustado.mu2 == 300.0
    assert params_ajustado.N2 == 240.0
    assert params_ajustado.peso_a == 5.0


def test_generacion_proyeccion_empresa():
    """Verifica la agregación de múltiples lotes en matriz semanal."""
    params_map = {
        "L001": ParametrosBhattacharya(lote="L001", campania="C2026", modulo="M01", turno="T01"),
        "L002": ParametrosBhattacharya(lote="L002", campania="C2026", modulo="M01", turno="T02"),
    }

    df_det, df_mat = generar_proyeccion_empresa(params_map, t_start=180, t_end=300)

    assert len(df_mat) == 2
    assert "Lote" in df_mat.columns
    assert len(df_det) > 0


def test_ajuste_automatico_mantiene_frutos_en_escala_por_planta():
    t_fin = np.arange(160.0, 335.0, 14.0)
    t_ini = t_fin - 14.0
    frutos = (
        cdf_interval(t_fin, t_ini, 220.0, 24.0) * 650.0
        + cdf_interval(t_fin, t_ini, 290.0, 30.0) * 280.0
        + cdf_interval(t_fin, t_ini, 355.0, 32.0) * 120.0
    )
    peso = 5.2 * np.exp(-0.0015 * t_fin)
    params = ajustar_lote_automatico(
        t_dias=t_fin,
        frutos_obs=frutos,
        peso_obs=peso,
        lote_id="10",
        lote="L001",
    )

    assert params.lote_id == "10"
    assert 50 <= params.N1 <= 2000
    assert 5 <= params.N2 <= 1500
    assert 5 <= params.N3 <= 1000
    assert params.frutos_observados_total < 2000
    assert params.rmse_total < 15


def test_calibracion_db_no_mezcla_codigos_repetidos_entre_lotes_fisicos():
    filas = []
    for lote_id, fundo, escala in (("10", "Aqu Anqa 1", 1.0), ("20", "Aqu Anqa 2", 1.6)):
        for t_dias, frutos in ((180, 20), (195, 45), (210, 70)):
            filas.append(
                {
                    "lote_id": lote_id,
                    "lote": "L001",
                    "fundo": fundo,
                    "modulo": "M01",
                    "turno": "T01",
                    "t_dias": t_dias,
                    "frutos_obs": frutos * escala,
                    "peso_baya": 4.0,
                    "fecha_poda": pd.Timestamp("2026-01-01"),
                    "n_plantas": 5000,
                }
            )
    parametros, tabla = calibrar_todos_los_lotes(
        df_cosecha=pd.DataFrame(filas),
        campania="C2026",
        paralelo=False,
    )

    assert set(parametros) == {"10", "20"}
    assert len(tabla) == 2
    assert parametros["10"].fundo != parametros["20"].fundo


def test_adaptador_automatico_normaliza_lote_b_y_conserva_trazabilidad():
    base = pd.DataFrame(
        [
            {
                "Fundo": "Ayllu",
                "FundoPPto": "Ayllu",
                "Modulo": "M15",
                "Turno": "T01",
                "Lote": "L01B",
                "Area": 0.05,
                "NPlantas": 300,
                "FPoda": pd.Timestamp("2025-08-28"),
            }
        ]
    )
    objetivos = pd.DataFrame(
        [
            {
                "lote_id": "209",
                "fundo": "Aqu Anqa 4",
                "modulo": "M15",
                "turno": "T01",
                "lote": "L001B",
                "area_ha": 0.0598,
                "n_plantas": 335,
                "fecha_poda": pd.Timestamp("2025-08-28"),
            }
        ]
    )
    universo = {
        "209": ParametrosBhattacharya(
            lote_id="209",
            lote="L001B",
            campania="C2026",
            mu1=215,
            sigma1=24,
            N1=500,
            fuente_parametros="postgres",
            nivel_calibracion="lote_actual",
        )
    }
    resultado, meta = reemplazar_parametros_excel_por_db(
        base,
        fundo_operativo="Ayllu",
        universo=universo,
        objetivos=objetivos,
    )

    assert resultado.iloc[0].LoteIdDB == "209"
    assert resultado.iloc[0].X1 == 215
    assert resultado.iloc[0].NPlantas == 335
    assert resultado.iloc[0].FuenteParametros == "postgres_auto"
    assert meta["filas"] == 1


def test_generar_proyeccion_empresa_vacia_devuelve_tablas_vacias():
    detalle, matriz = generar_proyeccion_empresa({})
    assert detalle.empty
    assert list(matriz.columns) == ["Fundo", "Lote", "Modulo", "Turno"]
