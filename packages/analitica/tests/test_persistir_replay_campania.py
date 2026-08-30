from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from analitica.aplicacion.servicios import persistir_replay_campania as service
from analitica.interfaces.scripts import persistir_replay_campania as facade

SCRIPT = Path(facade.__file__)


def _datos_sinteticos() -> SimpleNamespace:
    return SimpleNamespace(
        forecast=pd.DataFrame({"campania": ["C2026"]}),
        cosecha=pd.DataFrame({"campania": ["C2026"]}),
        fuente=SimpleNamespace(nombre="fuente-sintetica"),
    )


def _backtest_sintetico() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "lote_id": [101, 102],
            "fecha_emision": pd.to_datetime(["2026-01-01", "2026-01-01"]),
            "fecha_objetivo": pd.to_datetime(["2026-01-08", "2026-01-08"]),
            "real_kg": [100.0, 80.0],
            "p50_kg": [95.0, 75.0],
            "version_fuente": ["r09-sintetico", "r09-sintetico"],
            "modelo": [service.MODELO_R09, service.MODELO_R09],
        }
    )


def _predicciones_sinteticas() -> pd.DataFrame:
    filas = []
    for modelo, prediccion, fuente in (
        (service.MODELO_R09, 95.0, "R09_PostgreSQL_snapshot"),
        (service.MODELO_MACRO, 96.0, "macro-sintetico"),
        (service.NOMBRE_MODELO, 97.0, "hibrido-sintetico"),
    ):
        filas.append(
            {
                "modelo": modelo,
                "campania": "C2026",
                "lote_id": 101,
                "fecha_emision": pd.Timestamp("2026-01-01"),
                "fecha_objetivo": pd.Timestamp("2026-01-08"),
                "version_fuente": fuente,
                "real_kg": 100.0,
                "p50_kg": prediccion,
            }
        )
    return pd.DataFrame(filas)


def _preparar_servicio(monkeypatch) -> None:
    datos = _datos_sinteticos()
    predicciones = _predicciones_sinteticas()
    resumen = {"campania": "C2026", "filas": {"sintetico": len(predicciones)}}
    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")
    monkeypatch.setattr(service, "cargar_datos", lambda _fuente: datos)
    monkeypatch.setattr(
        service,
        "construir_replay",
        lambda _datos, _campania, _horizonte, _max_cortes: (
            predicciones.copy(),
            resumen.copy(),
        ),
    )
    monkeypatch.setattr(
        service,
        "controles_predicciones",
        lambda _predicciones: pd.DataFrame([{"regla": "sintetica", "estado": "ok"}]),
    )
    monkeypatch.setattr(
        service,
        "metricas_pronostico",
        lambda _predicciones: pd.DataFrame([{"modelo": service.MODELO_R09, "n": 1}]),
    )
    monkeypatch.setattr(
        service,
        "metricas_pareadas_modelos",
        lambda _predicciones, *, modelo_base, modelo_candidato: pd.DataFrame(
            [{"modelo_base": modelo_base, "modelo": modelo_candidato, "n": 1}]
        ),
    )


def test_fachada_conserva_aliases_firmas_y_argumentos(monkeypatch) -> None:
    aliases = (
        "argparse",
        "np",
        "pd",
        "time",
        "settings",
        "RepositorioAnalytics",
        "construir_backtest",
        "controles_predicciones",
        "cargar_datos",
        "NOMBRE_MODELO",
        "VERSION_MODELO",
        "backtest_hibrido_v1",
        "backtest_macro_legacy_v1",
        "metricas_pareadas_modelos",
        "metricas_pronostico",
        "MODELO_MACRO",
        "MODELO_R09",
        "construir_replay",
        "persistir_campania",
        "resumir_salida_cli",
        "_argumentos",
        "_completar_prediccion",
        "_emisiones_r09",
    )
    for nombre in aliases:
        assert getattr(facade, nombre) is getattr(service, nombre), nombre
        if callable(getattr(facade, nombre)):
            assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
                getattr(service, nombre)
            ), nombre

    # ``_argumentos`` uses argparse's process argv; exercise all historical defaults
    # through an isolated argv instead of connecting to any external service.
    monkeypatch.setattr("sys.argv", ["replay", "--campania", "C2026"])
    argumentos = facade._argumentos()
    assert vars(argumentos) == {
        "campania": "C2026",
        "horizonte_semanas": 10,
        "max_cortes": 0,
        "dry_run": False,
    }
    assert facade.json.__name__ == "json"


