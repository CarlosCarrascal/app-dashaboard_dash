from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from analitica.scripts import ver_comparaciones as fachada
from analitica.servicios import ver_comparaciones as servicio

NOMBRES_COMPATIBLES = (
    "ACCDB_PATH",
    "PROY_FOLDER",
    "tabla_matriz_six",
    "tabla_real_vs_modelos",
    "tabla_replicacion",
    "tabla_versiones_access",
    "argparse",
    "os",
    "pd",
    "postgres_dsn",
    "psycopg",
    "sys",
)


@pytest.mark.parametrize("nombre", NOMBRES_COMPATIBLES)
def test_fachada_conserva_aliases_historicos_y_firmas(nombre: str) -> None:
    alias = getattr(fachada, nombre)
    implementacion = getattr(servicio, nombre)
    assert alias is implementacion
    if callable(alias):
        assert inspect.signature(alias) == inspect.signature(implementacion)


def test_fachada_conserva_despacho_cli_historico(monkeypatch, capsys) -> None:
    llamadas: list[object] = []
    monkeypatch.setattr(fachada, "tabla_real_vs_modelos", lambda: llamadas.append("real"))
    monkeypatch.setattr(fachada, "tabla_replicacion", lambda semana: llamadas.append(semana))
    monkeypatch.setattr(fachada, "tabla_matriz_six", lambda: llamadas.append("six"))
    monkeypatch.setattr(fachada, "tabla_versiones_access", lambda: llamadas.append("versiones"))
    monkeypatch.setattr(sys, "argv", ["ver_comparaciones", "--vista", "todas"])

    assert fachada.main() is None
    assert llamadas == ["real", 33, 32, "six", "versiones"]
    assert capsys.readouterr().out == "\n\n\n\n"


def test_tabla_real_conserva_consulta_columnas_y_etiquetas(monkeypatch, capsys) -> None:
    consultas: list[str] = []

    class ConexionAccess:
        def close(self) -> None:
            pass

    class ConexionPostgres:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

    monkeypatch.setitem(
        sys.modules,
        "pyodbc",
        SimpleNamespace(connect=lambda cadena: ConexionAccess()),
    )
    monkeypatch.setattr(servicio, "postgres_dsn", lambda: "postgresql://prueba")
    monkeypatch.setattr(
        servicio.psycopg,
        "connect",
        lambda dsn: ConexionPostgres(),
    )

    def read_sql(query: str, _conexion) -> pd.DataFrame:
        consultas.append(query)
        if "H01_ProdHistorica" in query:
            return pd.DataFrame({"Semana": [25, 26], "Real_Kg": [100.0, 120.0]})
        return pd.DataFrame({"Semana": [25, 26], "Agronomo_R09_Kg": [90.0, 132.0]})

    def read_sql_query(query: str, _conexion) -> pd.DataFrame:
        consultas.append(query)
        return pd.DataFrame({"Semana": [25, 26], "Modelo_Python_Kg": [95.0, 110.0]})

    monkeypatch.setattr(servicio.pd, "read_sql", read_sql)
    monkeypatch.setattr(servicio.pd, "read_sql_query", read_sql_query)

    servicio.tabla_real_vs_modelos()
    salida = capsys.readouterr().out

    assert (
        "COMPARATIVO: COSECHA REAL vs. PRONOSTICO AGRONOMO (R09) vs. MODELO AUTONOMO PYTHON"
        in salida
    )
    assert "Cosecha Real (kg)" in salida
    assert "Agronomo R09 (kg)" in salida
    assert "Modelo Python (kg)" in salida
    assert "Error Agronomo" in salida
    assert "Error Python" in salida
    assert "Sem 25" in salida
    assert "-10.00%" in salida
    assert consultas[0].splitlines()[1].strip() == "SELECT Semana, Sum(KG) as Real_Kg"
    assert "Version='S' & CStr(Sem - 1)" in consultas[1]
    assert "r.modelo = 'HibridoOcurrenciaOnline_v2'" in consultas[2]
    assert "r.uso = 'historico'" in consultas[2]
    assert "r.estado = 'approved'" in consultas[2]
    assert "p.horizonte_semanas = 1" in consultas[2]
    assert '"Semana"' in consultas[2]
    assert '"Modelo_Python_Kg"' in consultas[2]


