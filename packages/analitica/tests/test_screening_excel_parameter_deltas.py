from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analitica.aplicacion.servicios import excel_parameter_deltas as service
from analitica.interfaces.scripts import screening_excel_parameter_deltas as facade

NOMBRES_COMPATIBLES = (
    "Configuracion",
    "_normalizar_texto",
    "_es_variante",
    "sha256_archivo",
    "inventariar_libros",
    "_tabla_hoja",
    "_columna",
    "_clave_lote",
    "leer_snapshot_libro",
    "cargar_snapshots",
    "_mediana_finita",
    "calcular_delta_snapshot",
    "construir_deltas",
    "aplicar_shrinkage_features",
    "construir_contrato",
    "_ajustar_predecir",
    "predecir_temporal",
    "configuraciones",
    "_metricas",
    "_evaluar_periodo",
    "seleccionar_configuracion",
    "_keyset",
    "ejecutar",
    "_json_default",
)


@pytest.mark.parametrize("nombre", NOMBRES_COMPATIBLES)
def test_fachada_conserva_identidad_y_firma_historica(nombre: str) -> None:
    assert getattr(facade, nombre) is getattr(service, nombre)
    assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
        getattr(service, nombre)
    )


def _snapshot_rows(*, current: bool) -> list[dict[str, object]]:
    common = {
        "clave_lote": "arena|lote-1",
        "X1": 2 if current else 1,
        "X2": 3 if current else 2,
        "X3": 4 if current else 3,
        "O1": 5 if current else 4,
        "O2": 6 if current else 5,
        "O3": 7 if current else 6,
        "N1": 2 if current else 1,
        "N2": 3 if current else 2,
        "N3": 4 if current else 3,
        "A1": 20 if current else 10,
        "A2": 30 if current else 20,
        "A3": 40 if current else 30,
        "B1": 0.2 if current else 0.1,
        "B2": 0.3 if current else 0.2,
        "B3": 0.4 if current else 0.3,
        "FePas1": pd.Timestamp("2026-01-03" if current else "2026-01-01"),
        "FePas2": pd.Timestamp("2026-01-05" if current else "2026-01-01"),
    }
    other = {**common, "clave_lote": "arena|lote-2"}
    added = {**common, "clave_lote": "arena|lote-3"}
    return [common, other] if not current else [common, added]


def test_delta_preserva_formulas_columnas_y_tratamiento_de_altas_bajas() -> None:
    anterior = pd.DataFrame(_snapshot_rows(current=False))
    actual = pd.DataFrame(_snapshot_rows(current=True))

    resultado_facade = facade.calcular_delta_snapshot(
        anterior,
        actual,
        semana_anterior=24,
        semana_actual=25,
        fundo_operativo="Arena",
    )
    resultado_service = service.calcular_delta_snapshot(
        anterior,
        actual,
        semana_anterior=24,
        semana_actual=25,
        fundo_operativo="Arena",
    )

    assert resultado_facade == resultado_service
    assert resultado_facade["n_actual"] == 2
    assert resultado_facade["n_anterior"] == 2
    assert resultado_facade["n_comunes"] == 1
    assert resultado_facade["n_agregados"] == 1
    assert resultado_facade["n_retirados"] == 1
    assert resultado_facade["delta_x_dias"] == 1.0
    assert resultado_facade["delta_o_dias"] == 1.0
    assert resultado_facade["delta_b_miles"] == pytest.approx(100.0)
    assert resultado_facade["delta_fepas1_dias"] == 2.0
    assert resultado_facade["delta_calendario_dias"] == 3.0
    assert resultado_facade["lotes_agregados_frac"] == 0.5
    assert resultado_facade["lotes_retirados_frac"] == 0.5
    assert resultado_facade["share_parametros_cambiados"] == 1.0
    assert resultado_facade["share_calendario_cambiado"] == 1.0
    assert resultado_facade["delta_log_n"] == pytest.approx(
        np.log((9.0 + 1e-6) / (6.0 + 1e-6))
    )
    assert resultado_facade["delta_log_a"] == pytest.approx(
        np.log((30.0 + 1e-6) / (20.0 + 1e-6))
    )


