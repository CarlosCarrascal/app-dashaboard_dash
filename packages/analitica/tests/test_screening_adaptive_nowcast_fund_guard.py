from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analitica.servicios import nowcast

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "screening_adaptive_nowcast_fund_guard.py"
SPEC = importlib.util.spec_from_file_location("screening_adaptive_nowcast_fund_guard_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULO = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULO
SPEC.loader.exec_module(MODULO)


def _cfg(
    *,
    min_semanas: int = 2,
    shrink: float = 2.0,
    ganancia: float = 0.0,
    retencion: float = 1.0,
    cambio: float = 0.60,
) -> object:
    return MODULO.ConfiguracionFundGuard(
        min_semanas_fundo=min_semanas,
        shrink_evidencia=shrink,
        ganancia_minima_pp=ganancia,
        retencion_maxima=retencion,
        cambio_maximo_relativo=cambio,
    )


def _base(*, semanas: int = 8) -> pd.DataFrame:
    fechas = pd.date_range("2026-05-04", periods=semanas, freq="7D")
    filas = []
    for numero, fecha in enumerate(fechas, start=19):
        for fundo, factor in (("Arena", 1.0), ("Quri", 0.7)):
            real = (100_000 + 10_000 * (numero - 19)) * factor
            macro = real * (0.90 if fundo == "Arena" else 0.95)
            candidato = real if fundo == "Arena" else real * 0.65
            filas.append(
                {
                    "campania": "C2026",
                    "fecha_emision": fecha - pd.Timedelta(days=7),
                    "fecha_objetivo": fecha,
                    "semana_emision": numero - 1,
                    "semana_objetivo": numero,
                    "fundo_operativo": fundo,
                    "real_kg": real,
                    "montue_kg": real * 0.41,
                    "macro_kg": macro,
                    "pace_kg": real,
                    "candidate_kg": candidato,
                    "r09_presemana_kg": real * 1.03,
                    "r09_misma_semana_kg": real * 1.01,
                }
            )
    return pd.DataFrame(filas)


def test_fachada_conserva_aliases_y_delega_en_el_servicio() -> None:
    assert MODULO.ejecutar is nowcast.ejecutar_fund_guard
    assert MODULO.BASE_CONGELADA is nowcast.BASE_CONGELADA
    assert MODULO.ConfiguracionFundGuard is nowcast.ConfiguracionFundGuard
    assert MODULO.ConfiguracionReconciliacionFundos is nowcast.ConfiguracionReconciliacionFundos
    for nombre in (
        "_evidencia_fundo",
        "_aplicar_guardia_online",
        "_reconciliar_total_empresa_online",
        "_seleccionar_guardia",
        "_seleccionar_reconciliacion",
        "_evaluar",
    ):
        assert getattr(MODULO, nombre) is getattr(nowcast, nombre)


def test_servicio_y_fachada_comparten_la_misma_frontera_temporal_y_r09() -> None:
    fuente = inspect.getsource(nowcast._aplicar_guardia_online).casefold()
    fuente += inspect.getsource(nowcast._reconciliar_total_empresa_online).casefold()
    assert "r09" not in fuente
    tabla = _base()
    antes = MODULO._aplicar_guardia_online(tabla, _cfg())
    tabla.loc[tabla.fecha_objetivo.eq(tabla.fecha_objetivo.max()), "real_kg"] *= 100.0
    despues = nowcast._aplicar_guardia_online(tabla, _cfg())
    columnas = ["candidate_kg", "guard_retencion", "guard_n_semanas", "guard_ruta"]
    pd.testing.assert_frame_equal(
        antes.loc[antes.fecha_objetivo.eq(antes.fecha_objetivo.max()), columnas]
        .reset_index(drop=True),
        despues.loc[despues.fecha_objetivo.eq(despues.fecha_objetivo.max()), columnas]
        .reset_index(drop=True),
    )


def test_real_actual_no_altera_la_guardia_de_su_misma_semana() -> None:
    original = MODULO._aplicar_guardia_online(_base(), _cfg())
    mutado = _base()
    fecha = mutado.fecha_objetivo.max()
    mutado.loc[mutado.fecha_objetivo.eq(fecha), "real_kg"] *= 100.0
    repetido = MODULO._aplicar_guardia_online(mutado, _cfg())

    columnas = [
        "fundo_operativo",
        "candidate_kg",
        "guard_retencion",
        "guard_n_semanas",
        "guard_ruta",
    ]
    esperado = original.loc[original.fecha_objetivo.eq(fecha), columnas].reset_index(drop=True)
    obtenido = repetido.loc[repetido.fecha_objetivo.eq(fecha), columnas].reset_index(drop=True)
    pd.testing.assert_frame_equal(esperado, obtenido)


def test_mutar_futuro_no_cambia_guardias_anteriores() -> None:
    original = MODULO._aplicar_guardia_online(_base(), _cfg())
    mutado = _base()
    corte = sorted(mutado.fecha_objetivo.unique())[4]
    mutado.loc[mutado.fecha_objetivo.gt(corte), "real_kg"] *= 50.0
    repetido = MODULO._aplicar_guardia_online(mutado, _cfg())

    columnas = ["fecha_objetivo", "fundo_operativo", "candidate_kg", "guard_ruta"]
    esperado = original.loc[original.fecha_objetivo.le(corte), columnas].reset_index(drop=True)
    obtenido = repetido.loc[repetido.fecha_objetivo.le(corte), columnas].reset_index(drop=True)
    pd.testing.assert_frame_equal(esperado, obtenido)


def test_historia_insuficiente_reproduce_macro_exactamente() -> None:
    protegido = MODULO._aplicar_guardia_online(_base(semanas=2), _cfg(min_semanas=3))

    np.testing.assert_allclose(protegido.candidate_kg, protegido.macro_kg)
    assert protegido.guard_ruta.eq("macro_fallback").all()


def test_fundo_con_evidencia_adversa_vuelve_a_macro() -> None:
    protegido = MODULO._aplicar_guardia_online(_base(), _cfg())
    quri = protegido.loc[protegido.fundo_operativo.eq("Quri") & protegido.guard_n_semanas.ge(2)]

    assert not quri.empty
    np.testing.assert_allclose(quri.candidate_kg, quri.macro_kg)
    assert quri.guard_ruta.eq("macro_fallback").all()


def test_fundo_con_evidencia_favorable_aplica_shrinkage() -> None:
    protegido = MODULO._aplicar_guardia_online(_base(), _cfg(shrink=2.0))
    arena = protegido.loc[
        protegido.fundo_operativo.eq("Arena") & protegido.guard_ruta.eq("adaptive_shrunk")
    ]

    assert not arena.empty
    assert arena.guard_retencion.between(0.0, 1.0, inclusive="neither").all()
    assert np.all(arena.candidate_kg > arena.macro_kg)
    assert np.all(arena.candidate_kg < arena.candidate_base_kg)


def test_selector_respeta_limite_de_diez_pp_por_fundo() -> None:
    ganador, ranking = MODULO._seleccionar_guardia(_base())
    protegido = MODULO._aplicar_guardia_online(_base(), ganador)

    assert ranking.iloc[0].configuracion_id == ganador.id
    assert ranking.iloc[0].max_deterioro_fundo_pp <= 10.0 + 1e-12
    assert MODULO._max_deterioro(protegido) <= 10.0 + 1e-12


def test_r09_no_interviene_en_evidencia_ni_en_prediccion_guardada() -> None:
    fuente = (
        inspect.getsource(MODULO._evidencia_fundo)
        + inspect.getsource(MODULO._aplicar_guardia_online)
    ).casefold()

    assert "r09" not in fuente


def test_base_global_permanece_congelada_desde_la_primera_ronda() -> None:
    assert MODULO.BASE_CONGELADA.id == "s4-sf4-m4-r1.0-p0.50-c0.20-tc0.25"


def test_control_macro_es_elegible_aun_si_no_hay_senal() -> None:
    sin_senal = _base()
    sin_senal["candidate_kg"] = sin_senal.real_kg * 0.10
    cfg = _cfg(min_semanas=999, retencion=0.0, cambio=0.0)
    protegido = MODULO._aplicar_guardia_online(sin_senal, cfg)

    assert MODULO._max_deterioro(protegido) == pytest.approx(0.0)
    np.testing.assert_allclose(protegido.candidate_kg, protegido.macro_kg)


def _cfg_recon(*, peso: float = 0.60, shrink: float = 2.0) -> object:
    return MODULO.ConfiguracionReconciliacionFundos(
        peso_participacion_montue=peso,
        shrink_semanas=shrink,
        retencion_cola=0.50,
    )


def test_reconciliacion_conserva_exactamente_total_empresa() -> None:
    reconciliado = MODULO._reconciliar_total_empresa_online(_base(), _cfg_recon())
    sumas = reconciliado.groupby("fecha_objetivo")[["candidate_kg", "candidate_base_kg"]].sum()

    np.testing.assert_allclose(sumas.candidate_kg, sumas.candidate_base_kg, rtol=0.0, atol=1e-9)


def test_reconciliacion_no_usa_real_actual_para_repartir() -> None:
    original = MODULO._reconciliar_total_empresa_online(_base(), _cfg_recon())
    mutado = _base()
    fecha = mutado.fecha_objetivo.max()
    mutado.loc[mutado.fecha_objetivo.eq(fecha), "real_kg"] *= 100.0
    repetido = MODULO._reconciliar_total_empresa_online(mutado, _cfg_recon())

    columnas = ["fundo_operativo", "candidate_kg", "recon_alpha"]
    esperado = original.loc[original.fecha_objetivo.eq(fecha), columnas].reset_index(drop=True)
    obtenido = repetido.loc[repetido.fecha_objetivo.eq(fecha), columnas].reset_index(drop=True)
    pd.testing.assert_frame_equal(esperado, obtenido)


def test_reconciliacion_mueve_shares_hacia_montue_sin_cambiar_total() -> None:
    tabla = _base()
    fecha = tabla.fecha_objetivo.max()
    tabla.loc[
        tabla.fecha_objetivo.eq(fecha) & tabla.fundo_operativo.eq("Arena"),
        "montue_kg",
    ] *= 4.0
    macro = MODULO._reconciliar_total_empresa_online(tabla, _cfg_recon(peso=0.0, shrink=0.0))
    mixto = MODULO._reconciliar_total_empresa_online(tabla, _cfg_recon(peso=1.0, shrink=0.0))
    arena_macro = macro.loc[
        macro.fecha_objetivo.eq(fecha) & macro.fundo_operativo.eq("Arena"),
        "candidate_kg",
    ].iloc[0]
    arena_mixto = mixto.loc[
        mixto.fecha_objetivo.eq(fecha) & mixto.fundo_operativo.eq("Arena"),
        "candidate_kg",
    ].iloc[0]

    assert arena_mixto > arena_macro
    assert mixto.loc[mixto.fecha_objetivo.eq(fecha), "candidate_kg"].sum() == pytest.approx(
        macro.loc[macro.fecha_objetivo.eq(fecha), "candidate_kg"].sum()
    )


def test_selector_reconciliado_cumple_guardia_y_no_usa_r09() -> None:
    ganador, ranking = MODULO._seleccionar_reconciliacion(_base())

    assert ranking.iloc[0].configuracion_id == ganador.id
    assert ranking.iloc[0].max_deterioro_fundo_pp <= 10.0 + 1e-12
    assert ranking.iloc[0].reconciliacion_max_error_kg <= 1e-6
    fuente = inspect.getsource(MODULO._reconciliar_total_empresa_online).casefold()
    assert "r09" not in fuente
