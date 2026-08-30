from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.servicios import small_data_farm

SCRIPT = Path(__file__).parents[1] / "interfaces" / "scripts" / "screening_small_data_farm.py"
SPEC = importlib.util.spec_from_file_location("screening_small_data_farm_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULO = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULO
SPEC.loader.exec_module(MODULO)


def test_fachada_reexporta_aliases_publicos_privados_y_firmas() -> None:
    nombres = (
        "RUNS_H1",
        "CIERRES",
        "FUNDOS",
        "Config",
        "_fundo",
        "_numero",
        "_features",
        "_clave_modelo",
        "comparar_r09",
        "configuraciones",
        "construir_fundo_semana",
        "ejecutar",
        "leer_panel",
        "metricas_empresa",
        "predecir_rolling",
    )
    for nombre in nombres:
        assert getattr(MODULO, nombre) is getattr(small_data_farm, nombre), nombre

    for nombre in nombres[4:]:
        objeto = getattr(MODULO, nombre)
        if callable(objeto):
            assert inspect.signature(objeto) == inspect.signature(getattr(small_data_farm, nombre))


def test_fachada_es_delgada_y_no_importa_otros_scripts() -> None:
    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    funciones = [
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert funciones == ["main"]
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
        for nodo in ast.walk(arbol)
    )


def test_fachada_cli_conserva_serializacion_y_ruta(tmp_path: Path, monkeypatch, capsys) -> None:
    salida = tmp_path / "resultado" / "small_data_farm.json"
    recibidos: list[Path] = []
    resultado = {"mejor": {"entero": np.int64(3), "fecha": pd.Timestamp("2026-08-16")}}

    def fake_ejecutar() -> dict[str, object]:
        return resultado

    def fake_escribir(valor: dict[str, object], ruta: Path) -> None:
        assert valor is resultado
        recibidos.append(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(valor["mejor"], default=str), encoding="utf-8")

    monkeypatch.setattr(MODULO, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(MODULO, "escribir_json_reproducible", fake_escribir)
    monkeypatch.setattr(sys, "argv", ["screening_small_data_farm", "--salida", str(salida)])

    assert MODULO.main() == 0
    assert recibidos == [salida]
    esperado = {"entero": "3", "fecha": "2026-08-16 00:00:00"}
    assert json.loads(salida.read_text(encoding="utf-8")) == esperado
    assert json.loads(capsys.readouterr().out) == esperado


def test_servicio_y_fachada_producen_la_misma_panelizacion_y_prediccion() -> None:
    macro = _macro()
    panel_fachada = MODULO.construir_fundo_semana(macro)
    panel_servicio = small_data_farm.construir_fundo_semana(macro)
    pd.testing.assert_frame_equal(panel_fachada, panel_servicio)

    config = MODULO.Config(
        objetivo="residuo_log",
        alpha=10.0,
        limite_inferior=0.70,
        limite_superior=1.35,
        ventana_misma_campania=4,
        incluir_clima=False,
        incluir_fenologia=False,
    )
    pred_fachada = MODULO.predecir_rolling(panel_fachada, config)
    pred_servicio = small_data_farm.predecir_rolling(panel_servicio, config)
    pd.testing.assert_frame_equal(pred_fachada, pred_servicio)


def test_features_respetan_asof_y_r09_no_es_predictor() -> None:
    macro = _macro(range(13, 27))
    panel = MODULO.construir_fundo_semana(macro)
    objetivo = pd.Timestamp("2026-04-06")
    mutado = macro.copy()
    mutado.loc[mutado.fecha_objetivo.eq(objetivo), "real_kg"] *= 100.0
    recalculado = MODULO.construir_fundo_semana(mutado)
    columnas = [
        "ultimo_real_cerrado",
        "media_real_4",
        "ratio_real_macro_4",
        "n_cerradas_campania",
        "log_ultimo_real",
        "log_media_real_4",
    ]
    antes_del_objetivo = panel.fecha_objetivo.le(objetivo)
    pd.testing.assert_frame_equal(
        panel.loc[antes_del_objetivo, columnas].reset_index(drop=True),
        recalculado.loc[antes_del_objetivo, columnas].reset_index(drop=True),
    )
    assert all("r09" not in columna.casefold() for columna in MODULO._features(MODULO.Config(
        "log_real", 1.0, 0.7, 1.35, 4, False, False
    )))


def _macro(semanas: range = range(13, 25)) -> pd.DataFrame:
    filas: list[dict[str, object]] = []
    lunes_base = pd.Timestamp("2026-01-05")
    for desplazamiento, semana in enumerate(semanas):
        objetivo = lunes_base + pd.Timedelta(days=7 * desplazamiento)
        emision = objetivo - pd.Timedelta(days=7)
        for fundo, escala in (("Arena", 1.0), ("Ayllu", 0.7), ("Kawsay", 1.4), ("Quri", 1.1)):
            macro = (100.0 + desplazamiento * 20.0) * escala
            real = macro * (1.10 + 0.02 * np.sin(desplazamiento))
            filas.append(
                {
                    "campania": "C2026",
                    "fecha_emision": emision,
                    "fecha_objetivo": objetivo,
                    "horizonte_semanas": 1,
                    "lote_id": f"{fundo}-{semana}",
                    "fundo": fundo,
                    "modulo": "M01",
                    "p50_kg": macro,
                    "real_kg": real,
                    "plantas": 1000.0 * escala,
                    "componentes": {
                        "flores": 10.0,
                        "frutos_muestra": 20.0,
                        "dias_desde_poda": 30.0,
                        "indice_estado": 0.5,
                        "gdd_7_0_7d": 40.0,
                        "gdd_7_0_28d": 120.0,
                        "temp_media_7d": 18.0,
                        "dpv_kpa_7d": 1.2,
                        "eto_7d": 25.0,
                        "kg_ultimas_4_semanas_asof": 80.0,
                        "real_acumulado": 500.0,
                    },
                }
            )
    return pd.DataFrame(filas)
