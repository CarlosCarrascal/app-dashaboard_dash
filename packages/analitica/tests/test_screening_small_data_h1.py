from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.servicios import small_data, small_data_h1

SCRIPT = Path(__file__).parents[1] / "interfaces" / "scripts" / "screening_small_data_h1.py"
SPEC = importlib.util.spec_from_file_location("screening_small_data_h1_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULO = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULO
SPEC.loader.exec_module(MODULO)


def test_fachada_reexporta_aliases_publicos_privados_y_firmas() -> None:
    nombres = (
        "CAMPANIA_DEFAULT",
        "FEATURE_SETS",
        "FUNDOS",
        "RUN_ID_DEFAULT",
        "SEMANA_MAX_SELECCION",
        "SEMANAS_HOLDOUT",
        "ULTIMO_CIERRE_DEFAULT",
        "Configuracion",
        "_ajustar_modelo",
        "_cargar_universo_lote",
        "_json_default",
        "_metricas",
        "_resumen_periodo",
        "_wins",
        "aplicar_candidato_a_lotes",
        "cargar_universo_lote",
        "construir_panel_fundo",
        "configuraciones",
        "ejecutar",
        "normalizar_fundo",
        "predecir_rolling",
        "seleccionar_configuracion",
    )
    for nombre in nombres:
        assert getattr(MODULO, nombre) is getattr(small_data_h1, nombre), nombre

    assert inspect.signature(MODULO.cargar_universo_lote) == inspect.signature(
        small_data.cargar_universo_lote
    )
    assert inspect.signature(MODULO.ejecutar) == inspect.signature(small_data_h1.ejecutar)


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


def test_fachada_cli_conserva_argumentos_serializacion_y_ruta(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    salida = tmp_path / "resultado" / "small_data_h1.json"
    recibidos: list[tuple[int, str, pd.Timestamp]] = []

    def fake_ejecutar(
        *, run_id: int, campania: str, ultimo_cierre: pd.Timestamp
    ) -> dict[str, object]:
        recibidos.append((run_id, campania, ultimo_cierre))
        return {"entero": np.int64(3), "fecha": pd.Timestamp("2026-08-16")}

    monkeypatch.setattr(MODULO, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screening_small_data_h1",
            "--run-id",
            "99",
            "--campania",
            "C2027",
            "--ultimo-cierre",
            "2026-08-20",
            "--salida",
            str(salida),
        ],
    )

    assert MODULO.main() == 0
    assert recibidos == [(99, "C2027", pd.Timestamp("2026-08-20"))]
    esperado = {"entero": 3, "fecha": "2026-08-16T00:00:00"}
    assert json.loads(salida.read_text(encoding="utf-8")) == esperado
    assert json.loads(capsys.readouterr().out) == esperado


def test_servicio_y_fachada_producen_la_misma_panelizacion_y_prediccion() -> None:
    universo = _universo()
    panel_fachada = MODULO.construir_panel_fundo(universo)
    panel_servicio = small_data_h1.construir_panel_fundo(universo)
    pd.testing.assert_frame_equal(panel_fachada, panel_servicio)

    config = MODULO.Configuracion(
        estimador="ridge",
        feature_set="macro_lags",
        alpha=10.0,
        epsilon=1.35,
        factor_minimo=0.8,
        factor_maximo=1.3,
    )
    pred_fachada = MODULO.predecir_rolling(panel_fachada, config)
    pred_servicio = small_data_h1.predecir_rolling(panel_servicio, config)
    pd.testing.assert_frame_equal(pred_fachada, pred_servicio)


def _universo(semanas: range = range(13, 25)) -> pd.DataFrame:
    filas: list[dict[str, object]] = []
    lunes_base = pd.Timestamp("2026-03-23")
    for desplazamiento, semana in enumerate(semanas):
        objetivo = lunes_base + pd.Timedelta(days=7 * desplazamiento)
        emision = objetivo - pd.Timedelta(days=7)
        for fundo, escala in (("Arena", 1.0), ("Ayllu", 0.7), ("Kawsay", 1.4), ("Quri", 1.1)):
            macro = (100.0 + desplazamiento * 20.0) * escala
            real = macro * (1.10 + 0.02 * np.sin(desplazamiento))
            for lote in range(2):
                filas.append(
                    {
                        "campania": "C2026",
                        "fecha_emision": emision,
                        "fecha_objetivo": objetivo,
                        "semana_fin": objetivo + pd.Timedelta(days=6),
                        "semana_objetivo": semana,
                        "fundo_operativo": fundo,
                        "fundo": fundo,
                        "modulo": "M01",
                        "lote_id": f"{fundo}-{lote}",
                        "macro_kg": macro / 2.0,
                        "real_kg": real / 2.0,
                        "r09_kg": real / 2.0,
                        "r09_emitio": lote == 0,
                    }
                )
    return pd.DataFrame(filas)


def test_features_asof_no_cambian_al_mutar_el_resultado_objetivo() -> None:
    universo = _universo()
    original = MODULO.construir_panel_fundo(universo)
    mutado = universo.copy()
    mutado.loc[mutado.semana_objetivo.eq(24), "real_kg"] *= 100.0
    recalculado = MODULO.construir_panel_fundo(mutado)

    features = sorted({columna for valores in MODULO.FEATURE_SETS.values() for columna in valores})
    pd.testing.assert_frame_equal(original[features], recalculado[features])
    assert not original.residuo_objetivo.equals(recalculado.residuo_objetivo)


def test_rolling_solo_entrena_con_semanas_cerradas_antes_de_emitir() -> None:
    panel = MODULO.construir_panel_fundo(_universo())
    config = MODULO.Configuracion(
        estimador="ridge",
        feature_set="macro_lags",
        alpha=10.0,
        epsilon=1.35,
        factor_minimo=0.8,
        factor_maximo=1.3,
    )
    prediccion = MODULO.predecir_rolling(panel, config)
    ajustadas = prediccion.loc[prediccion.modelo_ajustado]

    assert not ajustadas.empty
    # En h1 la emisión es el lunes anterior al objetivo; al emitir, la semana
    # inmediatamente anterior todavía no cerró. El máximo entrenable es S-2.
    assert (ajustadas.max_semana_entrenamiento <= ajustadas.semana_objetivo - 2).all()


def test_real_del_holdout_no_altera_su_propia_prediccion() -> None:
    universo = _universo()
    panel = MODULO.construir_panel_fundo(universo)
    config = MODULO.Configuracion(
        estimador="huber",
        feature_set="macro_lags_forma",
        alpha=0.01,
        epsilon=1.35,
        factor_minimo=0.65,
        factor_maximo=1.55,
    )
    original = MODULO.predecir_rolling(panel, config)

    mutado = universo.copy()
    mutado.loc[mutado.semana_objetivo.eq(24), "real_kg"] += 1_000_000.0
    repetido = MODULO.predecir_rolling(MODULO.construir_panel_fundo(mutado), config)
    columnas = ["semana_objetivo", "fundo_operativo", "candidate_kg"]
    esperado = original.loc[original.semana_objetivo.le(24), columnas].reset_index(drop=True)
    obtenido = repetido.loc[repetido.semana_objetivo.le(24), columnas].reset_index(drop=True)
    pd.testing.assert_frame_equal(esperado, obtenido)


def test_r09_no_es_feature_y_el_candidato_cubre_toda_la_macro() -> None:
    assert all(
        "r09" not in columna.casefold()
        for valores in MODULO.FEATURE_SETS.values()
        for columna in valores
    )
    universo = _universo(range(13, 15))
    panel = MODULO.construir_panel_fundo(universo)
    pred = panel.assign(candidate_kg=panel.macro_kg * 1.1)
    lotes = MODULO.aplicar_candidato_a_lotes(universo, pred)

    assert lotes.candidate_kg.notna().all()
    assert len(lotes.loc[lotes.r09_emitio]) < len(lotes)
    conciliado = lotes.groupby(
        ["fecha_objetivo", "fundo_operativo"], as_index=False
    ).candidate_kg.sum()
    esperado = pred[["fecha_objetivo", "fundo_operativo", "candidate_kg"]]
    pd.testing.assert_frame_equal(
        conciliado.sort_values(["fecha_objetivo", "fundo_operativo"]).reset_index(drop=True),
        esperado.sort_values(["fecha_objetivo", "fundo_operativo"]).reset_index(drop=True),
    )