def test_construccion_sintetica_fachada_y_servicio_tienen_paridad(monkeypatch) -> None:
    backtest = _backtest_sintetico()
    macro = backtest.copy()
    macro["p50_kg"] += 1.0
    macro["version_fuente"] = "macro-sintetico"
    hibrido = backtest.copy()
    hibrido["p50_kg"] += 2.0
    hibrido["version_fuente"] = "hibrido-sintetico"
    monkeypatch.setattr(service, "construir_backtest", lambda *_args: backtest.copy())
    monkeypatch.setattr(
        service,
        "backtest_macro_legacy_v1",
        lambda *_args, **kwargs: (macro.copy(), [f"macro:{kwargs['campania']}"]),
    )
    monkeypatch.setattr(
        service,
        "backtest_hibrido_v1",
        lambda *_args, **kwargs: (hibrido.copy(), [f"hibrido:{kwargs['campania']}"]),
    )
    monkeypatch.setattr(service.time, "perf_counter", lambda: 10.0)

    resultado_facade = facade.construir_replay(_datos_sinteticos(), "C2026", 10, 0)
    resultado_servicio = service.construir_replay(_datos_sinteticos(), "C2026", 10, 0)

    pd.testing.assert_frame_equal(resultado_facade[0], resultado_servicio[0])
    assert resultado_facade[1] == resultado_servicio[1]
    assert list(resultado_facade[0].modelo.unique()) == [
        service.MODELO_R09,
        service.MODELO_MACRO,
        service.NOMBRE_MODELO,
    ]
    assert resultado_facade[1]["advertencias"] == ["macro:C2026", "hibrido:C2026"]


def test_dry_run_no_instancia_ni_escribe_en_repositorio(monkeypatch) -> None:
    _preparar_servicio(monkeypatch)
    eventos: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, *_args, **_kwargs):
            eventos.append(("init",))

        def __getattr__(self, nombre):
            def registrar(*args, **kwargs):
                eventos.append((nombre, args, kwargs))

            return registrar

    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)

    resultado_facade = facade.persistir_campania("C2026", dry_run=True)
    resultado_servicio = service.persistir_campania("C2026", dry_run=True)

    assert resultado_facade == resultado_servicio
    assert resultado_facade["filas_predicciones"] == 3
    assert eventos == []


def test_persistencia_conserva_orden_y_finaliza_failed(monkeypatch) -> None:
    _preparar_servicio(monkeypatch)
    eventos: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, dsn):
            eventos.append(("init", dsn))

        def snapshot(self, datos):
            eventos.append(("snapshot", datos))
            return 700

        def crear_run(self, *args):
            eventos.append(("crear_run", *args))
            return 701

        def guardar_predicciones(self, *args):
            eventos.append(("guardar_predicciones", *args))

        def guardar_metricas(self, *args):
            eventos.append(("guardar_metricas", *args))
            raise RuntimeError("fallo sintetico")

        def finalizar_run(self, *args):
            eventos.append(("finalizar_run", *args))

    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)

    with pytest.raises(RuntimeError, match="fallo sintetico"):
        service.persistir_campania("C2026")

    assert [evento[0] for evento in eventos] == [
        "init",
        "snapshot",
        "crear_run",
        "guardar_predicciones",
        "guardar_metricas",
        "finalizar_run",
    ]
    assert eventos[-1] == ("finalizar_run", 701, "failed", "fallo sintetico")


def test_fachada_es_adaptador_cli_delgado() -> None:
    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    definiciones = [
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not any(
        isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
        for nodo in ast.walk(arbol)
    )
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
        for nodo in ast.walk(arbol)
    )


def test_salida_cli_conserva_json_resumido(monkeypatch, capsys) -> None:
    resultado = {
        "campania": "C2026",
        "metricas": [{"modelo": service.MODELO_R09, "n": 1}],
        "comparaciones": [
            {
                "modelo_base": service.MODELO_R09,
                "modelo": service.MODELO_MACRO,
                "banda_horizonte": "total",
                "n": 1,
                "wape": 0.1,
                "sesgo_pct": 2.0,
            }
        ],
        "calidad": [{"estado": "ok"}],
    }
    monkeypatch.setattr(facade, "_argumentos", lambda: SimpleNamespace(
        campania="C2026", horizonte_semanas=10, max_cortes=0, dry_run=True
    ))
    monkeypatch.setattr(facade, "persistir_campania", lambda *args, **kwargs: resultado)

    facade.main()
    salida = json.loads(capsys.readouterr().out)
    assert salida == {
        "campania": "C2026",
        "n_metricas": 1,
        "n_comparaciones": 1,
        "comparacion_resumen": [
            {
                "modelo_base": service.MODELO_R09,
                "modelo": service.MODELO_MACRO,
                "banda": "total",
                "n": 1,
                "wape": 0.1,
                "sesgo_pct": 2.0,
            }
        ],
        "n_calidad": 1,
    }
