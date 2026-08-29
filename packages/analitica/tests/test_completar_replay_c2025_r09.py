from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.scripts import completar_replay_c2025_r09 as facade
from analitica.servicios import completar_replay_c2025_r09 as service

SCRIPT = Path(facade.__file__)


def test_fachada_conserva_aliases_publicos_privados_constantes_y_firmas() -> None:
    for nombre in (
        "np",
        "pd",
        "settings",
        "RepositorioAnalytics",
        "metricas_cobertura_operacional",
        "metricas_pronostico",
        "RUN_COMPLETO",
        "RUN_ORIGEN",
        "SNAPSHOT_ID",
        "MODELO_R09",
        "_leer",
        "_metricas",
        "leer",
        "metricas",
        "ejecutar",
    ):
        assert getattr(facade, nombre) is getattr(service, nombre), nombre
        if callable(getattr(facade, nombre)):
            assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
                getattr(service, nombre)
            )

    assert service._leer is service.leer
    assert service._metricas is service.metricas


def test_fachada_y_servicio_conservan_paridad_de_metricas() -> None:
    tabla = pd.DataFrame(
        {
            "campania": ["C2025", "C2025", "C2025", "C2026"],
            "modelo": ["Macro", "Macro", "R09_publicado", "Macro"],
            "lote_id": [1, 2, 1, 3],
            "fecha_objetivo": pd.to_datetime(
                ["2025-01-06", "2025-01-06", "2025-01-06", "2026-01-05"]
            ),
            "real_kg": [100.0, 50.0, 100.0, 80.0],
            "p50_kg": [90.0, 60.0, 110.0, 80.0],
            "emitio_prediccion": [True, True, True, True],
        }
    )

    resultado_fachada = facade._metricas(tabla)
    resultado_servicio = service._metricas(tabla)
    pd.testing.assert_frame_equal(resultado_fachada, resultado_servicio)


def test_ejecutar_conserva_consolidacion_persistencia_y_resumen(
    monkeypatch,
) -> None:
    predicciones = pd.DataFrame(
        {
            "modelo": ["HibridoOcurrenciaOnline_v2", "R09_publicado"],
            "campania": ["C2025", "C2025"],
            "lote_id": [1, 2],
            "fecha_objetivo": pd.to_datetime(["2025-01-06", "2025-01-13"]),
        }
    )
    metricas = pd.DataFrame(
        {
            "campania": ["C2025"],
            "modelo": ["R09_publicado"],
            "wape": [0.1],
        }
    )
    llamadas: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, dsn: str) -> None:
            llamadas.append(("init", dsn))

        def crear_run(self, snapshot_id: int, tipo: str, configuracion: dict) -> int:
            llamadas.append(("crear_run", snapshot_id, tipo, configuracion))
            return 123

        def guardar_predicciones(self, run_id: int, tabla: pd.DataFrame) -> None:
            llamadas.append(("predicciones", run_id, tabla.copy()))

        def guardar_metricas(self, run_id: int, tabla: pd.DataFrame) -> None:
            llamadas.append(("metricas", run_id, tabla.copy()))

        def finalizar_run(self, run_id: int, estado: str, *detalle: str) -> None:
            llamadas.append(("finalizar", run_id, estado, *detalle))

    monkeypatch.setattr(service, "_leer", lambda: predicciones.copy())
    monkeypatch.setattr(service, "_metricas", lambda tabla: metricas.copy())
    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-prueba")

    resumen = service.ejecutar()

    assert resumen == {
        "run_id": 123,
        "filas": 2,
        "r09_c2025_filas": 1,
        "c2025_semanas_por_modelo": {
            "HibridoOcurrenciaOnline_v2": 1,
            "R09_publicado": 1,
        },
        "metricas_c2025": [{"campania": "C2025", "modelo": "R09_publicado", "wape": 0.1}],
    }
    assert llamadas[0] == ("init", "dsn-prueba")
    assert llamadas[1] == (
        "crear_run",
        40,
        "backtest",
        {
            "base_validada": 77,
            "r09_origen": 76,
            "modelo_hibrido": "HibridoOcurrenciaOnline_v2",
            "universo": "C2025_completa_mas_R09_publicado_disponible",
            "r09": "referencia_publicada_no_algoritmo",
        },
    )
    assert llamadas[-1] == ("finalizar", 123, "succeeded")


def test_cli_conserva_argumentos_y_serializacion(monkeypatch, capsys) -> None:
    resultado = {"entero": np.int64(3), "fecha": pd.Timestamp("2026-08-16")}
    monkeypatch.setattr(facade, "ejecutar", lambda: resultado)
    monkeypatch.setattr(sys, "argv", ["completar_replay_c2025_r09"])

    assert facade.main() is None
    assert json.loads(capsys.readouterr().out) == {
        "entero": "3",
        "fecha": "2026-08-16 00:00:00",
    }


def test_fachada_es_adaptador_cli_y_servicio_no_depende_de_scripts() -> None:
    arbol_fachada = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    definiciones = [
        nodo.name
        for nodo in arbol_fachada.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not any(
        isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
        for nodo in ast.walk(arbol_fachada)
    )
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
        for nodo in ast.walk(arbol_fachada)
    )

    arbol_servicio = ast.parse(
        Path(service.__file__).read_text(encoding="utf-8"), filename=str(service.__file__)
    )
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
        for nodo in ast.walk(arbol_servicio)
    )
