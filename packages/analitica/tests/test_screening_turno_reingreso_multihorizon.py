from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pandas as pd
import pytest

from analitica.aplicacion.procesos.candidatos import ConfiguracionTurnoTemporal
from analitica.aplicacion.servicios import turno_reingreso as SERVICIO
from analitica.interfaces.scripts.screening_turno_reingreso_multihorizon import (
    aplicar_configuracion,
    derivar_contexto_asof,
    enriquecer_macro,
    evaluar_panel,
    preparar_macro,
)

SCRIPT = (
    Path(__file__).parents[1]
    / "interfaces"
    / "scripts"
    / "screening_turno_reingreso_multihorizon.py"
)
FUNDOS = ["Aqu Anqa 1", "Aqu Anqa 4", "Aqu Anqa 3", "Aqu Anqa 2"]


def test_fachada_reexporta_aliases_y_firmas_del_servicio() -> None:
    from analitica.interfaces.scripts import screening_turno_reingreso_multihorizon as fachada

    nombres = (
        "ConfiguracionTurnoTemporal",
        "aplicar_turno_reingreso_candidate",
        "normalizar_forecast_candidate",
        "preparar_macro",
        "preparar_r09",
        "derivar_contexto_asof",
        "enriquecer_macro",
        "aplicar_configuracion",
        "auditar_paridad_funcion_pura",
        "seleccionar_configuracion",
        "comparar_r09_despues",
        "evaluar_panel",
        "postgres_dsn",
    )
    for nombre in nombres:
        implementacion = getattr(SERVICIO, nombre)
        alias = getattr(fachada, nombre)
        assert alias is implementacion
        assert inspect.signature(alias) == inspect.signature(implementacion)

    assert fachada.CLAVE is SERVICIO.CLAVE
    assert fachada.GRUPO_CURVA is SERVICIO.GRUPO_CURVA
    assert fachada.CONTRACT_ID == SERVICIO.CONTRACT_ID


def test_fachada_es_delgada_y_conserva_parser_y_ruta_historicos() -> None:
    from analitica.interfaces.scripts import screening_turno_reingreso_multihorizon as fachada

    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    definiciones = {
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert definiciones == {"construir_parser", "main"}
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
        for nodo in ast.walk(arbol)
    )

    args = fachada.construir_parser().parse_args([])
    assert args.salida == Path(".tmp/screening_turno_reingreso_multihorizon.json")
    assert tuple(inspect.signature(fachada.main).parameters) == ()


def _fuentes_sinteticas() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    macro: list[dict] = []
    r09: list[dict] = []
    for semana_emision in range(12, 33):
        emision = pd.Timestamp.fromisocalendar(2026, semana_emision, 1)
        for lote_id, fundo in enumerate(FUNDOS, start=1):
            for horizonte in range(1, 7):
                objetivo = emision + pd.Timedelta(weeks=horizonte)
                semana = int(objetivo.isocalendar().week)
                real = float(max(0, semana - 12) * 20 + lote_id * 5)
                pesos = (10.0, 20.0, 35.0, 20.0, 10.0, 5.0)
                base = {
                    "campania": "C2026",
                    "fecha_emision": emision,
                    "fecha_objetivo": objetivo,
                    "horizonte_semanas": horizonte,
                    "lote_id": lote_id,
                    "fundo": fundo,
                    "modulo": f"M{lote_id:02d}",
                    "real_kg": real,
                    "componentes": {},
                }
                macro.append({**base, "p50_kg": pesos[horizonte - 1] * lote_id})
                if lote_id <= 2 and horizonte <= 5:
                    r09.append({**base, "p50_kg": real * 1.08})

    h01: list[dict] = []
    for lote_id in range(1, 5):
        for fecha in pd.date_range("2026-01-05", "2026-08-10", freq="14D"):
            h01.append(
                {
                    "campania": "C2026",
                    "lote_id": lote_id,
                    "fecha": fecha,
                    "turno": f"T{lote_id:02d}",
                    "kg": float(10 * lote_id),
                }
            )
    return pd.DataFrame(macro), pd.DataFrame(r09), pd.DataFrame(h01)


