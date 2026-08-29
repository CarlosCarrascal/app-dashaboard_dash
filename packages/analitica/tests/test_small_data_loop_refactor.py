from __future__ import annotations

import ast
from pathlib import Path

from analitica.servicios import (
    loop_forecast_horizontes,
    loop_forecast_horizontes_configuracion,
    loop_forecast_horizontes_evaluacion,
    loop_forecast_horizontes_lectura,
    loop_forecast_horizontes_prediccion,
    loop_forecast_horizontes_salida,
    small_data_h1,
    small_data_h1_configuracion,
    small_data_h1_evaluacion,
    small_data_h1_lectura,
    small_data_h1_prediccion,
    small_data_h1_salida,
)


def test_facades_reexportan_responsabilidades_desde_modulos_hermanos() -> None:
    aliases = {
        small_data_h1: {
            small_data_h1.Configuracion: small_data_h1_configuracion,
            small_data_h1.configuraciones: small_data_h1_configuracion,
            small_data_h1.normalizar_fundo: small_data_h1_lectura,
            small_data_h1.cargar_universo_lote: small_data_h1_lectura,
            small_data_h1.construir_panel_fundo: small_data_h1_prediccion,
            small_data_h1.predecir_rolling: small_data_h1_prediccion,
            small_data_h1.aplicar_candidato_a_lotes: small_data_h1_prediccion,
            small_data_h1._metricas: small_data_h1_evaluacion,
            small_data_h1._wins: small_data_h1_evaluacion,
            small_data_h1._resumen_periodo: small_data_h1_evaluacion,
            small_data_h1.seleccionar_configuracion: small_data_h1_evaluacion,
            small_data_h1.ejecutar: small_data_h1_salida,
            small_data_h1._json_default: small_data_h1_salida,
        },
        loop_forecast_horizontes: {
            loop_forecast_horizontes._leer_predicciones: loop_forecast_horizontes_lectura,
            loop_forecast_horizontes._normalizar_fundo: loop_forecast_horizontes_lectura,
            loop_forecast_horizontes._consolidar_fundos: loop_forecast_horizontes_lectura,
            loop_forecast_horizontes._panel_base: loop_forecast_horizontes_lectura,
            loop_forecast_horizontes._leer_nowcast: loop_forecast_horizontes_lectura,
            loop_forecast_horizontes._aplicar_mejores: loop_forecast_horizontes_prediccion,
            loop_forecast_horizontes._semanal: loop_forecast_horizontes_evaluacion,
            loop_forecast_horizontes._metricas: loop_forecast_horizontes_evaluacion,
            loop_forecast_horizontes._metricas_por_horizonte: loop_forecast_horizontes_evaluacion,
            loop_forecast_horizontes._comparar_r09: loop_forecast_horizontes_evaluacion,
            loop_forecast_horizontes._resumen_nowcast_vs_v2: loop_forecast_horizontes_evaluacion,
            loop_forecast_horizontes.ejecutar: loop_forecast_horizontes_salida,
        },
    }
    for fachada, funciones in aliases.items():
        for funcion, modulo in funciones.items():
            assert funcion.__module__ == modulo.__name__, (fachada.__name__, funcion)


def test_facades_no_contienen_implementacion_y_conservan_simbolos_historicos() -> None:
    for fachada in (small_data_h1, loop_forecast_horizontes):
        arbol = ast.parse(Path(fachada.__file__).read_text(encoding="utf-8"))
        assert not [
            nodo
            for nodo in arbol.body
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]

    assert small_data_h1.FEATURE_SETS is small_data_h1_configuracion.FEATURE_SETS
    assert small_data_h1.FUNDOS is small_data_h1_configuracion.FUNDOS
    assert loop_forecast_horizontes.CIERRES is loop_forecast_horizontes_configuracion.CIERRES
    assert (
        loop_forecast_horizontes.HORIZONTES_LARGOS
        is loop_forecast_horizontes_configuracion.HORIZONTES_LARGOS
    )
