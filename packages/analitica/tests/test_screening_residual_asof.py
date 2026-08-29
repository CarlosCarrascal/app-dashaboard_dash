from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analitica.scripts import screening_residual_asof as facade
from analitica.servicios import residual_asof as service

SCRIPT = Path(facade.__file__)


def test_fachada_conserva_aliases_identidad_y_firmas() -> None:
    nombres = (
        "ConfiguracionResidualAsOf",
        "aplicar_calibracion_residual_asof",
        "configuraciones",
        "leer_panel",
        "_semanal",
        "comparar_comun",
        "score",
        "ejecutar",
    )
    for nombre in nombres:
        alias = getattr(facade, nombre)
        implementacion = getattr(service, nombre)
        assert alias is implementacion
        assert inspect.signature(alias) == inspect.signature(implementacion)

    for nombre in (
        "RUNS",
        "CIERRES",
        "asdict",
        "np",
        "pd",
        "psycopg",
        "escribir_json_reproducible",
        "postgres_dsn",
    ):
        assert getattr(facade, nombre) is getattr(service, nombre)


def _tabla_modelo(
    valores: list[tuple[str, str, str, int, float, float]],
) -> pd.DataFrame:
    filas = []
    for campania, emision, objetivo, horizonte, prediccion, real in valores:
        for lote, proporcion in (("L1", 0.4), ("L2", 0.6)):
            filas.append(
                {
                    "campania": campania,
                    "fecha_emision": pd.Timestamp(emision),
                    "fecha_objetivo": pd.Timestamp(objetivo),
                    "horizonte_semanas": horizonte,
                    "lote_id": lote,
                    "fundo": "F1",
                    "modulo": "M1",
                    "p50_kg": prediccion * proporcion,
                    "real_kg": real * proporcion,
                }
            )
    return pd.DataFrame(filas)


def test_paridad_de_agregacion_comparacion_y_score() -> None:
    datos = [
        ("C2024", "2025-01-06", "2025-01-12", 1, 30.0, 30.0),
        ("C2024", "2025-01-13", "2025-01-19", 2, 40.0, 50.0),
    ]
    macro = _tabla_modelo(datos)
    candidato = _tabla_modelo(
        [
            ("C2024", "2025-01-06", "2025-01-12", 1, 30.0, 30.0),
            ("C2024", "2025-01-13", "2025-01-19", 2, 45.0, 50.0),
        ]
    )
    r09 = _tabla_modelo(
        [
            ("C2024", "2025-01-06", "2025-01-12", 1, 30.0, 29.0),
            ("C2024", "2025-01-13", "2025-01-19", 2, 44.0, 50.0),
        ]
    )

    pd.testing.assert_frame_equal(
        facade._semanal(macro, "p50_kg"), service._semanal(macro, "p50_kg")
    )
    resultado = facade.comparar_comun(macro, candidato, r09, {"C2024"})
    assert resultado["n_emision_objetivo_horizonte"] == 2
    assert resultado["volumen_real_kg"] == pytest.approx(80.0)
    assert resultado["porcentaje_cortes_ganados_a_r09"] == pytest.approx(0.5)
    assert resultado["por_modelo"]["MacroLegacy_v1"] == {
        "wape": pytest.approx(0.125),
        "sesgo": pytest.approx(-0.125),
        "mae_kg": pytest.approx(5.0),
    }
    assert resultado["por_modelo"]["CandidateResidualAsOf_v1"] == {
        "wape": pytest.approx(0.0625),
        "sesgo": pytest.approx(-0.0625),
        "mae_kg": pytest.approx(2.5),
    }
    assert facade.score(resultado) == service.score(resultado)


def test_configuraciones_preservan_la_malla_historica() -> None:
    configuraciones = facade.configuraciones()
    assert len(configuraciones) == 16
    assert {config.nivel for config in configuraciones} == {"global", "fundo"}
    assert {config.ventana for config in configuraciones} == {4, 8}
    assert {config.regularizacion for config in configuraciones} == {2.0, 6.0}
    assert {config.usar_campanias_previas for config in configuraciones} == {False, True}
    assert all(
        config.factor_min == 0.80 and config.factor_max == 1.30
        for config in configuraciones
    )


def test_fachada_cli_conserva_argumento_salida_y_serializacion(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    salida = tmp_path / "resultado" / "residual_asof.json"
    resultado = {
        "mejor": {"valor": np.int64(3)},
        "decision": {"publicable": False},
        "protocolo_c2026_temporal": {"holdout": "C2026"},
    }
    llamadas = []

    def fake_ejecutar():
        return resultado

    def fake_escribir(valor, ruta):
        llamadas.append((valor, ruta))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(valor, default=str), encoding="utf-8")

    monkeypatch.setattr(facade, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(facade, "escribir_json_reproducible", fake_escribir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["screening_residual_asof", "--salida", str(salida)],
    )

    assert facade.main() == 0
    assert llamadas == [(resultado, salida)]
    assert json.loads(salida.read_text(encoding="utf-8"))["mejor"] == {"valor": "3"}
    assert '"publicable": false' in capsys.readouterr().out


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