def test_tablas_access_conservan_versiones_orden_y_columnas(monkeypatch, capsys) -> None:
    class ConexionAccess:
        def close(self) -> None:
            pass

    consultas: list[str] = []

    monkeypatch.setitem(
        sys.modules,
        "pyodbc",
        SimpleNamespace(connect=lambda cadena: ConexionAccess()),
    )

    def read_sql(query: str, _conexion) -> pd.DataFrame:
        consultas.append(query)
        if "KilosForecast" in query:
            return pd.DataFrame(
                {
                    "Version": ["S28", "S28", "S29", "S29"],
                    "SemanaDestino": [28, 29, 28, 29],
                    "KilosForecast": [1000.0, 2000.0, 1100.0, 2100.0],
                }
            )
        return pd.DataFrame(
            {"SemanaDestino": [28, 29], "KilosReales": [900.0, 1900.0]}
        )

    monkeypatch.setattr(servicio.pd, "read_sql", read_sql)
    servicio.tabla_matriz_six()
    matriz = capsys.readouterr().out

    assert "MATRIZ SIX: EVOLUCION Y VARIACIONES DEL PRONOSTICO RODANTE (ACCESS R09)" in matriz
    assert "Sem 28" in matriz and "1.0k" in matriz and "0.9k" in matriz
    assert "Cifras expresadas en miles de kilogramos ('k kg')." in matriz
    assert "'S28', 'S29', 'S30', 'S31'" in consultas[0]
    assert "'S32', 'S33', 'S34', 'S35'" in consultas[0]
    assert "Semana as SemanaDestino, Sum(KG) as KilosReales" in consultas[1]

    consultas.clear()
    monkeypatch.setattr(
        servicio.pd,
        "read_sql",
        lambda query, _conexion: (
            consultas.append(query)
            or pd.DataFrame(
                {
                    "Version": ["S10", "S2", "S1"],
                    "TotalFilas": [10, 2, 1],
                    "SemMin": [10, 2, 1],
                    "SemMax": [12, 4, 1],
                    "SemanasProyectadas": [3, 3, 1],
                    "FechaMin": ["2026-01-01"] * 3,
                    "FechaMax": ["2026-01-15"] * 3,
                    "TotalKg": [10000.0, 2000.0, 500.0],
                }
            )
        ),
    )
    servicio.tabla_versiones_access()
    versiones = capsys.readouterr().out

    assert (
        "TODAS LAS VERSIONES OFICIALES EN ACCESS [R09_Forecast_Semanal] (Campaña C2026)"
        in versiones
    )
    assert versiones.index("S1") < versiones.index("S2") < versiones.index("S10")
    assert "Horizonte" in versiones
    assert "Fechas" in versiones
    assert "Total Filas" in versiones
    assert "Total Kg Proyectados" in versiones
    assert "WHERE Campaña='C2026'" in consultas[0]
    assert "GROUP BY Version" in consultas[0]


def test_fachada_es_delgada_y_dependencias_opcionales_no_se_cargan_en_importacion() -> None:
    facade_tree = ast.parse(Path(fachada.__file__).read_text(encoding="utf-8"))
    assert [
        node.name
        for node in facade_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ] == ["main"]
    assert not [
        node
        for node in ast.walk(facade_tree)
        if isinstance(node, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
    ]
    assert not [
        node
        for node in ast.walk(facade_tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("analitica.scripts.")
    ]

    service_tree = ast.parse(Path(servicio.__file__).read_text(encoding="utf-8"))
    top_level_imports = [
        alias.name.split(".", maxsplit=1)[0]
        for node in service_tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [
        alias.name.split(".", maxsplit=1)[0]
        for node in service_tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]
    assert "pyodbc" not in top_level_imports
    assert "python_calamine" not in top_level_imports
    assert not [
        node
        for node in ast.walk(service_tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("analitica.scripts.")
    ]
