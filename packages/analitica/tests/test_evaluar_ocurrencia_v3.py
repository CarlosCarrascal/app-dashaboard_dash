from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd

from analitica.scripts import evaluar_ocurrencia_v3 as facade
from analitica.servicios import evaluacion_ocurrencia_v3 as service
from analitica.servicios import replay

SCRIPT = Path(facade.__file__)


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha_objetivo": pd.to_datetime(
                ["2026-01-05", "2026-01-05", "2026-01-12", "2026-01-12"]
            ),
            "real_kg": [100.0, 40.0, 120.0, 60.0],
            "p50_kg": [90.0, 50.0, 110.0, 70.0],
        }
    )


def _assert_dicts_equal(left: dict, right: dict) -> None:
    assert left.keys() == right.keys()
    for key in left:
        if pd.isna(left[key]) and pd.isna(right[key]):
            continue
        assert left[key] == right[key], key


def test_fachada_conserva_aliases_identidad_y_firmas() -> None:
    nombres = (
        "cargar_datos",
        "backtest_macro_legacy_v1",
        "ejecutar_replay_hibrido_ocurrencia",
        "ejecutar_replay_hibrido_ocurrencia_v2",
        "ejecutar_replay_hibrido_ocurrencia_v3",
        "emisiones_completas",
        "_emisiones_completas",
        "metricas_pronostico",
        "normalizar_modelo",
        "_normalizar_modelo",
        "_metricas",
        "metricas",
        "evaluar",
        "evaluar_ocurrencia_v3",
        "ejecutar",
    )
    for nombre in nombres:
        alias = getattr(facade, nombre)
        implementacion = getattr(service, nombre)
        assert alias is implementacion, nombre
        if callable(alias):
            assert inspect.signature(alias) == inspect.signature(implementacion)

    assert facade.emisiones_completas is replay.emisiones_completas
    assert facade._emisiones_completas is replay.emisiones_completas
    assert facade.normalizar_modelo is replay.normalizar_modelo
    assert facade._normalizar_modelo is replay.normalizar_modelo


def test_metricas_fachada_y_servicio_conservan_paridad() -> None:
    _assert_dicts_equal(
        facade._metricas(_panel(), "Modelo"), service._metricas(_panel(), "Modelo")
    )
    assert facade._metricas(_panel(), "Modelo")["modelo"] == "Modelo"
    assert facade._metricas(_panel(), "Modelo")["n_semanas"] == 2


def test_evaluar_conserva_orden_modelos_y_parametros(monkeypatch) -> None:
    datos = object()
    emisiones = object()
    macro = _panel()
    v1 = _panel()
    v2 = _panel()
    v3 = _panel()
    llamadas: list[tuple] = []

    monkeypatch.setattr(
        service,
        "emisiones_completas",
        lambda datos_recibidos, campania: (
            llamadas.append(("emisiones", datos_recibidos, campania)) or emisiones
        ),
    )
    monkeypatch.setattr(
        service,
        "backtest_macro_legacy_v1",
        lambda datos_recibidos, emisiones_recibidas, **kwargs: (
            llamadas.append(("macro", datos_recibidos, emisiones_recibidas, kwargs))
            or (macro, "resumen")
        ),
    )
    monkeypatch.setattr(
        service,
        "normalizar_modelo",
        lambda tabla: llamadas.append(("normalizar", tabla)) or tabla,
    )
    for nombre, tabla in (
        ("ejecutar_replay_hibrido_ocurrencia", v1),
        ("ejecutar_replay_hibrido_ocurrencia_v2", v2),
        ("ejecutar_replay_hibrido_ocurrencia_v3", v3),
    ):
        monkeypatch.setattr(
            service,
            nombre,
            lambda tabla=tabla, nombre=nombre: (
                llamadas.append((nombre, tabla)) or (tabla, "resumen")
            ),
        )

    resultado = service.evaluar(datos, campania="C2027")

    assert list(resultado) == [
        "MacroLegacy_v1",
        "HibridoOcurrenciaOnline_v1",
        "HibridoOcurrenciaOnline_v2",
        "HibridoOcurrenciaOnline_v3",
    ]
    assert [llamada[0] for llamada in llamadas] == [
        "emisiones",
        "macro",
        "normalizar",
        "ejecutar_replay_hibrido_ocurrencia",
        "ejecutar_replay_hibrido_ocurrencia_v2",
        "ejecutar_replay_hibrido_ocurrencia_v3",
    ]
    assert llamadas[0] == ("emisiones", datos, "C2027")
    assert llamadas[1][1:] == (datos, emisiones, {
        "campania": "C2027",
        "horizonte_semanas": 1,
        "max_cortes": None,
    })
    assert resultado["MacroLegacy_v1"]["modelo"] == "MacroLegacy_v1"
    assert resultado["HibridoOcurrenciaOnline_v3"]["modelo"] == (
        "HibridoOcurrenciaOnline_v3"
    )


def test_fachada_cli_conserva_carga_campania_y_serializacion(monkeypatch, capsys) -> None:
    datos = object()
    esperado = {
        "MacroLegacy_v1": {"modelo": "MacroLegacy_v1", "n_semanas": 2},
        "HibridoOcurrenciaOnline_v3": {"modelo": "HibridoOcurrenciaOnline_v3", "n_semanas": 2},
    }
    llamadas: list[tuple] = []

    monkeypatch.setattr(
        facade,
        "cargar_datos",
        lambda origen: llamadas.append(("cargar_datos", origen)) or datos,
    )
    monkeypatch.setattr(
        facade,
        "evaluar",
        lambda datos_recibidos, campania: (
            llamadas.append(("evaluar", datos_recibidos, campania)) or esperado
        ),
    )
    monkeypatch.setattr(sys, "argv", ["evaluar_ocurrencia_v3", "--argumento-historico"])

    assert facade.main() is None
    assert llamadas == [("cargar_datos", "postgres"), ("evaluar", datos, "C2026")]
    assert json.loads(capsys.readouterr().out) == esperado


def test_fachada_es_compuerta_cli_y_servicio_no_depende_de_scripts() -> None:
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
