from __future__ import annotations

import pandas as pd
import pytest

from analitica.aplicacion.procesos.candidatos import (
    ConfiguracionTurnoTemporal,
    aplicar_turno_reingreso_candidate,
    auditar_universo_candidate,
    construir_nowcast_separado,
    estimar_desplazamiento_temporal_asof,
    metricas_adversariales,
    normalizar_forecast_candidate,
)


def _curva() -> pd.DataFrame:
    filas = []
    emision = pd.Timestamp("2026-08-17")
    for horizonte, kg in enumerate((60.0, 30.0, 10.0), start=1):
        filas.append(
            {
                "evaluation_contract_id": 99,
                "campania": "C2026",
                "modelo": "MacroLegacy_v1",
                "version_modelo": "congelada",
                "fecha_emision": emision,
                "fecha_objetivo": emision + pd.to_timedelta(int(horizonte), unit="W"),
                "horizonte_semanas": horizonte,
                "lote_id": 1,
                "fundo": "Arena",
                "turno": "T01",
                "dias_reingreso": 20,
                "p50_kg": kg,
                "real_kg": kg,
            }
        )
    return pd.DataFrame(filas)


def test_rechaza_emisiones_mezcladas_y_horizonte_incorrecto():
    curva = _curva()
    duplicado = curva.iloc[[0]].copy()
    duplicado["lote_id"] = 2
    duplicado["fecha_emision"] = pd.Timestamp("2026-08-18")
    mezclado = pd.DataFrame([*curva.to_dict("records"), *duplicado.to_dict("records")])
    with pytest.raises(ValueError, match="mezcla emisiones"):
        normalizar_forecast_candidate(mezclado)

    horizonte_malo = _curva()
    horizonte_malo.loc[0, "horizonte_semanas"] = 2
    with pytest.raises(ValueError, match="horizonte declarado"):
        normalizar_forecast_candidate(horizonte_malo)


def test_turno_reingreso_conserva_volumen_y_no_lee_cosecha_futura():
    curva = _curva()
    historia = pd.DataFrame(
        {
            "campania": ["C2026", "C2026", "C2026"],
            "lote_id": [1, 1, 1],
            "fecha": pd.to_datetime(["2026-08-10", "2026-08-17", "2026-09-20"]),
            "fecha_disponible": pd.to_datetime(["2026-08-11", "2026-08-17", "2026-09-21"]),
            "kg": [25.0, 8_888.0, 9_999.0],
        }
    )
    config = ConfiguracionTurnoTemporal(peso_calendario=0.8, dispersion_semanas=0.5)
    primero = aplicar_turno_reingreso_candidate(curva, historia, config=config)
    mutado = historia.copy()
    mutado.loc[mutado.fecha.ge(pd.Timestamp("2026-08-17")), "kg"] *= 1000
    segundo = aplicar_turno_reingreso_candidate(curva, mutado, config=config)

    assert primero.p50_kg.sum() == pytest.approx(curva.p50_kg.sum())
    assert primero.loc[primero.horizonte_semanas.eq(2), "p50_kg"].iat[0] > 30.0
    pd.testing.assert_series_equal(primero.p50_kg, segundo.p50_kg)
    assert primero.estado_candidate.eq("calendario_reingreso_aplicado").all()


def test_desplazamiento_temporal_solo_usa_semanas_cerradas_antes_de_emision():
    fechas = pd.date_range("2026-01-05", periods=8, freq="7D")
    historial = pd.DataFrame(
        {
            "fundo": ["Arena"] * 8,
            "fecha_objetivo": fechas,
            "pred_base_kg": [0, 10, 20, 30, 40, 30, 20, 10],
            "real_kg": [10, 20, 30, 40, 30, 20, 10, 0],
        }
    )
    config = ConfiguracionTurnoTemporal(
        semanas_minimas_desplazamiento=6,
        penalizacion_desplazamiento=0.0,
    )
    original = estimar_desplazamiento_temporal_asof(
        historial, fecha_emision="2026-03-02", config=config
    )
    futuro = pd.concat(
        [
            historial,
            pd.DataFrame(
                {
                    "fundo": ["Arena"],
                    "fecha_objetivo": [pd.Timestamp("2026-03-09")],
                    "pred_base_kg": [1.0],
                    "real_kg": [1_000_000.0],
                }
            ),
        ],
        ignore_index=True,
    )
    mutado = estimar_desplazamiento_temporal_asof(futuro, fecha_emision="2026-03-02", config=config)

    assert original == mutado
    assert original["Arena"] == -1


def test_nowcast_es_separado_y_no_usa_datos_posteriores_a_emision():
    filas = []
    for lunes in pd.date_range("2026-07-20", periods=4, freq="7D"):
        for dia, kg in enumerate((10, 20, 30, 20, 20)):
            fecha = lunes + pd.to_timedelta(int(dia), unit="D")
            filas.append(
                {
                    "campania": "C2026",
                    "fecha": fecha,
                    "fecha_disponible": fecha,
                    "kg": kg,
                }
            )
    actual = pd.Timestamp("2026-08-17")
    filas.extend(
        [
            {"campania": "C2026", "fecha": actual, "fecha_disponible": actual, "kg": 20},
            {
                "campania": "C2026",
                "fecha": actual + pd.to_timedelta(1, unit="D"),
                "fecha_disponible": actual + pd.to_timedelta(1, unit="D"),
                "kg": 40,
            },
            {
                "campania": "C2026",
                "fecha": actual + pd.to_timedelta(3, unit="D"),
                "fecha_disponible": actual + pd.to_timedelta(3, unit="D"),
                "kg": 9999,
            },
        ]
    )
    cosecha = pd.DataFrame(filas)
    prior = pd.DataFrame({"campania": ["C2026"], "fecha_objetivo": [actual], "p50_kg": [250.0]})
    primero = construir_nowcast_separado(prior, cosecha, fecha_emision="2026-08-18")
    mutado = cosecha.copy()
    mutado.loc[mutado.fecha.gt(pd.Timestamp("2026-08-18")), "kg"] *= 1000
    segundo = construir_nowcast_separado(prior, mutado, fecha_emision="2026-08-18")

    assert primero.tipo_prediccion.iat[0] == "nowcast"
    assert not bool(primero.incluye_en_metricas_forecast.iat[0])
    assert primero.kg_parcial_asof.iat[0] == 60.0
    assert primero.p50_kg.iat[0] == pytest.approx(segundo.p50_kg.iat[0])


def test_metrica_agregada_puede_ocultar_error_grave_por_lote():
    universo = pd.concat([_curva().iloc[[0]], _curva().iloc[[0]]], ignore_index=True)
    universo.loc[0, ["lote_id", "p50_kg", "real_kg"]] = [1, 100.0, 100.0]
    universo.loc[1, ["lote_id", "p50_kg", "real_kg"]] = [2, 100.0, 100.0]
    candidato = universo.copy()
    candidato.loc[0, "p50_kg"] = 200.0
    candidato.loc[1, "p50_kg"] = 0.0

    metricas = metricas_adversariales(universo, candidato)

    assert metricas["wape_empresa_semana"] == 0.0
    assert metricas["wape_lote_semana"] == 1.0
    assert metricas["brecha_cancelacion"] == 1.0


def test_universo_es_comparable_aunque_cambie_el_nombre_del_modelo():
    universo = _curva()
    candidato = universo.copy()
    candidato["modelo"] = "CandidateTurnoTemporal_v1"

    auditoria = auditar_universo_candidate(universo, candidato)

    assert auditoria["universo_identico"] is True
    assert auditoria["denominador_identico"] is True
