from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).parents[1] / "interfaces" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "screening_adaptive_nowcast.py"
SERVICE = Path(__file__).parents[1] / "aplicacion" / "servicios" / "nowcast.py"
SPEC = importlib.util.spec_from_file_location("screening_adaptive_nowcast_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULO = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULO
SPEC.loader.exec_module(MODULO)


def _cfg(*, retencion: float = 0.25) -> object:
    return MODULO.ConfiguracionAdaptativa(
        lookback_share=4,
        shrink_fundo=4.0,
        lookback_modelo=4,
        regularizacion=4.0,
        peso_ritmo_prior=0.5,
        umbral_cola=0.35,
        retencion_correccion_cola=retencion,
    )


def _contrato() -> pd.DataFrame:
    fechas = pd.date_range("2026-05-04", periods=6, freq="7D")
    filas = []
    for semana, fecha in enumerate(fechas, start=19):
        for fondo, factor in (("Arena", 1.0), ("Quri", 0.7)):
            real = (100_000 + 15_000 * (semana - 19)) * factor
            filas.append(
                {
                    "campania": "C2026",
                    "fecha_emision": fecha - pd.Timedelta(days=7),
                    "fecha_objetivo": fecha,
                    "semana_emision": semana - 1,
                    "semana_objetivo": semana,
                    "fundo_operativo": fondo,
                    "real_kg": real,
                    "montue_kg": real * 0.41,
                    "macro_kg": real * 0.90,
                    "r09_presemana_kg": real * 1.03,
                    "r09_misma_semana_kg": real * 1.01,
                }
            )
    return pd.DataFrame(filas)


def test_real_de_la_semana_actual_no_altera_su_propia_prediccion() -> None:
    original = MODULO._predecir_online(_contrato(), _cfg())
    mutado = _contrato()
    fecha = mutado.fecha_objetivo.max()
    mutado.loc[mutado.fecha_objetivo.eq(fecha), "real_kg"] *= 100.0
    repetido = MODULO._predecir_online(mutado, _cfg())

    columnas = ["fundo_operativo", "candidate_kg", "coef_macro", "coef_pace"]
    esperado = original.loc[original.fecha_objetivo.eq(fecha), columnas].reset_index(drop=True)
    obtenido = repetido.loc[repetido.fecha_objetivo.eq(fecha), columnas].reset_index(drop=True)
    pd.testing.assert_frame_equal(esperado, obtenido)


def test_mutar_el_futuro_no_cambia_predicciones_anteriores() -> None:
    original = MODULO._predecir_online(_contrato(), _cfg())
    mutado = _contrato()
    corte = sorted(mutado.fecha_objetivo.unique())[3]
    mutado.loc[mutado.fecha_objetivo.gt(corte), ["real_kg", "montue_kg"]] *= 50.0
    repetido = MODULO._predecir_online(mutado, _cfg())

    esperado = original.loc[
        original.fecha_objetivo.le(corte), ["fecha_objetivo", "fundo_operativo", "candidate_kg"]
    ].reset_index(drop=True)
    obtenido = repetido.loc[
        repetido.fecha_objetivo.le(corte), ["fecha_objetivo", "fundo_operativo", "candidate_kg"]
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(esperado, obtenido)


def test_salvaguarda_de_cola_retrae_la_correccion_hacia_macro() -> None:
    tabla = _contrato()
    fecha = tabla.fecha_objetivo.max()
    tabla.loc[tabla.fecha_objetivo.eq(fecha), "macro_kg"] *= 0.10
    tabla.loc[tabla.fecha_objetivo.eq(fecha), "montue_kg"] *= 0.60

    protegido = MODULO._predecir_online(tabla, _cfg(retencion=0.25))
    libre = MODULO._predecir_online(tabla, _cfg(retencion=1.0))
    p = protegido.loc[protegido.fecha_objetivo.eq(fecha)].copy()
    libre_fecha = libre.loc[libre.fecha_objetivo.eq(fecha)].copy()

    assert p.fase_bajo_volumen.all()
    assert np.all(
        np.abs(p.candidate_kg.to_numpy() - p.macro_kg.to_numpy())
        <= np.abs(libre_fecha.candidate_kg.to_numpy() - libre_fecha.macro_kg.to_numpy()) + 1e-9
    )


def test_comparacion_pareada_excluye_solo_la_clave_sin_referencia() -> None:
    tabla = MODULO._predecir_online(_contrato(), _cfg())
    tabla.loc[0, "r09_presemana_kg"] = np.nan
    resultado = MODULO._bootstrap_pareado(tabla, "r09_presemana_kg", repeticiones=200)

    assert resultado is not None
    assert resultado["n_fundo_semana"] == len(tabla) - 1
    assert resultado["n_semanas"] == tabla.fecha_objetivo.nunique()
    assert set(resultado["por_fundo"]) == {"Arena", "Quri"}
    assert len(resultado["bootstrap_diferencia_wape_pp_ic95"]) == 2


def test_r09_no_interviene_en_pace_ni_en_combinacion_adaptativa() -> None:
    fuente = SERVICE.read_text(encoding="utf-8")
    pace = fuente.split("def _estimar_pace_online", 1)[1].split("def _ajustar_coeficientes", 1)[0]
    ajuste = fuente.split("def _ajustar_coeficientes", 1)[1].split("def _predecir_online", 1)[0]
    prediccion = fuente.split("def _predecir_online", 1)[1].split("def _bootstrap_pareado", 1)[0]

    assert "r09" not in (pace + ajuste + prediccion).casefold()


def test_configuracion_se_selecciona_solo_con_el_dataframe_recibido() -> None:
    desarrollo = _contrato().loc[lambda x: x.semana_objetivo.le(22)].copy()
    ganador, ranking = MODULO._seleccionar_configuracion(desarrollo)

    assert ganador.id == str(ranking.iloc[0].configuracion_id)
    assert ranking.n.min() == desarrollo.fecha_objetivo.nunique()
    assert ranking.wape.notna().all()


@pytest.mark.parametrize(
    ("origen", "esperado"),
    [
        ("Aqu Anqa - Arena Azul", "Arena"),
        ("Aqu Anqa II - Ayllu Allpa", "Ayllu"),
        ("Aqu Anqa II - Kawsay Allpa", "Kawsay"),
        ("Aqu Anqa II - Quri Allpa", "Quri"),
    ],
)
def test_normaliza_nombres_historicos_de_fundo_r09(origen: str, esperado: str) -> None:
    assert MODULO._normalizar_fundo_r09(origen) == esperado


def test_share_reporta_empresa_y_fundo_sin_confundir_granos() -> None:
    diagnostico = MODULO._diagnostico_shares(_contrato())

    assert diagnostico["mediana_empresa_semana"] == pytest.approx(0.41)
    assert diagnostico["mediana_fundo_semana"] == pytest.approx(0.41)
    assert diagnostico["n_empresa_semana"] == 6
    assert diagnostico["n_fundo_semana"] == 12
