from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from analitica.scripts import persistir_ocurrencia_universo as facade
from analitica.servicios import persistir_ocurrencia_universo as service

SCRIPT = Path(facade.__file__)


def _universo_sintetico() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "prediction_id": [10, 20, 11, 21],
            "run_id": [71, 72, 71, 72],
            "modelo": [service.MODELO_R09, service.MODELO_MACRO] * 2,
            "campania": ["C2026"] * 4,
            "lote_id": [101, 101, 102, 102],
            "lote": ["L101", "L101", "L102", "L102"],
            "fundo": ["Aqu Anqa 1"] * 4,
            "modulo": ["M01"] * 4,
            "fecha_emision": pd.to_datetime(
                ["2026-01-01", "2026-01-01", "2026-01-08", "2026-01-08"]
            ),
            "fecha_objetivo": pd.to_datetime(
                ["2026-01-05", "2026-01-05", "2026-01-12", "2026-01-12"]
            ),
            "horizonte_semanas": [1] * 4,
            "real_kg": [100.0, 100.0, 80.0, 80.0],
            "p50_kg": [90.0, 95.0, 70.0, 75.0],
        }
    )


def test_fachada_conserva_aliases_publicos_privados_y_firmas() -> None:
    aliases = (
        "argparse",
        "np",
        "pd",
        "settings",
        "RepositorioAnalytics",
        "NOMBRE_MODELO",
        "VERSION_MODELO",
        "ejecutar_replay_hibrido_ocurrencia",
        "metricas_semanales",
        "metricas_pareadas_modelos",
        "MODELO_R09",
        "MODELO_MACRO",
        "SNAPSHOT_ID",
        "RUNS_MACRO",
        "CLAVES",
        "construir_corrida",
        "persistir",
        "_argumentos",
        "_leer_universo",
        "_por_modelo",
        "_preparar_panel_ocurrencia",
        "_contrato_predicciones",
    )
    for nombre in aliases:
        assert getattr(facade, nombre) is getattr(service, nombre), nombre
        if callable(getattr(facade, nombre)):
            assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
                getattr(service, nombre)
            ), nombre
    assert facade.json.__name__ == "json"


def test_leer_universo_usa_doble_psycopg_y_conserva_interseccion_ordenada(monkeypatch) -> None:
    origen = pd.DataFrame(
        {
            "prediction_id": [1, 2, 3, 4, 5, 6, 7, 8, 9],
            "run_id": [71, 71, 72, 73, 71, 72, 71, 72, 71],
            "modelo": [
                service.MODELO_R09,
                service.MODELO_R09,
                service.MODELO_MACRO,
                service.MODELO_R09,
                service.MODELO_MACRO,
                service.MODELO_R09,
                service.MODELO_MACRO,
                service.MODELO_R09,
                service.MODELO_MACRO,
            ],
            "campania": ["C2026"] * 9,
            "lote_id": [101, 101, 101, 101, 101, 102, 103, 104, 105],
            "fecha_emision": pd.to_datetime(
                [
                    "2025-12-29",
                    "2025-12-30",
                    "2025-12-28",
                    "2025-12-27",
                    "2026-01-02",
                    "2026-01-03",
                    "2026-01-03",
                    "2026-01-03",
                    "2026-01-03",
                ]
            ),
            "fecha_objetivo": pd.to_datetime(["2026-01-05"] * 5 + ["2026-01-12"] * 4),
            "horizonte_semanas": [1, 1, 1, 1, 1, 1, 1, 2, 1],
            "real_kg": [90.0, 91.0, 90.0, 92.0, 90.0, 80.0, 70.0, 60.0, None],
            "p50_kg": [80.0, 81.0, 82.0, 83.0, 84.0, 75.0, 65.0, 55.0, 50.0],
        }
    )
    conexion = object()
    llamadas: list[tuple[str, object, object]] = []

    class ConexionFalsa:
        def __enter__(self):
            return conexion

        def __exit__(self, *_args):
            return False

    def conectar(dsn):
        llamadas.append(("connect", dsn, None))
        return ConexionFalsa()

    def leer_sql(consulta, recibida, params):
        llamadas.append((consulta, recibida, params))
        assert "HAVING COUNT(DISTINCT modelo) = 2" in consulta
        assert "ORDER BY u.campania, u.fecha_objetivo, u.lote_id, u.modelo" in consulta
        assert recibida is conexion
        assert params == ([71, 72, 73], [service.MODELO_R09, service.MODELO_MACRO])

        candidatos = origen[
            origen.run_id.isin(params[0])
            & origen.modelo.isin(params[1])
            & origen.horizonte_semanas.eq(1)
            & origen.real_kg.notna()
        ].copy()
        candidatos = candidatos.sort_values(
            ["modelo", "campania", "lote_id", "fecha_objetivo", "fecha_emision", "prediction_id"],
            ascending=[True, True, True, True, False, False],
        )
        candidatos["rn"] = candidatos.groupby(
            ["modelo", "campania", "lote_id", "fecha_objetivo"]
        ).cumcount() + 1
        unicos = candidatos[candidatos.rn.eq(1)].copy()
        comunes = (
            unicos.groupby(["campania", "lote_id", "fecha_objetivo"])["modelo"]
            .nunique()
            .loc[lambda serie: serie.eq(2)]
            .index
        )
        salida = unicos.set_index(["campania", "lote_id", "fecha_objetivo"]).loc[comunes]
        return (
            salida.reset_index()
            .sort_values(["campania", "fecha_objetivo", "lote_id", "modelo"])
            .reset_index(drop=True)
        )

    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=conectar))
    monkeypatch.setattr(service.pd, "read_sql_query", leer_sql)

    resultado = service._leer_universo()

    assert llamadas[0] == ("connect", "dsn-sintetico", None)
    assert list(zip(resultado.lote_id, resultado.modelo, strict=True)) == [
        (101, service.MODELO_MACRO),
        (101, service.MODELO_R09),
    ]
    assert resultado.prediction_id.tolist() == [5, 2]
    assert resultado.rn.tolist() == [1, 1]
    assert resultado.fecha_emision.dtype == "datetime64[ns]"
    assert resultado.fecha_objetivo.dtype == "datetime64[ns]"


