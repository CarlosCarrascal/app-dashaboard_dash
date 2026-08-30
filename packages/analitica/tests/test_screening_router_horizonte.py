from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd

from analitica.aplicacion.servicios import router_horizonte as servicio
from analitica.interfaces.scripts import screening_router_horizonte as fachada

ROOT = Path(__file__).resolve().parents[1]


def _filas(campania: str, horizontes: tuple[int, ...], valor: float, real: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "campania": campania,
                "fecha_emision": pd.Timestamp("2026-01-05"),
                "fecha_objetivo": pd.Timestamp("2026-01-05")
                + pd.to_timedelta(int(horizonte), unit="W"),
                "horizonte_semanas": horizonte,
                "lote_id": "lote-1",
                "fundo": "fundo-1",
                "modulo": "modulo-1",
                "p50_kg": valor + horizonte,
                "real_kg": real,
            }
            for horizonte in horizontes
        ]
    )


def _leer_sintetico(
    run_id: int, campania: str, modelo: str, horizontes: tuple[int, ...]
) -> pd.DataFrame:
    valores = {
        "HibridoOcurrenciaOnline_v2": (90.0, 100.0),
        "MacroLegacy_v1": (80.0, 100.0),
        "R09_publicado": (95.0, 100.0),
    }
    valor, real = valores[modelo]
    if run_id == servicio.RUNS_H1[campania] and horizontes == (1,):
        return _filas(campania, horizontes, valor, real)
    return _filas(campania, horizontes, valor + run_id / 1000, real)


def test_fachada_reexporta_servicio_y_conserva_aliases_historicos() -> None:
    for nombre in (
        "CIERRES",
        "RUNS_H1",
        "RUNS_MULTI",
        "agregar",
        "ejecutar",
        "evaluar_campania",
        "leer",
    ):
        assert getattr(fachada, nombre) is getattr(servicio, nombre)
    assert fachada._leer is servicio.leer
    assert fachada._agregar is servicio.agregar
    assert inspect.signature(fachada.evaluar_campania) == inspect.signature(
        servicio.evaluar_campania
    )
    assert inspect.signature(fachada.ejecutar) == inspect.signature(servicio.ejecutar)


def test_fachada_y_servicio_conservan_paridad_y_forma_de_salida(monkeypatch) -> None:
    monkeypatch.setattr(servicio, "_leer", _leer_sintetico)

    por_campania_fachada = fachada.evaluar_campania("C2025")
    por_campania_servicio = servicio.evaluar_campania("C2025")
    assert por_campania_fachada == por_campania_servicio
    assert set(por_campania_fachada) == {
        "campania",
        "n_emision_objetivo_horizonte",
        "volumen_real_kg",
        "por_modelo",
        "por_horizonte",
        "porcentaje_cortes_ganados_r09",
    }
    assert set(por_campania_fachada["por_modelo"]) == {
        "RouterHorizonte_v1",
        "MacroLegacy_v1",
        "R09_publicado",
    }
    assert set(por_campania_fachada["por_horizonte"]) == {"1", "2", "3", "4", "5"}

    salida_fachada = fachada.ejecutar()
    salida_servicio = servicio.ejecutar()
    assert salida_fachada == salida_servicio
    assert set(salida_fachada) == {
        "schema",
        "formula",
        "usa_r09_como_predictor",
        "runs_h1",
        "runs_multi",
        "resultados",
        "decisiones",
        "publicable",
    }
    assert salida_fachada["schema"] == "screening-router-horizonte-v1"
    assert salida_fachada["formula"] == (
        "HibridoOcurrenciaOnline_v2 en h1; MacroLegacy_v1 en h2-h5"
    )
    assert salida_fachada["usa_r09_como_predictor"] is False
    assert salida_fachada["publicable"] is False


def test_cli_conserva_salida_json_y_argumentos(monkeypatch, capsys) -> None:
    resultado = {
        "schema": "screening-router-horizonte-v1",
        "resultados": {"C2025": {"por_modelo": {}}},
    }
    monkeypatch.setattr(fachada, "ejecutar", lambda: resultado)
    monkeypatch.setattr(sys, "argv", ["screening_router_horizonte"])

    assert fachada.main() == 0
    assert json.loads(capsys.readouterr().out) == resultado


def test_fachada_no_contiene_logica_de_negocio() -> None:
    arbol = ast.parse(
        (ROOT / "interfaces" / "scripts" / "screening_router_horizonte.py").read_text(
            encoding="utf-8"
        )
    )
    assert [n.name for n in arbol.body if isinstance(n, ast.FunctionDef)] == ["main"]
