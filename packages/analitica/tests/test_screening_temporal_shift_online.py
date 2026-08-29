from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analitica.scripts import screening_temporal_shift_online as facade
from analitica.servicios import temporal_shift as service

SCRIPT = Path(facade.__file__)


def test_fachada_conserva_aliases_identidad_y_firmas() -> None:
    nombres = (
        "Configuracion",
        "_metricas",
        "_keyset_sha256",
        "_cargar_contrato",
        "_ponderaciones",
        "_elegir",
        "_predecir_online",
        "ejecutar",
    )
    for nombre in nombres:
        alias = getattr(facade, nombre)
        implementacion = getattr(service, nombre)
        assert alias is implementacion
        assert inspect.signature(alias) == inspect.signature(implementacion)

    for nombre in (
        "ACCESS_DEFAULT",
        "leer_reales_r09_fundo",
        "agregar",
        "leer",
        "escribir_json_reproducible",
    ):
        assert getattr(facade, nombre) is getattr(service, nombre)


def _tabla_sintetica() -> pd.DataFrame:
    filas = []
    for indice, semana in enumerate(range(20, 28)):
        emision = pd.Timestamp.fromisocalendar(2026, semana - 1, 1)
        filas.append(
            {
                "campania": "C2026",
                "fecha_emision": emision,
                "fecha_objetivo": emision + pd.Timedelta(weeks=1),
                "semana_objetivo": semana,
                "macro_h1": 100.0 + indice,
                "macro_h2": 120.0 + indice,
                "macro_h3": 140.0 + indice,
                "real_kg": 120.0 + indice,
                "r09_kg": 118.0 + indice,
                "r09_disponible": indice % 2 == 0,
            }
        )
    tabla = pd.DataFrame(filas)
    tabla.loc[2, "macro_h2"] = np.nan
    tabla.loc[3, "macro_h3"] = np.nan
    return tabla


def test_paridad_de_ponderacion_seleccion_prediccion_metricas_y_keyset() -> None:
    tabla = _tabla_sintetica()
    config = service.Configuracion(
        lookback=6,
        min_historia=4,
        half_life=4.0,
        penalizacion_shift=0.02,
        penalizacion_escala=0.01,
    )

    np.testing.assert_allclose(
        facade._ponderaciones(8, config.half_life),
        service._ponderaciones(8, config.half_life),
    )
    assert facade._elegir(tabla.iloc[:6], config) == service._elegir(tabla.iloc[:6], config)
    pd.testing.assert_frame_equal(
        facade._predecir_online(tabla, config),
        service._predecir_online(tabla, config),
    )
    assert facade._metricas(tabla, "macro_h1") == service._metricas(tabla, "macro_h1")
    assert facade._keyset_sha256(tabla) == service._keyset_sha256(tabla)


def test_prediccion_online_no_usa_r09_ni_datos_futuros() -> None:
    tabla = _tabla_sintetica()
    config = service.Configuracion(6, 4, 4.0, 0.02, 0.01)
    original = facade._predecir_online(tabla, config)

    mutado = tabla.copy()
    mutado.loc[:, "r09_kg"] = 999_999.0
    mutado.loc[:, "r09_disponible"] = True
    mutado.loc[6:, "real_kg"] = 999_999.0
    alterado = facade._predecir_online(mutado, config)

    columnas_prediccion = ["candidate_kg", "shift", "escala", "n_historia"]
    pd.testing.assert_frame_equal(
        original.loc[:5, columnas_prediccion].reset_index(drop=True),
        alterado.loc[:5, columnas_prediccion].reset_index(drop=True),
    )
    assert original.loc[2, "candidate_kg"] == pytest.approx(original.loc[2, "macro_h1"])
    assert original.loc[3, "candidate_kg"] == pytest.approx(original.loc[3, "macro_h1"])


def test_fachada_cli_conserva_argumentos_serializacion_y_ruta(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    salida = tmp_path / "resultado" / "temporal_shift.json"
    resultado = {
        "ganador_micro_replay": "l6-m4-h4.0-pd0.02-ps0.01",
        "evaluation_contract": {"keyset_sha256": "abc", "n_filas": 2},
        "metricas": {"contrato_completo": {"n": 2}},
        "detalle": [{"valor": np.int64(3)}],
    }
    llamadas = []

    def fake_ejecutar(*, access, campania="C2026"):
        llamadas.append((access, campania))
        return resultado

    monkeypatch.setattr(facade, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screening_temporal_shift_online",
            "--access",
            str(tmp_path / "fuente.accdb"),
            "--salida",
            str(salida),
        ],
    )

    assert facade.main() == 0
    assert llamadas == [(tmp_path / "fuente.accdb", "C2026")]
    assert json.loads(salida.read_text(encoding="utf-8"))["detalle"] == [{"valor": 3}]
    assert json.loads(capsys.readouterr().out)["contrato"] == resultado["evaluation_contract"]


def test_fachada_es_compuerta_ast_sin_logica_de_negocio() -> None:
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
        if isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
    ]
    assert not [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
    ]
