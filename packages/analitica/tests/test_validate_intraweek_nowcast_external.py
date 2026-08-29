from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from analitica.scripts import validate_intraweek_nowcast_external as fachada
from analitica.servicios import validate_intraweek_nowcast_external as servicio

SCRIPT = Path(fachada.__file__)


def test_fachada_conserva_aliases_publicos_privados_y_firmas() -> None:
    nombres = (
        "ACCESS_DEFAULT",
        "CALIBRACION_CONGELADA",
        "CONFIGURACION_CONGELADA",
        "Configuracion",
        "R09_ACCESS_DEFAULT",
        "RUNS_CERTIFICADOS",
        "calibrar_residuo_online",
        "comparacion_pareada",
        "ejecutar",
        "escribir_json_reproducible",
        "evaluar_campania",
        "leer_diario",
        "leer_macro_h1",
        "leer_reales_r09_fundo",
        "metricas",
        "pd",
        "predecir",
        "_construir_contrato",
        "_predecir_fundos",
        "_resumen_fundos",
    )
    for nombre in nombres:
        alias = getattr(fachada, nombre)
        implementacion = getattr(servicio, nombre)
        assert alias is implementacion
        if callable(alias):
            assert inspect.signature(alias) == inspect.signature(implementacion)


def _datos_fundos() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fecha_1 = pd.Timestamp("2026-01-05")
    fecha_2 = pd.Timestamp("2026-01-12")
    semanal = pd.DataFrame(
        [
            {
                "fecha_objetivo": fecha,
                "semana_objetivo": semana,
                "fundo_operativo": fundo,
                "real_kg": real,
                "montue_kg": montue,
                "fecha_max": fecha + pd.Timedelta(6, unit="D"),
            }
            for fecha, semana, valores in (
                (fecha_1, 1, (("Arena", 100.0, 40.0), ("Quri", 50.0, 20.0))),
                (fecha_2, 2, (("Arena", 120.0, 48.0), ("Quri", 60.0, 24.0))),
            )
            for fundo, real, montue in valores
        ]
    )
    macro = pd.DataFrame(
        [
            {"fecha_objetivo": fecha, "fundo_operativo": fundo, "macro_kg": macro_kg}
            for fecha, valores in (
                (fecha_1, (("Arena", 100.0), ("Quri", 50.0))),
                (fecha_2, (("Arena", 150.0), ("Quri", 75.0))),
            )
            for fundo, macro_kg in valores
        ]
    )
    final = pd.DataFrame(
        {
            "fecha_objetivo": [fecha_1, fecha_2],
            "semana_objetivo": [1, 2],
            "semana_emision": [0, 1],
            "escala_residual": [1.0, 0.9],
        }
    )
    r09 = pd.DataFrame(
        {
            "semana_emision": [0, 1],
            "semana_objetivo": [1, 2],
            "fundo_operativo": ["Arena", "Arena"],
            "r09_kg": [95.0, 140.0],
        }
    )
    return final, semanal, macro, r09


def test_servicio_y_fachada_conservan_paridad_por_fundo_y_as_of(monkeypatch) -> None:
    final, semanal, macro, r09 = _datos_fundos()
    monkeypatch.setattr(servicio, "leer_reales_r09_fundo", lambda access, campania: (None, r09))

    obtenido = fachada._predecir_fundos(
        final,
        semanal,
        macro,
        campania="C2026",
        r09_access=Path("r09.accdb"),
    )
    esperado = servicio._predecir_fundos(
        final,
        semanal,
        macro,
        campania="C2026",
        r09_access=Path("r09.accdb"),
    )
    assert_frame_equal(obtenido, esperado)

    mutado = semanal.copy()
    mutado.loc[mutado.fecha_objetivo.eq(pd.Timestamp("2026-01-12")), "real_kg"] *= 100.0
    repetido = servicio._predecir_fundos(
        final,
        mutado,
        macro,
        campania="C2026",
        r09_access=Path("r09.accdb"),
    )
    columnas = ["fecha_objetivo", "fundo_operativo", "pace_kg", "candidate_kg"]
    assert_frame_equal(obtenido[columnas], repetido[columnas])


def test_fachada_cli_conserva_argumentos_serializacion_y_ruta(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    access = tmp_path / "entrada.accdb"
    r09_access = tmp_path / "r09.accdb"
    salida = tmp_path / "subdir" / "resultado.json"
    resultado = {
        "schema": "validate-intraweek-nowcast-external-v1",
        "rutas": {"access": str(access), "r09": str(r09_access)},
        "n": 3,
    }
    llamadas: list[tuple[Path, Path]] = []
    serializaciones: list[tuple[dict[str, object], Path]] = []

    def fake_ejecutar(*, access: Path, r09_access: Path) -> dict[str, object]:
        llamadas.append((access, r09_access))
        return resultado

    def fake_escribir(valor: dict[str, object], ruta: Path) -> None:
        serializaciones.append((valor, ruta))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(valor), encoding="utf-8")

    monkeypatch.setattr(fachada, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(fachada, "escribir_json_reproducible", fake_escribir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_intraweek_nowcast_external",
            "--access",
            str(access),
            "--r09-access",
            str(r09_access),
            "--salida",
            str(salida),
        ],
    )

    assert fachada.main() == 0
    assert llamadas == [(access, r09_access)]
    assert serializaciones == [(resultado, salida)]
    assert json.loads(salida.read_text(encoding="utf-8")) == resultado
    assert json.loads(capsys.readouterr().out) == resultado


def test_script_es_fachada_ast_y_servicio_no_depende_de_scripts() -> None:
    arbol_script = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    assert [
        nodo.name
        for nodo in arbol_script.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ] == ["main"]
    assert not [
        nodo
        for nodo in ast.walk(arbol_script)
        if isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
    ]
    assert not [
        nodo
        for nodo in ast.walk(arbol_script)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
    ]

    service_path = Path(servicio.__file__)
    arbol_servicio = ast.parse(service_path.read_text(encoding="utf-8"), filename=str(service_path))
    assert not [
        nodo
        for nodo in ast.walk(arbol_servicio)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
    ]
