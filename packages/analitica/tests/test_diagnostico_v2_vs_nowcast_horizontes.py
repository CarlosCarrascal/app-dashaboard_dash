from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.servicios import diagnostico_nowcast_horizontes as servicio
from analitica.interfaces.scripts import diagnostico_v2_vs_nowcast_horizontes as fachada

SCRIPT = Path(fachada.__file__)


def test_fachada_conserva_aliases_identidad_y_firmas() -> None:
    nombres = (
        "ConfiguracionCorreccionHorizonte",
        "aplicar_correccion_horizonte",
        "configuraciones_loop",
        "ejecutar_loop_horizonte",
        "metricas_horizonte",
        "leer_v2",
        "leer_nowcast",
        "_seleccionar_total_nowcast",
        "_resumen_serie_semanal",
        "_seleccionar_vintage_coherente",
        "_metricas_serie",
        "resumen_nowcast",
        "ejecutar",
    )
    for nombre in nombres:
        alias = getattr(fachada, nombre)
        implementacion = getattr(servicio, nombre)
        assert alias is implementacion
        if callable(alias):
            assert inspect.signature(alias) == inspect.signature(implementacion)

    for nombre in ("RUN_V2_APROBADO", "RUN_V2_LABORATORIO", "RUN_NOWCAST"):
        assert getattr(fachada, nombre) is getattr(servicio, nombre)

    for nombre in ("pd", "psycopg", "postgres_dsn"):
        assert getattr(fachada, nombre) is getattr(servicio, nombre)


def test_fachada_solo_conserva_el_adaptador_cli() -> None:
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
        and nodo.module.startswith("analitica.interfaces.scripts.")
    ]


def test_fachada_y_servicio_conservan_paridad_de_series_y_metricas() -> None:
    tabla = pd.DataFrame(
        {
            "fecha_objetivo": ["2026-08-03", "2026-08-03", "2026-08-10"],
            "fecha_emision": ["2026-07-27", "2026-07-20", "2026-08-03"],
            "fundo": ["Arena", "Empresa", "Empresa"],
            "p50_kg": [40.0, 100.0, 80.0],
            "real_kg": [50.0, 100.0, 100.0],
        }
    )
    pd.testing.assert_frame_equal(
        fachada._seleccionar_total_nowcast(tabla),
        servicio._seleccionar_total_nowcast(tabla),
    )
    pd.testing.assert_frame_equal(
        fachada._resumen_serie_semanal(
            tabla,
            fecha_columna="fecha_objetivo",
            pred_columna="p50_kg",
        ),
        servicio._resumen_serie_semanal(
            tabla,
            fecha_columna="fecha_objetivo",
            pred_columna="p50_kg",
        ),
    )

    resumen_fachada = fachada.resumen_nowcast(tabla, fecha_maxima=pd.Timestamp("2026-08-10"))
    resumen_servicio = servicio.resumen_nowcast(tabla, fecha_maxima=pd.Timestamp("2026-08-10"))
    assert resumen_fachada == resumen_servicio
    assert resumen_fachada["n_semanas"] == 2


def test_fachada_cli_conserva_argumento_serializacion_y_ruta(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    salida = tmp_path / "resultado" / "diagnostico.json"
    resultado = {"entero": np.int64(3), "fecha": pd.Timestamp("2026-08-16")}

    monkeypatch.setattr(fachada, "ejecutar", lambda: resultado)
    monkeypatch.setattr(
        sys,
        "argv",
        ["diagnostico_v2_vs_nowcast_horizontes", "--salida", str(salida)],
    )

    assert fachada.main() == 0
    esperado = {"entero": "3", "fecha": "2026-08-16 00:00:00"}
    assert json.loads(salida.read_text(encoding="utf-8")) == esperado
    assert json.loads(capsys.readouterr().out) == esperado
