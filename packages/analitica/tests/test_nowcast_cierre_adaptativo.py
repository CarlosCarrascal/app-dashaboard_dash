from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analitica.proyeccion import nowcast_cierre_adaptativo as nowcast

ARTEFACTO_DORADO = (
    Path(__file__).resolve().parent / "fixtures" / "nowcast_cierre_adaptativo_c2026.json"
)


def _panel_sintetico(*, semanas: int = 10) -> pd.DataFrame:
    fechas = pd.date_range("2026-05-04", periods=semanas, freq="7D")
    filas: list[dict[str, object]] = []
    fondos = (("Arena", 1.00), ("Ayllu", 0.65), ("Kawsay", 1.25), ("Quri", 0.85))
    for numero, fecha in enumerate(fechas):
        fase = 1.0 + 0.09 * numero
        for posicion, (fundo, factor) in enumerate(fondos):
            real = (95_000.0 * fase + 2_500.0 * posicion) * factor
            macro = real * (0.82 + 0.02 * posicion)
            share_montue = 0.39 + 0.01 * posicion
            filas.append(
                {
                    "campania": "C2026",
                    "fecha_objetivo": fecha,
                    "fecha_corte_asof": fecha + pd.Timedelta(days=1),
                    "fundo_operativo": fundo,
                    "macro_kg": macro,
                    "montue_kg": real * share_montue,
                    "dias_montue_observados": 2,
                    "real_kg": real,
                }
            )
    return pd.DataFrame(filas)


def _panel_artefacto() -> tuple[pd.DataFrame, pd.DataFrame]:
    documento = json.loads(ARTEFACTO_DORADO.read_text(encoding="utf-8"))
    detalle = pd.DataFrame(documento["detalle"]["C2026"])
    panel = detalle[
        [
            "campania",
            "fecha_objetivo",
            "fundo_operativo",
            "macro_kg",
            "montue_kg",
            "real_kg",
        ]
    ].copy()
    panel["fecha_objetivo"] = pd.to_datetime(panel.fecha_objetivo)
    panel["fecha_corte_asof"] = panel.fecha_objetivo + pd.Timedelta(days=1)
    panel["dias_montue_observados"] = 2
    return panel, detalle


def _wape(real: pd.Series, prediccion: pd.Series) -> float:
    return float((prediccion - real).abs().sum() / real.abs().sum())


def test_configuracion_de_produccion_esta_congelada() -> None:
    cfg = nowcast.CONFIGURACION_CONGELADA

    assert cfg.lookback_share == 4
    assert cfg.lookback_modelo == 4
    assert cfg.peso_participacion_montue == pytest.approx(0.40)
    assert cfg.retencion_reconciliacion_cola == pytest.approx(0.25)
    assert cfg.dias_montue_requeridos == 2


def test_real_actual_no_altera_su_propio_nowcast() -> None:
    panel = _panel_sintetico()
    fecha = panel.fecha_objetivo.max()
    original = nowcast.calcular_nowcast_cierre_adaptativo(panel).predicciones
    mutado = panel.copy()
    mutado.loc[mutado.fecha_objetivo.eq(fecha), "real_kg"] *= 100.0
    repetido = nowcast.calcular_nowcast_cierre_adaptativo(mutado).predicciones

    columnas = [
        "fundo_operativo",
        "candidate_kg",
        "candidate_base_kg",
        "coef_macro",
        "coef_pace",
        "recon_alpha",
    ]
    esperado = original.loc[original.fecha_objetivo.eq(fecha), columnas].reset_index(drop=True)
    obtenido = repetido.loc[repetido.fecha_objetivo.eq(fecha), columnas].reset_index(drop=True)
    pd.testing.assert_frame_equal(esperado, obtenido)


def test_mutar_futuro_no_altera_predicciones_pasadas() -> None:
    panel = _panel_sintetico()
    corte = sorted(panel.fecha_objetivo.unique())[5]
    original = nowcast.calcular_nowcast_cierre_adaptativo(panel).predicciones
    mutado = panel.copy()
    futuro = mutado.fecha_objetivo.gt(corte)
    mutado.loc[futuro, "real_kg"] *= 75.0
    mutado.loc[futuro, "macro_kg"] *= 12.0
    mutado.loc[futuro, "montue_kg"] *= 9.0
    repetido = nowcast.calcular_nowcast_cierre_adaptativo(mutado).predicciones

    columnas = [
        "fecha_objetivo",
        "fundo_operativo",
        "candidate_kg",
        "candidate_base_kg",
        "estado_nowcast",
    ]
    esperado = original.loc[original.fecha_objetivo.le(corte), columnas].reset_index(drop=True)
    obtenido = repetido.loc[repetido.fecha_objetivo.le(corte), columnas].reset_index(drop=True)
    pd.testing.assert_frame_equal(esperado, obtenido)


