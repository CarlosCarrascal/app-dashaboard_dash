from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pandas as pd
import pytest

from analitica.aplicacion.servicios import active_lot_scheduler as servicio
from analitica.interfaces.scripts import screening_active_lot_scheduler as modulo

SCRIPT = Path(__file__).parents[1] / "interfaces" / "scripts" / "screening_active_lot_scheduler.py"


def test_fachada_reexporta_aliases_historicos_por_identidad_y_firma():
    nombres = (
        "configuraciones",
        "_normalizar_fechas",
        "leer_fuentes",
        "_intervalo_mediano",
        "_distancia_periodica",
        "derivar_contexto_asof",
        "_actividad",
        "_metricas",
        "_escala_online",
        "predecir_scheduler",
        "construir_verdad",
        "_cobertura_y_ceros",
        "bootstrap_pareado",
        "resumir",
        "anexar_r09",
        "resumir_con_r09",
        "seleccionar_configuracion",
        "_keyset_sha256",
        "ejecutar",
        "_json_default",
        "escribir_resultado",
        "leer_r09_access",
        "normalizar_fundo",
    )
    for nombre in nombres:
        fachada = getattr(modulo, nombre)
        implementacion = getattr(servicio, nombre)
        assert fachada is implementacion
        if callable(fachada):
            assert inspect.signature(fachada) == inspect.signature(implementacion)

    for nombre in (
        "RUN_ID",
        "CAMPANIAS",
        "FUNDOS",
        "SEMANA_DESARROLLO_FINAL",
        "SEMANAS_HOLDOUT",
        "CIERRE_C2026",
        "RUTA_SALIDA",
        "R09_ACCESS_DEFAULT",
        "ConfiguracionScheduler",
    ):
        assert getattr(modulo, nombre) is getattr(servicio, nombre)


def test_fachada_solo_conserva_el_adaptador_cli():
    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    definiciones = [
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
    ]


def test_fachada_y_servicio_conservan_paridad_de_prediccion():
    macro = _macro().iloc[:2].copy()
    h01 = _h01()
    contexto_fachada = modulo.derivar_contexto_asof(macro, h01)
    contexto_servicio = servicio.derivar_contexto_asof(macro, h01)
    pd.testing.assert_frame_equal(contexto_fachada, contexto_servicio)

    verdad = modulo.construir_verdad(h01)
    config = modulo.ConfiguracionScheduler(5, 0.4, 1.0, 0.08, 0.0, 4)
    pred_fachada = modulo.predecir_scheduler(contexto_fachada, verdad, config)
    pred_servicio = servicio.predecir_scheduler(contexto_servicio, verdad, config)
    pd.testing.assert_frame_equal(pred_fachada, pred_servicio)


def _macro() -> pd.DataFrame:
    filas = []
    for semana in range(13, 34):
        objetivo = pd.Timestamp.fromisocalendar(2026, semana, 1)
        emision = objetivo - pd.Timedelta(days=7)
        for lote_id in (1, 2):
            filas.append(
                {
                    "campania": "C2026",
                    "fecha_emision": emision,
                    "fecha_objetivo": objetivo,
                    "lote_id": lote_id,
                    "fundo": "Arena",
                    "modulo": "M01",
                    "macro_kg": 100.0 if lote_id == 1 else 0.0,
                }
            )
    return pd.DataFrame(filas)


def _h01() -> pd.DataFrame:
    filas = []
    for lote_id, offset in ((1, 0), (2, 7)):
        for fecha in pd.date_range("2026-01-05", "2026-08-30", freq="14D"):
            filas.append(
                {
                    "campania": "C2026",
                    "lote_id": lote_id,
                    "fecha": fecha + pd.Timedelta(days=offset),
                    "turno": f"T0{lote_id}",
                    "kg": 60.0 if lote_id == 1 else 40.0,
                }
            )
    return pd.DataFrame(filas)


def test_contexto_ignora_h01_en_y_despues_de_la_emision():
    macro = _macro().iloc[:2].copy()
    original = modulo.derivar_contexto_asof(macro, _h01())
    futuro = pd.DataFrame(
        [
            {
                "campania": "C2026",
                "lote_id": 1,
                "fecha": pd.Timestamp("2026-12-31"),
                "turno": "FUTURO",
                "kg": 9e9,
            }
        ]
    )
    mutado = modulo.derivar_contexto_asof(macro, pd.concat([_h01(), futuro], ignore_index=True))
    columnas = [
        "turno_asof",
        "ultima_cosecha_asof",
        "dias_reingreso_asof",
        "distancia_lote_dias",
        "distancia_turno_dias",
    ]
    pd.testing.assert_frame_equal(original[columnas], mutado[columnas])


