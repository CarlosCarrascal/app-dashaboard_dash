from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.servicios import cross_campaign as SERVICIO

SCRIPT = Path(__file__).parents[1] / "scripts" / "screening_cross_campaign_h1.py"
SPEC = importlib.util.spec_from_file_location("screening_cross_campaign_h1_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULO = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULO
SPEC.loader.exec_module(MODULO)


def test_la_fachada_reexporta_la_unica_implementacion_y_conserva_firmas() -> None:
    nombres = (
        "sha256_archivo",
        "leer_macro_h1",
        "leer_reales_access",
        "construir_panel",
        "construir_features_asof",
        "configuraciones",
        "mascara_entrenamiento",
        "predecir_rolling",
        "bootstrap_pareado",
        "mascara_seleccion",
        "seleccionar_configuracion",
        "ejecutar",
        "escribir_json",
        "normalizar_fundo",
        "leer_r09_access",
        "preparar_r09_crudo",
    )
    for nombre in nombres:
        fachada = getattr(MODULO, nombre)
        servicio = getattr(SERVICIO, nombre)
        assert fachada is servicio
        assert inspect.signature(fachada) == inspect.signature(servicio)

    assert MODULO.Configuracion is SERVICIO.Configuracion
    assert MODULO.FEATURE_SETS is SERVICIO.FEATURE_SETS


def test_el_script_solo_conserva_el_adaptador_cli() -> None:
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
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
    ]


def _panel_sintetico() -> pd.DataFrame:
    filas: list[dict[str, object]] = []
    definiciones = (
        ("C2024", pd.Timestamp("2025-01-06"), 10),
        ("C2025", pd.Timestamp("2025-06-02"), 12),
        ("C2026", pd.Timestamp("2026-03-23"), 12),
    )
    for campania, inicio, n_semanas in definiciones:
        for i in range(n_semanas):
            objetivo = inicio + pd.Timedelta(days=7 * i)
            emision = objetivo - pd.Timedelta(days=7)
            for j, fundo in enumerate(MODULO.FUNDOS):
                macro = (80_000.0 + 8_000.0 * i) * (0.65 + 0.18 * j)
                real = macro * (1.08 + 0.03 * np.sin(i / 2.0 + j))
                filas.append(
                    {
                        "campania": campania,
                        "fecha_emision": emision,
                        "fecha_objetivo": objetivo,
                        "semana_fin": objetivo + pd.Timedelta(days=6),
                        "semana_iso": int(objetivo.isocalendar().week),
                        "fundo_operativo": fundo,
                        "macro_kg": macro,
                        "real_kg": real,
                        "residuo_objetivo": np.log1p(real) - np.log1p(macro),
                    }
                )
    return pd.DataFrame(filas)


def test_features_asof_no_usan_el_real_de_su_objetivo() -> None:
    panel = _panel_sintetico()
    original = MODULO.construir_features_asof(panel)
    fecha = pd.Timestamp("2026-06-08")
    mutado = panel.copy()
    mutado.loc[mutado.campania.eq("C2026") & mutado.fecha_objetivo.eq(fecha), "real_kg"] *= 100.0
    mutado["residuo_objetivo"] = np.log1p(mutado.real_kg) - np.log1p(mutado.macro_kg)
    repetido = MODULO.construir_features_asof(mutado)
    columnas = sorted(
        {columna for conjunto in MODULO.FEATURE_SETS.values() for columna in conjunto}
    )
    mascara = original.fecha_objetivo.le(fecha)
    pd.testing.assert_frame_equal(
        original.loc[mascara, columnas].reset_index(drop=True),
        repetido.loc[mascara, columnas].reset_index(drop=True),
    )


def test_rolling_entrena_solo_con_cierres_anteriores_a_la_emision() -> None:
    panel = MODULO.construir_features_asof(_panel_sintetico())
    config = MODULO.Configuracion(
        estimador="ridge",
        feature_set="compacto",
        alpha=10.0,
        factor_minimo=0.8,
        factor_maximo=1.35,
    )
    prediccion = MODULO.predecir_rolling(panel, config)
    ajustadas = prediccion.loc[prediccion.modelo_ajustado]
    assert not ajustadas.empty
    assert (ajustadas.max_cierre_entrenamiento < ajustadas.fecha_emision).all()


