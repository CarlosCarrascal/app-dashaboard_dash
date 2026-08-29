from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from analitica.scripts import persistir_proyeccion_operativa_v2 as facade
from analitica.servicios import persistir_proyeccion_operativa_v2 as service

SCRIPT = Path(facade.__file__)


def _fuentes_sinteticas() -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    emision = pd.Timestamp("2026-04-08")
    actual = pd.DataFrame(
        {
            "prediction_id": [1, 2, 3, 4],
            "run_id": [901] * 4,
            "modelo": ["ModeloOperativoActual_v1"] * 4,
            "campania": ["C2026"] * 4,
            "lote_id": [101, 102, 103, 101],
            "lote": ["L101", "L102", "L103", "L101"],
            "fecha_emision": [emision] * 4,
            "fecha_objetivo": pd.to_datetime(
                ["2026-04-06", "2026-04-06", "2026-04-13", "2026-03-30"]
            ),
            "p50_kg": [100.0, 50.0, 80.0, 999.0],
            "real_kg": [None, None, None, None],
        }
    )
    historico = pd.DataFrame(
        {
            "prediction_id": [11],
            "run_id": [701],
            "modelo": ["MacroLegacy_v1"],
            "campania": ["C2026"],
            "lote_id": [101],
            "lote": ["L101"],
            "fecha_emision": [pd.Timestamp("2026-04-01")],
            "fecha_objetivo": [pd.Timestamp("2026-03-30")],
            "p50_kg": [90.0],
            "real_kg": [88.0],
        }
    )
    return actual, historico, emision


def _meta_base() -> dict[str, object]:
    return {
        "snapshot_id": 42,
        "fecha_emision": "2026-04-08",
        "fuente_run_operativo": 901,
        "fuente_run_historico": 701,
    }


def test_cargar_fuentes_conserva_run_snapshot_y_corte_as_of(monkeypatch) -> None:
    actual, historico, emision = _fuentes_sinteticas()
    conexion = object()
    llamadas: list[tuple[str, object, object]] = []

    class ConexionFalsa:
        def __enter__(self):
            return conexion

        def __exit__(self, *_args):
            return False

    def conectar(dsn, connect_timeout):
        llamadas.append(("connect", dsn, connect_timeout))
        return ConexionFalsa()

    def leer_sql(consulta, recibida, params=None):
        llamadas.append((consulta, recibida, params))
        assert recibida is conexion
        if "p.modelo = 'ModeloOperativoActual_v1'" in consulta:
            assert params is None
            return actual.assign(fuente_snapshot_id=42, fuente_run_id=901)
        assert "p.fecha_objetivo < %s" in consulta
        assert params == ("C2026", "C2026", pd.Timestamp("2026-04-06").date())
        return historico.copy()

    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=conectar))
    monkeypatch.setattr(service.pd, "read_sql_query", leer_sql)

    actual_out, historico_out, snapshot_id, fuente_run_id, emision_out = service._cargar_fuentes()

    assert llamadas[0] == ("connect", "dsn-sintetico", 5)
    assert snapshot_id == 42
    assert fuente_run_id == 901
    assert emision_out == emision
    assert historico_out["fecha_emision"].eq(emision).all()
    assert len(actual_out) == len(actual)


def test_fachada_conserva_aliases_privados_publicos_y_firmas() -> None:
    aliases = (
        "argparse",
        "np",
        "pd",
        "settings",
        "RepositorioAnalytics",
        "NOMBRE_MODELO",
        "VERSION_MODELO",
        "ejecutar_replay_hibrido_ocurrencia_v2",
        "banda_horizonte",
        "MODELO_BASE",
        "CLAVES_SEMANA",
        "construir_corrida",
        "persistir",
        "_argumentos",
        "_semana_inicio",
        "_primero",
        "_cargar_fuentes",
        "_agregar_semana",
        "_construir_base",
        "_componentes",
        "_distribuir_a_panas",
    )
    for nombre in aliases:
        assert getattr(facade, nombre) is getattr(service, nombre), nombre
        if callable(getattr(facade, nombre)):
            assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
                getattr(service, nombre)
            ), nombre


