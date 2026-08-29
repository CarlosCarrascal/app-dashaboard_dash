from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd

from analitica.scripts import screening_lagged_parameters_horizons as fachada
from analitica.servicios import lagged_parameters_horizons as servicio
from analitica.servicios import parametros_replay

ROOT = Path(__file__).resolve().parents[1]


def test_fachada_conserva_aliases_identidad_y_firmas() -> None:
    nombres = (
        "_libros",
        "ACCESS_DEFAULT",
        "ROOT_DEFAULT",
        "cargar_reales_y_r09",
        "ejecutar",
        "ejecutar_proyeccion_semanal_dataframe",
        "escribir_json_reproducible",
        "leer_libro_operativo",
        "pd",
        "seleccionar_libros_parametros",
    )
    for nombre in nombres:
        alias = getattr(fachada, nombre)
        implementacion = getattr(servicio, nombre)
        assert alias is implementacion
        if callable(alias):
            assert inspect.signature(alias) == inspect.signature(implementacion)

    assert servicio.ACCESS_DEFAULT is parametros_replay.ACCESS_DEFAULT
    assert servicio.ROOT_DEFAULT is parametros_replay.ROOT_DEFAULT
    assert servicio.cargar_reales_y_r09 is parametros_replay.cargar_reales_y_r09
    assert inspect.signature(fachada.ejecutar) == inspect.signature(servicio.ejecutar)


def test_servicio_conserva_paridad_de_agregacion_y_filtros_asof(monkeypatch) -> None:
    motor = pd.DataFrame(
        {
            "FeCos": [
                pd.Timestamp.fromisocalendar(2026, 27, 1),
                pd.Timestamp.fromisocalendar(2026, 28, 1),
                pd.Timestamp.fromisocalendar(2026, 30, 1),
                pd.Timestamp.fromisocalendar(2026, 32, 1),
            ],
            "Kg": [10.0, 20.0, 40.0, 80.0],
        }
    )
    llamadas: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        servicio,
        "cargar_reales_y_r09",
        lambda _access, _campania: (
            {27: 11.0, 28: 18.0, 30: 45.0},
            {(26, 27): 9.0, (26, 28): 19.0, (26, 30): 44.0},
        ),
    )
    monkeypatch.setattr(servicio, "_libros", lambda _root, _semana: {"Fundo": Path("S25.xlsx")})
    monkeypatch.setattr(
        servicio,
        "leer_libro_operativo",
        lambda _ruta: (pd.DataFrame(), pd.DataFrame(), None),
    )

    def proyectar(_parametros, _panel, *, campana: str, fundo_nombre: str) -> pd.DataFrame:
        llamadas.append((campana, fundo_nombre, "proyeccion"))
        return motor.copy()

    monkeypatch.setattr(servicio, "ejecutar_proyeccion_semanal_dataframe", proyectar)

    resultado_servicio = servicio.ejecutar(
        root=Path("proyecciones"),
        access=Path("entrada.accdb"),
        campania="C2026",
        emisiones=(26,),
        ultima_semana_cerrada=31,
    )
    resultado_fachada = fachada.ejecutar(
        root=Path("proyecciones"),
        access=Path("entrada.accdb"),
        campania="C2026",
        emisiones=(26,),
        ultima_semana_cerrada=31,
    )

    assert json.dumps(resultado_fachada, sort_keys=True) == json.dumps(
        resultado_servicio, sort_keys=True
    )
    assert llamadas == [("C2026", "Fundo", "proyeccion")] * 2
    assert resultado_servicio["schema"] == "screening-lagged-parameters-horizons-v1"
    assert resultado_servicio["publicable"] is False
    detalle = resultado_servicio["detalle"]
    assert len(detalle) == 3
    assert detalle[0] == {
        "campania": "C2026",
        "semana_emision": 26,
        "semana_parametros": 25,
        "semana_objetivo": 27,
        "horizonte": 1,
        "real_kg": 11.0,
        "lagged_kg": 10.0,
        "r09_kg": 9.0,
    }
    assert [(fila["semana_objetivo"], fila["horizonte"]) for fila in detalle] == [
        (27, 1),
        (28, 2),
        (30, 4),
    ]
    assert detalle[1]["r09_kg"] == 19.0
    assert detalle[2]["r09_kg"] == 44.0


def test_fachada_cli_conserva_argumentos_salida_serializacion_y_ruta(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    root = tmp_path / "proyecciones"
    access = tmp_path / "entrada.accdb"
    salida = tmp_path / "resultado" / "screening.json"
    esperado = {"resumen": [{"horizonte": "todos", "n": 1}], "detalle": []}
    recibidos: dict[str, object] = {}

    def ejecutar_falso(
        *,
        root: Path,
        access: Path,
        campania: str,
        emisiones: tuple[int, ...],
        ultima_semana_cerrada: int,
    ) -> dict[str, object]:
        recibidos.update(
            root=root,
            access=access,
            campania=campania,
            emisiones=emisiones,
            ultima_semana_cerrada=ultima_semana_cerrada,
        )
        return esperado

    def escribir_falso(resultado: dict[str, object], ruta: Path) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(resultado), encoding="utf-8")

    monkeypatch.setattr(fachada, "ejecutar", ejecutar_falso)
    monkeypatch.setattr(fachada, "escribir_json_reproducible", escribir_falso)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screening_lagged_parameters_horizons",
            "--root",
            str(root),
            "--access",
            str(access),
            "--campania",
            "C2025",
            "--emisiones",
            "26",
            "29",
            "--ultima-semana-cerrada",
            "33",
            "--salida",
            str(salida),
        ],
    )

    assert fachada.main() == 0
    assert recibidos == {
        "root": root,
        "access": access,
        "campania": "C2025",
        "emisiones": (26, 29),
        "ultima_semana_cerrada": 33,
    }
    assert json.loads(salida.read_text(encoding="utf-8")) == esperado
    assert json.loads(capsys.readouterr().out) == esperado["resumen"]


def test_fachada_es_delgada_y_servicio_no_importa_scripts() -> None:
    script_ast = ast.parse(
        (ROOT / "scripts" / "screening_lagged_parameters_horizons.py").read_text(encoding="utf-8")
    )
    assert [
        nodo.name
        for nodo in script_ast.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ] == ["main"]
    assert not any(
        isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
        for nodo in ast.walk(script_ast)
    )
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
        for nodo in ast.walk(script_ast)
    )

    service_ast = ast.parse(Path(servicio.__file__).read_text(encoding="utf-8"))
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
        for nodo in ast.walk(service_ast)
    )