def test_fachada_y_servicio_conservan_paridad_del_universo_y_la_corrida(monkeypatch) -> None:
    universo = _universo_sintetico()

    def replay_falso(panel):
        assert panel["modelo"].eq(service.MODELO_MACRO).all()
        assert panel["version_fuente"].eq("snapshot_40_universo_R09_Macro_h1").all()
        ocurrencia = panel.copy()
        ocurrencia["p50_kg"] = ocurrencia["p50_kg"] * 0.8
        resumen = panel.groupby("fecha_objetivo", as_index=False).size()
        return ocurrencia, resumen

    def metricas_semanales_falsas(semanal):
        return {"wape": float(semanal.p50_kg.sum() / semanal.real_kg.sum())}

    monkeypatch.setattr(service, "_leer_universo", lambda: universo.copy())
    monkeypatch.setattr(service, "ejecutar_replay_hibrido_ocurrencia", replay_falso)
    monkeypatch.setattr(service, "metricas_semanales", metricas_semanales_falsas)
    monkeypatch.setattr(
        service,
        "metricas_pareadas_modelos",
        lambda *_args, **_kwargs: pd.DataFrame(
            {"modelo": [service.NOMBRE_MODELO], "wape": [0.2]}
        ),
    )

    pred_fachada, resumen_fachada = facade.construir_corrida()
    pred_servicio, resumen_servicio = service.construir_corrida()

    pd.testing.assert_frame_equal(pred_fachada, pred_servicio)
    assert resumen_fachada == resumen_servicio
    assert resumen_servicio["filas_universo_lote_semana"] == 2
    assert resumen_servicio["semanas_universo"] == 2
    assert set(pred_servicio.modelo) == {
        service.MODELO_R09,
        service.MODELO_MACRO,
        service.NOMBRE_MODELO,
    }
    for modelo in resumen_servicio["modelos"]:
        assert set(
            map(
                tuple,
                pred_servicio.loc[pred_servicio.modelo.eq(modelo), service.CLAVES].to_numpy(),
            )
        ) == set(map(tuple, universo[service.CLAVES].drop_duplicates().to_numpy()))


def test_dry_run_no_escribe_en_repositorio(monkeypatch) -> None:
    resumen = {
        "snapshot_id": service.SNAPSHOT_ID,
        "runs_origen": list(service.RUNS_MACRO),
        "modelos": [service.MODELO_R09, service.MODELO_MACRO, service.NOMBRE_MODELO],
        "campanias": ["C2026"],
        "metricas": [],
        "comparaciones": [],
    }
    escrituras: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, *_args, **_kwargs):
            escrituras.append(("init",))

        def __getattr__(self, nombre):
            def registrar(*args, **kwargs):
                escrituras.append((nombre, args, kwargs))

            return registrar

    monkeypatch.setattr(service, "construir_corrida", lambda: (pd.DataFrame(), resumen.copy()))
    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(
        service.settings,
        "postgres_dsn",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run no debe pedir DSN")),
    )

    assert facade.persistir(dry_run=True) == resumen
    assert escrituras == []


def test_persistencia_conserva_orden_de_escrituras_con_repositorio_falso(monkeypatch) -> None:
    predicciones = pd.DataFrame({"modelo": [service.MODELO_R09]})
    resumen = {
        "modelos": [service.MODELO_R09],
        "campanias": ["C2026"],
        "metricas": [{"modelo": service.MODELO_R09}],
        "comparaciones": [{"modelo": service.MODELO_R09}],
    }
    llamadas: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, dsn):
            llamadas.append(("init", dsn))

        def crear_run(self, *args):
            llamadas.append(("crear_run", *args))
            return 901

        def guardar_predicciones(self, *args):
            llamadas.append(("guardar_predicciones", *args))

        def guardar_metricas(self, *args):
            llamadas.append(("guardar_metricas", *args))

        def guardar_metricas_comparacion(self, *args):
            llamadas.append(("guardar_metricas_comparacion", *args))

        def finalizar_run(self, *args):
            llamadas.append(("finalizar_run", *args))

    monkeypatch.setattr(service, "construir_corrida", lambda: (predicciones, resumen))
    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")

    resultado = service.persistir()

    assert resultado["run_id"] == 901
    assert [llamada[0] for llamada in llamadas] == [
        "init",
        "crear_run",
        "guardar_predicciones",
        "guardar_metricas",
        "guardar_metricas_comparacion",
        "finalizar_run",
    ]
    assert llamadas[-1] == ("finalizar_run", 901, "succeeded")


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
        and nodo.module.startswith("analitica.scripts.")
        for nodo in ast.walk(arbol)
    )
