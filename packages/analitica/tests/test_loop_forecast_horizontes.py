from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.servicios import loop_forecast_horizontes as servicio
from analitica.interfaces.scripts import loop_forecast_horizontes as fachada

SCRIPT = Path(fachada.__file__)


def test_fachada_conserva_aliases_privados_publicos_constantes_y_firmas() -> None:
    nombres = (
        "_leer_predicciones",
        "_normalizar_fundo",
        "_consolidar_fundos",
        "_panel_base",
        "_semanal",
        "_metricas",
        "_aplicar_mejores",
        "_metricas_por_horizonte",
        "_comparar_r09",
        "_leer_nowcast",
        "_resumen_nowcast_vs_v2",
        "ConfiguracionCorreccionHorizonte",
        "aplicar_correccion_horizonte",
        "configuraciones_loop",
        "ejecutar_loop_por_horizonte",
        "seleccionar_vintage_coherente",
        "ejecutar",
    )
    for nombre in nombres:
        alias = getattr(fachada, nombre)
        implementacion = getattr(servicio, nombre)
        assert alias is implementacion, nombre
        if callable(alias):
            assert inspect.signature(alias) == inspect.signature(implementacion), nombre

    for nombre in (
        "RUN_MACRO_MULTI",
        "RUN_H1_APROBADO",
        "RUN_R09_MULTI",
        "RUN_NOWCAST",
        "CIERRES",
        "HORIZONTES",
        "HORIZONTES_LARGOS",
    ):
        assert getattr(fachada, nombre) is getattr(servicio, nombre), nombre

    for nombre in ("Any", "pd", "psycopg", "postgres_dsn"):
        assert getattr(fachada, nombre) is getattr(servicio, nombre), nombre

    assert fachada.argparse.__name__ == "argparse"
    assert fachada.json.__name__ == "json"
    assert fachada.Path is Path


def test_fachada_es_delgada_y_servicio_no_depende_de_scripts() -> None:
    arbol_fachada = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    definiciones = [
        nodo.name
        for nodo in arbol_fachada.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not [
        nodo
        for nodo in ast.walk(arbol_fachada)
        if isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
    ]
    assert not [
        nodo
        for nodo in ast.walk(arbol_fachada)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
    ]

    arbol_servicio = ast.parse(
        Path(servicio.__file__).read_text(encoding="utf-8"), filename=str(servicio.__file__)
    )
    assert not [
        nodo
        for nodo in ast.walk(arbol_servicio)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
    ]


def test_fachada_y_servicio_conservan_paridad_de_normalizacion_agregacion_y_metricas() -> None:
    assert [fachada._normalizar_fundo(valor) for valor in ("Aqu Anqa 3", "ayllu", None)] == [
        servicio._normalizar_fundo(valor) for valor in ("Aqu Anqa 3", "ayllu", None)
    ]
    tabla = pd.DataFrame(
        {
            "campania": ["C2026", "C2026", "C2026"],
            "fecha_emision": pd.to_datetime(["2026-07-20"] * 3),
            "fecha_objetivo": pd.to_datetime(["2026-08-03"] * 3),
            "horizonte_semanas": [2, 2, 3],
            "fundo": ["Kawsay", "Kawsay", "Arena"],
            "p50_kg": [10.0, 5.0, 20.0],
            "real_kg": [12.0, np.nan, 18.0],
            "n_filas": [1, 2, 1],
            "n_reales": [1, 0, 1],
        }
    )
    pd.testing.assert_frame_equal(
        fachada._consolidar_fundos(tabla), servicio._consolidar_fundos(tabla)
    )
    pd.testing.assert_frame_equal(
        fachada._semanal(tabla, "p50_kg"), servicio._semanal(tabla, "p50_kg")
    )
    assert fachada._metricas(tabla, "p50_kg") == servicio._metricas(tabla, "p50_kg")
    assert fachada._metricas_por_horizonte(tabla, "p50_kg") == servicio._metricas_por_horizonte(
        tabla, "p50_kg"
    )


def test_fachada_cli_conserva_argumentos_json_y_ruta_de_salida(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    salida = tmp_path / "resultado" / "loop.json"
    resultado = {"entero": np.int64(3), "fecha": pd.Timestamp("2026-08-16")}
    llamadas: list[tuple[str, str | None]] = []

    def ejecutar_falso(campania: str, desarrollo_hasta: str | None) -> dict[str, object]:
        llamadas.append((campania, desarrollo_hasta))
        return resultado

    monkeypatch.setattr(fachada, "ejecutar", ejecutar_falso)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loop_forecast_horizontes",
            "--campania",
            "C2025",
            "--desarrollo-hasta",
            "2026-01-18",
            "--salida",
            str(salida),
        ],
    )

    assert fachada.main() == 0
    esperado = {"entero": "3", "fecha": "2026-08-16 00:00:00"}
    assert llamadas == [("C2025", "2026-01-18")]
    assert json.loads(salida.read_text(encoding="utf-8")) == esperado
    assert json.loads(capsys.readouterr().out) == esperado
