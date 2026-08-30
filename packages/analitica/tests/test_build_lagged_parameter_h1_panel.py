from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd

from analitica.aplicacion.servicios import lagged_parameter_h1_panel as service
from analitica.interfaces.scripts import build_lagged_parameter_h1_panel as facade

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "interfaces" / "scripts" / "build_lagged_parameter_h1_panel.py"


def test_fachada_conserva_aliases_identidad_y_firmas() -> None:
    for nombre in (
        "ROOT_DEFAULT",
        "pd",
        "ejecutar_proyeccion_semanal_dataframe",
        "seleccionar_libros_parametros",
        "leer_libro_operativo",
        "construir",
    ):
        assert getattr(facade, nombre) is getattr(service, nombre)

    assert inspect.signature(facade.construir) == inspect.signature(service.construir)


def test_construir_es_paritario_y_conserva_el_contrato_as_of(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "proyecciones"
    ruta = root / "ProyeccionSemanal_24" / "ProySemanal_24_Arena.xlsm"
    manifiesto = pd.DataFrame(
        [
            {
                "semana_emision": 24,
                "fundo_operativo": "Arena",
                "archivo_fuente": ruta.name,
                "ruta_fuente": str(ruta),
                "sha256_fuente": "abc123",
                "variante": "base",
            }
        ]
    )
    faltantes = pd.DataFrame(
        [{"semana_emision": 24, "fundo": "Quri", "estado": "sin_datos"}]
    )
    llamadas: list[tuple[Path, str, str]] = []

    def fake_seleccionar(
        recibido: Path, *, semanas: tuple[int, ...]
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        assert recibido == root
        assert semanas == (24,)
        return manifiesto, faltantes

    def fake_leer(recibido: Path) -> tuple[pd.DataFrame, pd.DataFrame, object]:
        assert recibido == ruta
        return pd.DataFrame({"parametro": [1]}), pd.DataFrame({"panel": [2]}), object()

    def fake_motor(
        *, df_parametros: pd.DataFrame, df_panel: pd.DataFrame, campana: str, fundo_nombre: str
    ) -> pd.DataFrame:
        assert list(df_parametros.columns) == ["parametro"]
        assert list(df_panel.columns) == ["panel"]
        llamadas.append((Path(str(ruta)), campana, fundo_nombre))
        return pd.DataFrame(
            {
                "FeCos": [
                    pd.Timestamp.fromisocalendar(2026, 26, 1),
                    pd.Timestamp.fromisocalendar(2026, 27, 1),
                ],
                "Kg": [123.5, 999.0],
            }
        )

    monkeypatch.setattr(service, "seleccionar_libros_parametros", fake_seleccionar)
    monkeypatch.setattr(service, "leer_libro_operativo", fake_leer)
    monkeypatch.setattr(service, "ejecutar_proyeccion_semanal_dataframe", fake_motor)

    tabla_facade, metadata_facade = facade.construir(
        root=root, campania="C2026", semanas_fuente=(24,)
    )
    tabla_service, metadata_service = service.construir(
        root=root, campania="C2026", semanas_fuente=(24,)
    )

    pd.testing.assert_frame_equal(tabla_facade, tabla_service)
    assert metadata_facade == metadata_service
    assert tabla_facade.to_dict("records") == [
        {
            "campania": "C2026",
            "semana_parametros": 24,
            "semana_emision": 25,
            "semana_objetivo": 26,
            "horizonte": 1,
            "fundo_operativo": "Arena",
            "lagged_kg": 123.5,
            "n_filas_motor": 1,
            "archivo_fuente": ruta.name,
            "ruta_fuente": str(ruta),
            "sha256_fuente": "abc123",
            "variante": "base",
        }
    ]
    assert metadata_facade == {
        "schema": "lagged-parameter-h1-cache-v1",
        "campania": "C2026",
        "descripcion": "S-1 parámetros canónicos -> emisión S -> objetivo S+1",
        "n_filas": 1,
        "semanas_parametros": [24],
        "faltantes": faltantes.to_dict("records"),
        "errores": [],
        "publicable": False,
    }
    assert llamadas == [(ruta, "C2026", "Arena"), (ruta, "C2026", "Arena")]


def test_fachada_cli_conserva_argumentos_salida_serializacion_y_rutas(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    root = tmp_path / "proyecciones"
    salida = tmp_path / "resultado" / "panel.parquet"
    tabla = pd.DataFrame({"semana_objetivo": [26], "lagged_kg": [123.5]})
    metadata = {
        "schema": "lagged-parameter-h1-cache-v1",
        "campania": "C2027",
        "n_filas": 1,
        "faltantes": [],
        "errores": [],
        "publicable": False,
    }
    llamadas: list[tuple[Path, str, tuple[int, ...]]] = []

    def fake_construir(
        *, root: Path, campania: str, semanas_fuente: tuple[int, ...]
    ) -> tuple[pd.DataFrame, dict[str, object]]:
        llamadas.append((root, campania, semanas_fuente))
        return tabla, metadata

    monkeypatch.setattr(facade, "construir", fake_construir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_lagged_parameter_h1_panel",
            "--root",
            str(root),
            "--campania",
            "C2027",
            "--desde",
            "24",
            "--hasta",
            "26",
            "--salida",
            str(salida),
        ],
    )

    assert facade.main() == 0
    assert llamadas == [(root, "C2027", (24, 25, 26))]
    pd.testing.assert_frame_equal(pd.read_parquet(salida), tabla)
    assert json.loads(salida.with_suffix(".json").read_text(encoding="utf-8")) == metadata
    assert '"schema": "lagged-parameter-h1-cache-v1"' in capsys.readouterr().out


def test_script_es_fachada_cli_y_no_importa_opcionales_en_carga() -> None:
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

    imports = [
        alias.name.split(".", maxsplit=1)[0]
        for nodo in ast.walk(ast.parse(Path(service.__file__).read_text(encoding="utf-8")))
        if isinstance(nodo, ast.Import)
        for alias in nodo.names
    ]
    imported_from = [
        alias.name.split(".", maxsplit=1)[0]
        for nodo in ast.walk(ast.parse(Path(service.__file__).read_text(encoding="utf-8")))
        if isinstance(nodo, ast.ImportFrom)
        for alias in nodo.names
    ]
    assert "pyodbc" not in imports + imported_from
    assert "python_calamine" not in imports + imported_from

    service_imports = ast.walk(ast.parse(Path(service.__file__).read_text(encoding="utf-8")))
    assert not [
        nodo
        for nodo in service_imports
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
    ]
