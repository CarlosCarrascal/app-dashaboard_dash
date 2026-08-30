from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from analitica.aplicacion.servicios import screening_turno_reingreso as servicio
from analitica.interfaces.scripts import screening_turno_reingreso as fachada

SCRIPT = Path(fachada.__file__)


def _fuentes_sinteticas() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    emisiones = {
        "C2024": pd.Timestamp("2025-01-01"),
        "C2025": pd.Timestamp("2025-06-02"),
        "C2026": pd.Timestamp("2026-04-06"),
    }
    macro: list[dict[str, object]] = []
    r09: list[dict[str, object]] = []
    cosecha: list[dict[str, object]] = []
    for campania, emision in emisiones.items():
        for horizonte, p50 in enumerate((100.0, 80.0, 60.0), start=1):
            fila = {
                "campania": campania,
                "fecha_emision": emision,
                "fecha_objetivo": emision + pd.Timedelta(weeks=horizonte),
                "horizonte_semanas": horizonte,
                "lote_id": 1,
                "fundo": "Arena",
                "modulo": "M01",
                "real_kg": p50 * 1.1,
            }
            macro.append({**fila, "p50_kg": p50})
            r09.append({**fila, "p50_kg": p50 * 1.05})
        cosecha.extend(
            {
                "campania": campania,
                "lote_id": 1,
                "fecha": emision - pd.Timedelta(days=dias),
                "kg": 10.0,
            }
            for dias in (28, 14)
        )
    return pd.DataFrame(macro), pd.DataFrame(r09), pd.DataFrame(cosecha)


def test_fachada_conserva_aliases_publicos_privados_imports_y_firmas() -> None:
    nombres = (
        "leer_datos",
        "_historia_por_lote",
        "_share_calendario",
        "precomputar_shares",
        "aplicar_config",
        "_serie_empresa",
        "metricas",
        "comparar",
        "_cortes_micro",
        "ejecutar",
    )
    for nombre in nombres:
        alias = getattr(fachada, nombre)
        implementacion = getattr(servicio, nombre)
        assert alias is implementacion
        assert inspect.signature(alias) == inspect.signature(implementacion)

    for nombre in (
        "RUNS",
        "CIERRES",
        "Config",
        "asdict",
        "dataclass",
        "np",
        "pd",
        "psycopg",
        "escribir_json_reproducible",
        "postgres_dsn",
    ):
        assert getattr(fachada, nombre) is getattr(servicio, nombre)
    assert fachada._COSECHA_GLOBAL is servicio._COSECHA_GLOBAL


def test_servicio_y_fachada_conservan_paridad_y_suma_por_lote_emision(monkeypatch) -> None:
    macro, r09, cosecha = _fuentes_sinteticas()
    monkeypatch.setattr(servicio, "_COSECHA_GLOBAL", cosecha)

    shares_fachada = fachada.precomputar_shares(macro)
    shares_servicio = servicio.precomputar_shares(macro)
    assert_frame_equal(shares_fachada, shares_servicio)

    config = servicio.Config(5, 4.5, 0.5)
    candidato_fachada = fachada.aplicar_config(shares_fachada, config)
    candidato_servicio = servicio.aplicar_config(shares_servicio, config)
    assert_frame_equal(candidato_fachada, candidato_servicio)

    grano = ["campania", "fecha_emision", "lote_id"]
    esperado = shares_servicio.groupby(grano).p50_kg.sum().sort_index()
    obtenido = candidato_servicio.groupby(grano).candidate_kg.sum().sort_index()
    pd.testing.assert_series_equal(esperado, obtenido, check_names=False)


def test_ejecutar_conserva_paridad_de_resultado(monkeypatch) -> None:
    fuentes = _fuentes_sinteticas()

    def fake_leer_datos() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        return tuple(tabla.copy() for tabla in fuentes)  # type: ignore[return-value]

    monkeypatch.setattr(servicio, "leer_datos", fake_leer_datos)
    resultado_fachada = fachada.ejecutar(micro=True)
    resultado_servicio = servicio.ejecutar(micro=True)

    assert json.dumps(resultado_fachada, sort_keys=True, default=str) == json.dumps(
        resultado_servicio, sort_keys=True, default=str
    )
    assert resultado_fachada["micro_replay"] is True
    assert resultado_fachada["n_configuraciones"] == 24


def test_cli_conserva_micro_salida_y_serializacion(monkeypatch, tmp_path, capsys) -> None:
    salida = tmp_path / "resultado" / "screening.json"
    resultado = {"mejor": {"config": {"peso_calendario": 0.2}}, "publicable": False}
    recibidos: list[bool] = []

    def fake_ejecutar(*, micro: bool = False) -> dict[str, object]:
        recibidos.append(micro)
        return resultado

    monkeypatch.setattr(fachada, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(
        sys,
        "argv",
        ["screening_turno_reingreso", "--micro", "--salida", str(salida)],
    )

    assert fachada.main() == 0
    assert recibidos == [True]
    assert json.loads(salida.read_text(encoding="utf-8")) == resultado
    assert json.loads(capsys.readouterr().out) == resultado["mejor"]


def test_fachada_es_delgada_y_servicio_no_importa_scripts() -> None:
    fachada_ast = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    definiciones = [
        nodo.name
        for nodo in fachada_ast.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not [
        nodo
        for nodo in ast.walk(fachada_ast)
        if isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
    ]

    servicio_ast = ast.parse(
        Path(servicio.__file__).read_text(encoding="utf-8"), filename=str(servicio.__file__)
    )
    assert not [
        nodo
        for nodo in ast.walk(servicio_ast)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
    ]