def test_fachada_y_servicio_conservan_filas_semanas_y_suma_kg(monkeypatch) -> None:
    actual, historico, emision = _fuentes_sinteticas()

    base, futuro = service._construir_base(actual, historico, emision)
    assert len(futuro) == 3
    assert set(base.fecha_objetivo) == {
        pd.Timestamp("2026-03-30"),
        pd.Timestamp("2026-04-06"),
        pd.Timestamp("2026-04-13"),
    }
    assert not base.duplicated(service.CLAVES_SEMANA).any()
    assert base.loc[base.fecha_objetivo.eq("2026-03-30"), "p50_kg"].sum() == 90.0

    def replay_sintetico(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        salida = panel.copy()
        salida["p50_kg"] = salida["p50_kg"] * 1.5
        salida["componentes"] = [{"fuente": "doble"}] * len(salida)
        return salida, pd.DataFrame()

    monkeypatch.setattr(service, "_cargar_fuentes", lambda: (actual, historico, 42, 901, emision))
    monkeypatch.setattr(service, "ejecutar_replay_hibrido_ocurrencia_v2", replay_sintetico)

    salida_facade, meta_facade = facade.construir_corrida()
    salida_service, meta_service = service.construir_corrida()

    pd.testing.assert_frame_equal(salida_facade, salida_service)
    assert meta_facade == meta_service
    assert len(salida_service) == len(futuro)
    assert not salida_service.duplicated(["campania", "lote_id", "fecha_objetivo"]).any()
    assert set(salida_service.modelo) == {service.NOMBRE_MODELO}
    assert set(salida_service.version_modelo) == {service.VERSION_MODELO}
    assert set(salida_service.fecha_objetivo) == {
        pd.Timestamp("2026-04-06"),
        pd.Timestamp("2026-04-13"),
    }

    base_v2, _ = service._construir_base(actual, historico, emision)
    base_v2["p50_kg"] *= 1.5
    v2_futuro = base_v2[base_v2.fecha_objetivo >= "2026-04-06"]
    suma_salida = salida_service.groupby(service.CLAVES_SEMANA, as_index=False).p50_kg.sum()
    suma_v2 = v2_futuro.groupby(service.CLAVES_SEMANA, as_index=False).p50_kg.sum()
    pd.testing.assert_frame_equal(suma_salida, suma_v2)
    assert meta_service["filas_base_semanal"] == 4
    assert meta_service["filas_salida_lote_pania"] == 3
    assert meta_service["semanas_futuras"] == 2
    assert meta_service["kg_macro_futuro"] == 230.0
    assert meta_service["kg_v2_futuro"] == 345.0


def test_dry_run_no_hace_escrituras(monkeypatch) -> None:
    meta = _meta_base()
    escrituras: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, *_args, **_kwargs):
            escrituras.append(("init",))

        def __getattr__(self, nombre):
            def registrar(*args, **kwargs):
                escrituras.append((nombre, args, kwargs))

            return registrar

    monkeypatch.setattr(service, "construir_corrida", lambda: (pd.DataFrame(), meta.copy()))
    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(
        service.settings,
        "postgres_dsn",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run no debe pedir DSN")),
    )

    assert facade.persistir(dry_run=True) == meta
    assert escrituras == []


def test_persistencia_conserva_orden_y_finaliza_succeeded(monkeypatch) -> None:
    predicciones = pd.DataFrame({"modelo": [service.NOMBRE_MODELO], "p50_kg": [10.0]})
    meta = _meta_base()
    llamadas: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, dsn):
            llamadas.append(("init", dsn))

        def crear_run(self, *args):
            llamadas.append(("crear_run", *args))
            return 903

        def guardar_predicciones(self, *args):
            llamadas.append(("guardar_predicciones", *args))

        def finalizar_run(self, *args):
            llamadas.append(("finalizar_run", *args))

    monkeypatch.setattr(service, "construir_corrida", lambda: (predicciones, meta.copy()))
    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")

    resultado = service.persistir()

    assert resultado["run_id"] == 903
    assert [llamada[0] for llamada in llamadas] == [
        "init",
        "crear_run",
        "guardar_predicciones",
        "finalizar_run",
    ]
    assert llamadas[-1] == ("finalizar_run", 903, "succeeded")


def test_fallo_de_escritura_finaliza_run_failed_y_repropaga(monkeypatch) -> None:
    meta = _meta_base()
    llamadas: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, *_args, **_kwargs):
            pass

        def crear_run(self, *_args):
            llamadas.append(("crear_run",))
            return 904

        def guardar_predicciones(self, *_args):
            llamadas.append(("guardar_predicciones",))
            raise RuntimeError("fallo sintético")

        def finalizar_run(self, *args):
            llamadas.append(("finalizar_run", *args))

    monkeypatch.setattr(service, "construir_corrida", lambda: (pd.DataFrame(), meta.copy()))
    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")

    with pytest.raises(RuntimeError, match="fallo sintético"):
        facade.persistir()

    assert llamadas == [
        ("crear_run",),
        ("guardar_predicciones",),
        ("finalizar_run", 904, "failed", "fallo sintético"),
    ]


def test_cli_conserva_argumento_dry_run_y_serializacion_json(monkeypatch, capsys) -> None:
    recibidos: list[bool] = []
    resultado = {"estado": "ok", "fecha": pd.Timestamp("2026-04-08")}

    monkeypatch.setattr(facade, "_argumentos", lambda: SimpleNamespace(dry_run=True))
    monkeypatch.setattr(
        facade,
        "persistir",
        lambda dry_run=False: (recibidos.append(dry_run), resultado)[1],
    )

    assert facade.main() is None
    assert recibidos == [True]
    assert json.loads(capsys.readouterr().out) == {
        "estado": "ok",
        "fecha": "2026-04-08 00:00:00",
    }


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
