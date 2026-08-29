from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd

from analitica.scripts import build_expert_parameter_h1_panel as facade
from analitica.servicios import expert_parameter_h1_panel as service

ROOT = Path(__file__).resolve().parents[1]


def test_fachada_conserva_aliases_identidad_y_firmas() -> None:
    nombres = (
        "ROOT_DEFAULT",
        "SEMANAS_CERTIFICADAS",
        "construir",
        "ejecutar_proyeccion_semanal_dataframe",
        "leer_libro_operativo",
        "pd",
        "seleccionar_libros_parametros",
    )
    for nombre in nombres:
        alias = getattr(facade, nombre)
        implementacion = getattr(service, nombre)
        assert alias is implementacion, nombre
        if callable(alias):
            assert inspect.signature(alias) == inspect.signature(implementacion)


def test_servicio_y_fachada_conservan_paridad_asof_del_panel(monkeypatch) -> None:
    manifiesto = pd.DataFrame(
        [
            {
                "semana_emision": 25,
                "fundo_operativo": "Quri",
                "archivo_fuente": "ProySemanal_25_Quri.xlsm",
                "ruta_fuente": "datos/Quri.xlsm",
                "sha256_fuente": "hash-quri",
                "variante": "base",
            },
            {
                "semana_emision": 24,
                "fundo_operativo": "Arena",
                "archivo_fuente": "ProySemanal_24_Arena.xlsm",
                "ruta_fuente": "datos/Arena.xlsm",
                "sha256_fuente": "hash-arena",
                "variante": "promovida",
            },
        ]
    )
    faltantes = pd.DataFrame([{"semana_emision": 26, "fundo_operativo": "Kawsay"}])
    motores = {
        "Arena": pd.DataFrame(
            {
                "FeCos": [
                    pd.Timestamp.fromisocalendar(2026, 25, 1),
                    pd.Timestamp.fromisocalendar(2026, 25, 2),
                    pd.Timestamp.fromisocalendar(2026, 26, 1),
                ],
                "Kg": [10.0, 5.0, 999.0],
            }
        ),
        "Quri": pd.DataFrame(
            {
                "FeCos": [pd.Timestamp.fromisocalendar(2026, 26, 1)],
                "Kg": [20.0],
            }
        ),
    }

    monkeypatch.setattr(
        service,
        "seleccionar_libros_parametros",
        lambda _root, *, semanas: (manifiesto, faltantes),
    )
    monkeypatch.setattr(
        service,
        "leer_libro_operativo",
        lambda _ruta: (pd.DataFrame(), pd.DataFrame(), pd.DataFrame()),
    )
    monkeypatch.setattr(
        service,
        "ejecutar_proyeccion_semanal_dataframe",
        lambda *, df_parametros, df_panel, campana, fundo_nombre: motores[fundo_nombre],
    )

    tabla_servicio, metadatos_servicio = service.construir(
        root=Path("proyecciones"), campania="C2026", semanas_fuente=(24, 25, 26)
    )
    tabla_fachada, metadatos_fachada = facade.construir(
        root=Path("proyecciones"), campania="C2026", semanas_fuente=(24, 25, 26)
    )

    pd.testing.assert_frame_equal(tabla_fachada, tabla_servicio)
    assert metadatos_fachada == metadatos_servicio
    assert tabla_servicio[["semana_emision", "semana_objetivo", "fundo_operativo"]].to_dict(
        "records"
    ) == [
        {"semana_emision": 24, "semana_objetivo": 25, "fundo_operativo": "Arena"},
        {"semana_emision": 25, "semana_objetivo": 26, "fundo_operativo": "Quri"},
    ]
    assert tabla_servicio.expert_kg.tolist() == [15.0, 20.0]
    assert tabla_servicio.n_filas_motor.tolist() == [2, 1]
    assert metadatos_servicio["publicable"] is False
    assert metadatos_servicio["faltantes"] == faltantes.to_dict("records")


def test_fachada_cli_conserva_argumentos_salida_serializacion_y_rutas(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    root = tmp_path / "proyecciones"
    salida = tmp_path / "resultado" / "panel.parquet"
    tabla = pd.DataFrame({"expert_kg": [12.5], "fundo_operativo": ["Arena"]})
    metadatos = {
        "schema": "expert-parameter-h1-cache-v1",
        "campania": "C2027",
        "descripcion": "parámetros canónicos S disponibles en S -> objetivo S+1",
        "semanas_certificadas": [28, 31],
        "n_filas": 1,
        "faltantes": [],
        "errores": [],
        "publicable": False,
    }
    recibidos: dict[str, object] = {}

    def construir_falso(
        *, root: Path, campania: str, semanas_fuente: tuple[int, ...]
    ) -> tuple[pd.DataFrame, dict[str, object]]:
        recibidos.update(root=root, campania=campania, semanas_fuente=semanas_fuente)
        return tabla, metadatos

    monkeypatch.setattr(facade, "construir", construir_falso)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_expert_parameter_h1_panel",
            "--root",
            str(root),
            "--campania",
            "C2027",
            "--semanas",
            "28",
            "31",
            "--salida",
            str(salida),
        ],
    )

    assert facade.main() == 0
    assert recibidos == {"root": root, "campania": "C2027", "semanas_fuente": (28, 31)}
    pd.testing.assert_frame_equal(pd.read_parquet(salida), tabla)
    assert json.loads(salida.with_suffix(".json").read_text(encoding="utf-8")) == metadatos
    salida_consola = capsys.readouterr().out
    assert '"schema": "expert-parameter-h1-cache-v1"' in salida_consola
    assert '"n_faltantes": 0' in salida_consola
    assert '"errores": []' in salida_consola


def test_fachada_es_delgada_y_servicio_no_depende_de_scripts() -> None:
    ruta_fachada = Path(facade.__file__)
    arbol_fachada = ast.parse(ruta_fachada.read_text(encoding="utf-8"), filename=str(ruta_fachada))
    assert [
        nodo.name
        for nodo in arbol_fachada.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ] == ["main"]
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

    ruta_servicio = Path(service.__file__)
    arbol_servicio = ast.parse(
        ruta_servicio.read_text(encoding="utf-8"), filename=str(ruta_servicio)
    )
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
        for nodo in ast.walk(arbol_servicio)
    )