def test_shrinkage_de_features_es_paritario_y_conserva_pesos() -> None:
    tabla = pd.DataFrame(
        [
            {
                "semana_emision": 24,
                "n_comunes": 1,
                **{feature: 0.0 for feature in service.FEATURES_CRUDAS},
            },
            {
                "semana_emision": 24,
                "n_comunes": 3,
                **{feature: 10.0 for feature in service.FEATURES_CRUDAS},
            },
        ]
    )

    salida_facade = facade.aplicar_shrinkage_features(tabla, 10.0)
    salida_service = service.aplicar_shrinkage_features(tabla, 10.0)

    pd.testing.assert_frame_equal(salida_facade, salida_service)
    assert salida_facade.loc[0, "delta_log_n_shrunk"] == pytest.approx(10.0 / 11.0 * 7.5)
    assert salida_facade.loc[1, "delta_log_n_shrunk"] == pytest.approx(
        3.0 / 13.0 * 10.0 + 10.0 / 13.0 * 7.5
    )


def test_prediccion_temporal_respeta_corte_asof_y_no_usa_futuro() -> None:
    filas = []
    for semana_objetivo in range(1, 11):
        fila = {
            "campania": "C2026",
            "semana_emision": semana_objetivo - 1,
            "semana_objetivo": semana_objetivo,
            "fundo_operativo": "Arena",
            "macro_kg": 100.0 + semana_objetivo,
            "real_kg": 110.0 + semana_objetivo,
            "r09_kg": 0.0,
            "r09_disponible": False,
            "residuo_objetivo": 0.1,
            "n_comunes": 10,
        }
        fila.update({feature: float(semana_objetivo) for feature in service.FEATURES_CRUDAS})
        filas.append(fila)
    contrato = pd.DataFrame(filas)
    config = service.Configuracion("amplitud", 20.0, 20.0, 12.0, 0.35)

    salida_facade = facade.predecir_temporal(contrato, config)
    salida_service = service.predecir_temporal(contrato, config)

    pd.testing.assert_frame_equal(salida_facade, salida_service)
    assert salida_facade.loc[
        salida_facade.semana_objetivo.eq(10), "n_entrenamiento"
    ].iat[0] == 8
    assert salida_facade.loc[
        salida_facade.semana_objetivo.eq(9), "n_entrenamiento"
    ].iat[0] == 0
    assert (salida_facade.n_entrenamiento.iloc[:8] == 0).all()


def test_fachada_cli_conserva_argumentos_serializacion_y_ruta(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    salida = tmp_path / "resultado" / "screening.json"
    raiz = tmp_path / "proyecciones"
    esperado = {
        "schema": "screening-excel-parameter-deltas-v1",
        "configuracion_ganadora": {"feature_set": "sin_correccion"},
        "trazabilidad": {"root": str(raiz)},
        "evaluation_contract": {"keyset_sha256": "abc"},
        "desarrollo": {"empresa": {}},
        "holdout": {"empresa": {}},
        "veredicto": {"publicable": False},
        "detalle": [{"valor": np.int64(3)}],
    }
    llamadas = []

    def fake_ejecutar(*, root, run_id, campania):
        llamadas.append((root, run_id, campania))
        return esperado

    monkeypatch.setattr(facade, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screening_excel_parameter_deltas",
            "--root",
            str(raiz),
            "--run-id",
            "88",
            "--campania",
            "C2027",
            "--salida",
            str(salida),
        ],
    )

    assert facade.main() == 0
    assert llamadas == [(raiz, 88, "C2027")]
    assert json.loads(salida.read_text(encoding="utf-8"))["detalle"] == [{"valor": 3}]
    assert json.loads(capsys.readouterr().out)["veredicto"] == {"publicable": False}


def test_fachada_es_compuerta_cli_sin_logica_de_negocio() -> None:
    ruta = Path(facade.__file__)
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    definiciones = [
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
    ]