def test_scheduler_es_continuo_y_no_genera_falso_cero_si_hay_volumen_fundo():
    macro = _macro().iloc[:2].copy()
    contexto = modulo.derivar_contexto_asof(macro, _h01())
    verdad = pd.DataFrame(
        [
            {
                "campania": "C2026",
                "fecha_objetivo": macro.fecha_objetivo.iloc[0],
                "lote_id": 1,
                "real_kg": 80.0,
            },
            {
                "campania": "C2026",
                "fecha_objetivo": macro.fecha_objetivo.iloc[0],
                "lote_id": 2,
                "real_kg": 20.0,
            },
        ]
    )
    config = modulo.ConfiguracionScheduler(5, 0.4, 1.0, 0.08, 0.0, 4)
    pred = modulo.predecir_scheduler(contexto, verdad, config)
    lote_dos = pred.loc[pred.lote_id.eq(2)].iloc[0]
    assert lote_dos.macro_kg == 0.0
    assert lote_dos.candidate_kg > 0.0
    assert not bool(lote_dos.falso_cero_candidate)
    assert pred.candidate_kg.sum() == pytest.approx(pred.macro_kg.sum())


def test_evaluacion_excluye_semanas_sin_emision_pero_penaliza_lote_ausente():
    macro = _macro().iloc[:2].copy()
    contexto = modulo.derivar_contexto_asof(macro, _h01())
    objetivo = macro.fecha_objetivo.iloc[0]
    verdad = pd.DataFrame(
        [
            {"campania": "C2026", "fecha_objetivo": objetivo, "lote_id": 99, "real_kg": 25.0},
            {
                "campania": "C2026",
                "fecha_objetivo": objetivo + pd.Timedelta(days=7),
                "lote_id": 99,
                "real_kg": 999.0,
            },
        ]
    )
    config = modulo.ConfiguracionScheduler(5, 0.25, 1.0, 0.08, 0.0, 4)
    pred = modulo.predecir_scheduler(contexto, verdad, config)
    assert set(pred.fecha_objetivo) == {objetivo}
    ausente = pred.loc[pred.lote_id.eq(99)].iloc[0]
    assert ausente.real_kg == 25.0
    assert not bool(ausente.emitio_candidate)
    cobertura = modulo._cobertura_y_ceros(pred, "candidate_kg")
    assert cobertura["cobertura_lotes_con_real"] == 0.0
    assert cobertura["falsos_ceros_volumen_kg"] == 25.0


def test_seleccion_solo_usa_desarrollo_hasta_s30():
    macro = _macro()
    contexto = modulo.derivar_contexto_asof(macro, _h01())
    verdad = modulo.construir_verdad(_h01())
    ganador_a, _, _ = modulo.seleccionar_configuracion(contexto, verdad)
    mutada = verdad.copy()
    semanas = mutada.fecha_objetivo.dt.isocalendar().week.astype(int)
    mutada.loc[semanas.isin([31, 32, 33]), "real_kg"] *= 1000
    ganador_b, _, _ = modulo.seleccionar_configuracion(contexto, mutada)
    assert ganador_a.id == ganador_b.id


def test_bootstrap_reporta_signo_de_diferencia():
    tabla = pd.DataFrame(
        {
            "campania": ["C2026"] * 4,
            "fecha_objetivo": pd.date_range("2026-01-05", periods=4, freq="7D"),
            "real_kg": [100.0] * 4,
            "candidate_kg": [100.0] * 4,
            "macro_kg": [130.0] * 4,
        }
    )
    resultado = modulo.bootstrap_pareado(tabla, "candidate_kg", "macro_kg", repeticiones=300)
    assert resultado is not None
    assert resultado["diferencia_wape_pp"] < 0
    assert resultado["ic95_diferencia_wape_pp"][1] < 0


def test_script_no_persiste_no_publica_y_r09_no_es_predictor():
    fuente = inspect.getsource(modulo)
    assert "INSERT INTO" not in fuente.upper()
    assert "UPDATE ANALYTICS" not in fuente.upper()
    assert "model_series_release" not in fuente
    assert "R09 se incorpora solamente despues" in modulo.__doc__
    assert "r09_kg" not in inspect.getsource(modulo.predecir_scheduler)
