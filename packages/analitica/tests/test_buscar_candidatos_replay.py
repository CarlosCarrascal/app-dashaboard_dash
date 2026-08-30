from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.servicios import buscar_candidatos_replay as servicio
from analitica.interfaces.scripts import buscar_candidatos_replay as fachada

SCRIPT = Path(fachada.__file__)


def test_fachada_conserva_aliases_publicos_privados_identidad_y_firmas() -> None:
    nombres = (
        "_argumentos",
        "_leer",
        "ejecutar",
        "escribir_json_reproducible",
        "postgres_dsn",
        "preparar_panel",
        "successive_halving",
    )
    for nombre in nombres:
        alias = getattr(fachada, nombre)
        implementacion = getattr(servicio, nombre)
        assert alias is implementacion, nombre
        if callable(alias):
            assert inspect.signature(alias) == inspect.signature(implementacion)

    for nombre in ("Path", "argparse", "pd", "psycopg"):
        assert getattr(fachada, nombre) is getattr(servicio, nombre)


def test_servicio_y_fachada_conservan_paridad_de_orquestacion(monkeypatch) -> None:
    datos = pd.DataFrame({"campania": ["C2025"], "real_kg": [10.0]})
    panel = pd.DataFrame({"modelo": ["MacroLegacy_v1"], "p50_kg": [11.0]})
    resultado = {
        "mejor": {"modelo": "MacroLegacy_v1", "valor": np.float64(11.0)},
        "decision": {"publicable": False},
        "escenarios": ["fijo", "online"],
    }
    llamadas: list[object] = []

    def leer_falso() -> pd.DataFrame:
        llamadas.append("leer")
        return datos

    def preparar_falso(tabla: pd.DataFrame) -> pd.DataFrame:
        llamadas.append(("preparar", tabla))
        return panel

    def halving_falso(tabla: pd.DataFrame) -> dict[str, object]:
        llamadas.append(("halving", tabla))
        return resultado

    monkeypatch.setattr(servicio, "_leer", leer_falso)
    monkeypatch.setattr(servicio, "preparar_panel", preparar_falso)
    monkeypatch.setattr(servicio, "successive_halving", halving_falso)
    resultado_servicio = servicio.ejecutar()
    resultado_fachada = fachada.ejecutar()

    assert resultado_fachada == resultado_servicio == resultado
    assert [llamada[0] if isinstance(llamada, tuple) else llamada for llamada in llamadas] == [
        "leer",
        "preparar",
        "halving",
        "leer",
        "preparar",
        "halving",
    ]
    pd.testing.assert_frame_equal(llamadas[1][1], datos)  # type: ignore[index]
    pd.testing.assert_frame_equal(llamadas[2][1], panel)  # type: ignore[index]


def test_fachada_cli_conserva_argumentos_serializacion_y_ruta(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    salida = tmp_path / "resultado" / "candidatos.json"
    resultado = {
        "mejor": {"valor": np.int64(3)},
        "decision": {"publicable": False},
    }
    llamadas: list[tuple[object, Path]] = []

    monkeypatch.setattr(fachada, "ejecutar", lambda: resultado)

    def escribir_falso(valor: object, ruta: Path) -> None:
        llamadas.append((valor, ruta))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(valor, default=str), encoding="utf-8")

    monkeypatch.setattr(fachada, "escribir_json_reproducible", escribir_falso)
    monkeypatch.setattr(
        sys,
        "argv",
        ["buscar_candidatos_replay", "--salida", str(salida)],
    )

    assert fachada.main() == 0
    assert llamadas == [(resultado, salida)]
    assert json.loads(salida.read_text(encoding="utf-8")) == {
        "mejor": {"valor": "3"},
        "decision": {"publicable": False},
    }
    salida_consola = capsys.readouterr().out
    assert '"valor": "3"' in salida_consola
    assert '"publicable": false' in salida_consola


def test_fachada_es_delgada_y_servicio_no_importa_scripts() -> None:
    arbol_fachada = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
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
        and nodo.module.startswith("analitica.interfaces.scripts.")
        for nodo in ast.walk(arbol_fachada)
    )

    arbol_servicio = ast.parse(
        Path(servicio.__file__).read_text(encoding="utf-8"), filename=str(servicio.__file__)
    )
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
        for nodo in ast.walk(arbol_servicio)
    )


def test_leer_conserva_filtros_asof_y_serializa_columnas(monkeypatch) -> None:
    class Cursor:
        description = [type("Descripcion", (), {"name": nombre}) for nombre in ("a", "b")]

        def __init__(self) -> None:
            self.consulta = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def execute(self, consulta: str) -> None:
            self.consulta = consulta

        def fetchall(self) -> list[tuple[int, str]]:
            return [(1, "C2025")]

    class Conexion:
        def __init__(self, cursor: Cursor) -> None:
            self.cursor_obj = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def cursor(self) -> Cursor:
            return self.cursor_obj

    cursor = Cursor()
    monkeypatch.setattr(servicio, "postgres_dsn", lambda: "postgresql://test")
    monkeypatch.setattr(servicio.psycopg, "connect", lambda _dsn: Conexion(cursor))

    salida = servicio._leer()

    assert salida.to_dict("records") == [{"a": 1, "b": "C2025"}]
    assert "r.estado = 'approved' AND r.activo AND r.uso = 'historico'" in cursor.consulta
    assert "r.modelo IN ('MacroLegacy_v1', 'HibridoOcurrenciaOnline_v2')" in cursor.consulta
    assert "r.campania IN ('C2025', 'C2026')" in cursor.consulta
    assert "p.horizonte_semanas = 1" in cursor.consulta
    assert "p.real_kg IS NOT NULL" in cursor.consulta
    assert "COALESCE(p.origen_emision, p.fecha_emision)" in cursor.consulta
    assert "< date_trunc('week', p.fecha_objetivo)::date" in cursor.consulta