def test_fuente_publicada_no_contiene_referencia_como_predictor() -> None:
    fuente = inspect.getsource(nowcast).casefold()

    assert "r09" not in fuente


def test_reconciliacion_fundos_conserva_total_empresa_exactamente() -> None:
    resultado = nowcast.calcular_nowcast_cierre_adaptativo(_panel_sintetico())
    sumas = resultado.predicciones.groupby(
        ["campania", "fecha_objetivo"], as_index=False
    ).candidate_kg.sum()
    empresa = resultado.empresa[["campania", "fecha_objetivo", "total_adaptativo_kg"]]
    comparacion = empresa.merge(sumas, on=["campania", "fecha_objetivo"], validate="one_to_one")

    np.testing.assert_allclose(
        comparacion.candidate_kg,
        comparacion.total_adaptativo_kg,
        rtol=0.0,
        atol=1e-9,
    )
    assert resultado.empresa.error_reconciliacion_kg.max() <= 1e-9


def test_semana_sin_lunes_martes_completos_no_se_predice() -> None:
    panel = _panel_sintetico()
    fecha = panel.fecha_objetivo.max()
    fila = panel.fecha_objetivo.eq(fecha) & panel.fundo_operativo.eq("Ayllu")
    panel.loc[fila, "dias_montue_observados"] = 1

    resultado = nowcast.calcular_nowcast_cierre_adaptativo(panel)
    semana = resultado.predicciones.loc[resultado.predicciones.fecha_objetivo.eq(fecha)]
    empresa = resultado.empresa.loc[resultado.empresa.fecha_objetivo.eq(fecha)].iloc[0]

    assert semana.candidate_kg.isna().all()
    assert semana.estado_nowcast.eq("datos_montue_insuficientes").all()
    assert empresa.estado_nowcast == "datos_montue_insuficientes"
    assert pd.isna(empresa.candidate_kg)


def test_contrato_rechaza_datos_despues_del_martes() -> None:
    panel = _panel_sintetico(semanas=2)
    panel.loc[0, "fecha_corte_asof"] = panel.loc[0, "fecha_objetivo"] + pd.Timedelta(days=2)

    with pytest.raises(nowcast.ContratoNowcastError, match="lunes y martes"):
        nowcast.calcular_nowcast_cierre_adaptativo(panel)


def test_reproduce_exactamente_artefacto_holdout_s31_s33() -> None:
    panel, detalle = _panel_artefacto()
    resultado = nowcast.calcular_nowcast_cierre_adaptativo(panel)
    esperado = detalle.loc[detalle.semana_objetivo.between(31, 33)].copy()
    esperado["fecha_objetivo"] = pd.to_datetime(esperado.fecha_objetivo)
    obtenido = resultado.predicciones.merge(
        esperado[["campania", "fecha_objetivo", "fundo_operativo", "candidate_kg"]].rename(
            columns={"candidate_kg": "candidate_kg_dorado"}
        ),
        on=["campania", "fecha_objetivo", "fundo_operativo"],
        how="inner",
        validate="one_to_one",
    )

    assert len(obtenido) == len(esperado)
    np.testing.assert_allclose(
        obtenido.candidate_kg,
        obtenido.candidate_kg_dorado,
        rtol=0.0,
        atol=1e-8,
    )
    fechas_holdout = sorted(esperado.fecha_objetivo.unique())
    empresa_holdout = resultado.empresa.loc[resultado.empresa.fecha_objetivo.isin(fechas_holdout)]
    assert _wape(empresa_holdout.real_kg, empresa_holdout.candidate_kg) == pytest.approx(
        0.09023880699452279,
        abs=1e-12,
    )
    assert resultado.configuracion_id.startswith("NowcastCierreAdaptativo_v1__")