def test_holdout_c2026_no_entra_en_la_seleccion() -> None:
    tabla = pd.DataFrame(
        {
            "campania": ["C2025", "C2026", "C2026", "C2026"],
            "semana_iso": [52, 30, 31, 33],
        }
    )
    mascara = MODULO.mascara_seleccion(tabla)
    assert mascara.tolist() == [True, True, False, False]
    assert not tabla.loc[mascara, "semana_iso"].isin(MODULO.SEMANAS_HOLDOUT_C2026).any()


def test_r09_contemporaneo_se_excluye_y_se_elige_ultima_variante_previa() -> None:
    crudo = pd.DataFrame(
        {
            "campania": ["C2026", "C2026", "C2026"],
            "version": ["S33", "S33_v2", "S34"],
            "fecha_cosecha": [pd.Timestamp("2026-08-17")] * 3,
            "fundo": ["Aqu Anqa 1"] * 3,
            "r09_kg": [100.0, 110.0, 900.0],
        }
    )
    resultado = MODULO.preparar_r09_crudo(crudo)
    assert len(resultado) == 1
    assert resultado.iloc[0].version == "S33_v2"
    assert resultado.iloc[0].r09_kg == 110.0
    assert resultado.iloc[0].fecha_emision < resultado.iloc[0].fecha_objetivo


def test_fundos_descriptivos_de_r09_se_normalizan_al_contrato_operativo() -> None:
    assert MODULO.normalizar_fundo("Aqu Anqa - Arena Azul") == "Arena"
    assert MODULO.normalizar_fundo("Aqu Anqa II - Ayllu Allpa") == "Ayllu"
    assert MODULO.normalizar_fundo("Aqu Anqa II - Kawsay Allpa") == "Kawsay"
    assert MODULO.normalizar_fundo("Aqu Anqa II - Quri Allpa") == "Quri"


def test_grilla_no_duplica_configuraciones_y_aplica_peso_en_ridge() -> None:
    configuraciones = MODULO.configuraciones()
    ids = [config.id for config in configuraciones]
    assert len(ids) == len(set(ids))
    pesos_ridge = {
        config.peso_correccion for config in configuraciones if config.estimador == "ridge"
    }
    assert pesos_ridge == {0.25, 0.50, 0.75}


def test_r09_no_es_feature_ni_argumento_del_predictor() -> None:
    assert all(
        "r09" not in columna.casefold()
        for conjunto in MODULO.FEATURE_SETS.values()
        for columna in conjunto
    )
    assert "r09" not in MODULO.predecir_rolling.__code__.co_varnames


def test_bootstrap_compara_el_mismo_universo_semanal() -> None:
    tabla = pd.DataFrame(
        {
            "campania": ["C2026"] * 8,
            "fecha_objetivo": np.repeat(pd.date_range("2026-07-06", periods=2, freq="7D"), 4),
            "fundo_operativo": list(MODULO.FUNDOS) * 2,
            "real_kg": [100.0] * 8,
            "candidate_kg": [105.0] * 8,
            "macro_kg": [120.0] * 8,
        }
    )
    resultado = MODULO.bootstrap_pareado(tabla, "candidate_kg", "macro_kg", 200)
    assert resultado is not None
    assert resultado["n_semanas"] == 2
    assert resultado["diferencia_wape_pp"] < 0.0


def test_bootstrap_por_fundo_conserva_los_cuatro_fundos() -> None:
    tabla = pd.DataFrame(
        {
            "campania": ["C2026"] * 8,
            "fecha_objetivo": np.repeat(pd.date_range("2026-07-06", periods=2, freq="7D"), 4),
            "fundo_operativo": list(MODULO.FUNDOS) * 2,
            "real_kg": [100.0] * 8,
            "candidate_kg": [105.0] * 8,
            "macro_kg": [120.0] * 8,
        }
    )
    resultado = MODULO._bootstrap_por_fundo(tabla, "candidate_kg", "macro_kg")
    assert set(resultado) == set(MODULO.FUNDOS)
    assert all(valor is not None and valor["n_semanas"] == 2 for valor in resultado.values())