def test_run73_exige_h1_h6_contiguos_de_la_misma_emision_lote():
    macro, _, _ = _fuentes_sinteticas()
    valido = preparar_macro(macro)
    tamanos = valido.groupby(["fecha_emision", "lote_id"]).size()
    assert tamanos.min() == tamanos.max() == 6

    incompleto = macro.drop(
        macro[
            macro.fecha_emision.eq(macro.fecha_emision.min())
            & macro.lote_id.eq(1)
            & macro.horizonte_semanas.eq(6)
        ].index
    )
    with pytest.raises(ValueError, match="h1-h6 contiguos"):
        preparar_macro(incompleto)


def test_candidate_redistribuye_pero_conserva_total_h1_h6():
    macro, _, h01 = _fuentes_sinteticas()
    base = preparar_macro(macro)
    contexto = derivar_contexto_asof(base, h01)
    curva = enriquecer_macro(base, contexto)
    config = ConfiguracionTurnoTemporal(
        peso_calendario=0.8,
        dispersion_semanas=0.6,
        desplazamiento_max_semanas=0,
    )
    candidato = aplicar_configuracion(curva, config)

    grano = ["campania", "fecha_emision", "lote_id"]
    esperado = curva.groupby(grano).p50_kg.sum().sort_index()
    obtenido = candidato.groupby(grano).p50_kg.sum().sort_index()
    pd.testing.assert_series_equal(esperado, obtenido)
    assert (candidato.p50_kg - curva.p50_kg).abs().max() > 0


def test_contexto_turno_reingreso_no_cambia_al_mutar_h01_futuro():
    macro, _, h01 = _fuentes_sinteticas()
    base = preparar_macro(macro)
    original = derivar_contexto_asof(base, h01)
    futuro = pd.DataFrame(
        [
            {
                "campania": "C2026",
                "lote_id": 1,
                "fecha": pd.Timestamp("2026-12-31"),
                "turno": "FUTURO",
                "kg": 9_999_999.0,
            }
        ]
    )
    mutado = derivar_contexto_asof(base, pd.concat([h01, futuro], ignore_index=True))

    columnas = [
        "turno",
        "dias_reingreso",
        "nivel_reingreso",
        "n_intervalos_reingreso_asof",
        "fecha_ultima_cosecha_asof",
    ]
    pd.testing.assert_frame_equal(original[columnas], mutado[columnas])
    assert original.dias_reingreso.dropna().eq(14.0).all()


def test_seleccion_s13_s30_no_lee_el_holdout_s31_s33():
    macro, r09, h01 = _fuentes_sinteticas()
    original = evaluar_panel(macro, r09, h01)

    macro_mutado = macro.copy()
    r09_mutado = r09.copy()
    for tabla in (macro_mutado, r09_mutado):
        semana = pd.to_datetime(tabla.fecha_objetivo).dt.isocalendar().week.astype(int)
        tabla.loc[semana.between(31, 33), "real_kg"] *= 1000
    mutado = evaluar_panel(macro_mutado, r09_mutado, h01)

    assert original["seleccion"]["configuracion"] == mutado["seleccion"]["configuracion"]
    scores_original = [fila["score"] for fila in original["seleccion"]["screening"]]
    scores_mutado = [fila["score"] for fila in mutado["seleccion"]["screening"]]
    assert scores_original == pytest.approx(scores_mutado)


def test_r09_se_compara_despues_y_solo_sobre_cobertura_pareada():
    macro, r09, h01 = _fuentes_sinteticas()
    resultado = evaluar_panel(macro, r09, h01)
    comparacion = resultado["comparacion_r09_posterior"]

    assert 0 < comparacion["cobertura"]["h1_h6"]["cobertura_filas"] < 1
    holdout = comparacion["holdout_s31_s33"]
    assert holdout["candidate_pareado"]["h1"]["empresa_semana"]["n"] == 3
    assert holdout["r09_condicionado"]["h1"]["empresa_semana"]["n"] == 3
    assert resultado["persistencia_postgresql"] is False
    assert resultado["publicado"] is False
