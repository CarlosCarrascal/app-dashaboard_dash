from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from analitica.scripts import screening_router_parametros_lagged as fachada
from analitica.servicios import router_parametros_lagged as servicio

ROOT = Path(__file__).resolve().parents[1]


def test_la_fachada_conserva_aliases_identidad_y_firmas():
    nombres = (
        "ACCESS_DEFAULT",
        "ARTEFACTO_LAGGED",
        "ConfiguracionHibridoParametrosLagged",
        "agregar",
        "cargar_reales_y_r09",
        "ejecutar",
        "leer",
        "seleccionar_peso_parametros_asof",
    )
    for nombre in nombres:
        assert getattr(fachada, nombre) is getattr(servicio, nombre)
    assert fachada._metricas is servicio._metricas
    assert fachada._bootstrap_beneficio is servicio._bootstrap_beneficio
    assert inspect.signature(fachada.ejecutar) == inspect.signature(servicio.ejecutar)
    assert inspect.signature(fachada._metricas) == inspect.signature(servicio._metricas)
    assert inspect.signature(fachada._bootstrap_beneficio) == inspect.signature(
        servicio._bootstrap_beneficio
    )


def test_fachada_y_servicio_conservan_paridad_de_ejecucion(monkeypatch, tmp_path):
    def fake_leer(
        run_id: int, campania: str, modelo: str, horizontes: tuple[int, ...]
    ) -> pd.DataFrame:
        valores = {
            (76, "MacroLegacy_v1"): (100.0, 110.0),
            (76, "R09_publicado"): (105.0, 110.0),
            (73, "MacroLegacy_v1"): (200.0, 210.0),
            (73, "R09_publicado"): (205.0, 210.0),
        }
        valor, real = valores[(run_id, modelo)]
        filas = []
        for horizonte in horizontes:
            objetivo = 29 + horizonte
            filas.append(
                {
                    "campania": campania,
                    "fecha_emision": pd.Timestamp.fromisocalendar(2026, 29, 1),
                    "fecha_objetivo": pd.Timestamp.fromisocalendar(2026, objetivo, 1),
                    "horizonte_semanas": horizonte,
                    "p50_kg": valor,
                    "real_kg": real,
                }
            )
        return pd.DataFrame(filas)

    monkeypatch.setattr(servicio, "leer", fake_leer)
    monkeypatch.setattr(servicio, "cargar_reales_y_r09", lambda access, campania: ({28: 90.0}, {}))
    artefacto = tmp_path / "lagged.json"
    artefacto.write_text(
        json.dumps(
            {
                "detalle": [
                    {
                        "bloque": "ninguno",
                        "semana_emision": 29,
                        "semana_objetivo": 30,
                        "candidato_kg": 100.0,
                        "real_kg": 110.0,
                        "r09_kg": 105.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    servicio_resultado = servicio.ejecutar(
        access=tmp_path / "access.accdb", artefacto_lagged=artefacto
    )
    fachada_resultado = fachada.ejecutar(
        access=tmp_path / "access.accdb", artefacto_lagged=artefacto
    )

    assert fachada_resultado.keys() == servicio_resultado.keys()
    for clave in fachada_resultado.keys() - {"detalle"}:
        assert fachada_resultado[clave] == servicio_resultado[clave]
    assert_frame_equal(
        pd.DataFrame(fachada_resultado["detalle"]),
        pd.DataFrame(servicio_resultado["detalle"]),
    )
    assert servicio_resultado["n_reemplazos_h1"] == 1
    assert servicio_resultado["reemplazos_h1"][0]["candidate_kg"] == 100.0


def test_cli_conserva_argumentos_salida_y_serializacion(monkeypatch, tmp_path, capsys):
    access = tmp_path / "entrada.accdb"
    artefacto = tmp_path / "lagged.json"
    salida = tmp_path / "resultado.json"
    resultado = {
        "resumen": {"candidato": {"wape": 0.1}},
        "por_horizonte": {"1": {"candidato": {"wape": 0.1}}},
        "bootstrap_beneficio_wape_vs_r09": {"p05": 0.0, "p50": 0.1, "p95": 0.2},
    }
    recibidos = {}

    def fake_ejecutar(*, access: Path, artefacto_lagged: Path):
        recibidos.update(access=access, artefacto_lagged=artefacto_lagged)
        return resultado

    monkeypatch.setattr(fachada, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screening_router_parametros_lagged",
            "--access",
            str(access),
            "--artefacto-lagged",
            str(artefacto),
            "--salida",
            str(salida),
        ],
    )

    assert fachada.main() == 0

    assert recibidos == {"access": access, "artefacto_lagged": artefacto}
    assert json.loads(salida.read_text(encoding="utf-8")) == resultado
    assert json.loads(capsys.readouterr().out) == {
        "resumen": resultado["resumen"],
        "por_horizonte": resultado["por_horizonte"],
        "bootstrap": resultado["bootstrap_beneficio_wape_vs_r09"],
    }


def test_script_es_fachada_ast_sin_logica_de_negocio_y_servicio_sin_scripts():
    script = ROOT / "scripts" / "screening_router_parametros_lagged.py"
    arbol_script = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    assert [n.name for n in arbol_script.body if isinstance(n, ast.FunctionDef)] == ["main"]

    servicio_ast = ast.parse(
        (ROOT / "servicios" / "router_parametros_lagged.py").read_text(encoding="utf-8"),
        filename="router_parametros_lagged.py",
    )
    imports_de_scripts = [
        nodo.module
        for nodo in ast.walk(servicio_ast)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
    ]
    assert imports_de_scripts == []
