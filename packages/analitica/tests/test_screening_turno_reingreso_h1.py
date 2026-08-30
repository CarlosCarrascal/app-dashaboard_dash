from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from analitica.aplicacion.servicios import turno_reingreso_h1 as servicio
from analitica.interfaces.scripts import screening_turno_reingreso_h1 as fachada
from analitica.interfaces.scripts.screening_turno_reingreso_h1 import (
    auditar_aplicabilidad_h1,
    derivar_turno_reingreso_asof,
    evaluar_panel,
    preparar_contrato,
)

SCRIPT = Path(fachada.__file__)

FUNDOS = ["Aqu Anqa 1", "Aqu Anqa 4", "Aqu Anqa 3", "Aqu Anqa 2"]


def _run76_sintetico() -> tuple[pd.DataFrame, pd.DataFrame]:
    macro: list[dict] = []
    r09: list[dict] = []
    for semana in range(13, 34):
        objetivo = pd.Timestamp.fromisocalendar(2026, semana, 1)
        emision = objetivo - pd.Timedelta(days=7)
        for lote_id, fundo in enumerate(FUNDOS, start=1):
            real = float(100 + 5 * semana + lote_id)
            base = {
                "campania": "C2026",
                "fecha_emision": emision,
                "fecha_objetivo": objetivo,
                "horizonte_semanas": 1,
                "lote_id": lote_id,
                "fundo": fundo,
                "modulo": f"M{lote_id:02d}",
                "real_kg": real,
            }
            macro.append({**base, "p50_kg": real * 0.9, "componentes": {}})
            emitio = not (semana == 14 and lote_id in (1, 2))
            r09.append(
                {
                    **base,
                    "p50_kg": real * 1.05 if emitio else 0.0,
                    "componentes": {"emitio_prediccion": emitio},
                }
            )
    return pd.DataFrame(macro), pd.DataFrame(r09)


def _h01() -> pd.DataFrame:
    filas: list[dict] = []
    for lote_id in range(1, 5):
        for fecha in pd.date_range("2026-01-05", "2026-08-24", freq="14D"):
            filas.append(
                {
                    "campania": "C2026",
                    "lote_id": lote_id,
                    "fecha": fecha,
                    "turno": f"T{lote_id:02d}",
                    "kg": float(10 * lote_id),
                }
            )
    return pd.DataFrame(filas)


def test_run76_h1_bloquea_redistribucion_y_no_selecciona_configuracion():
    macro, r09 = _run76_sintetico()
    resultado = evaluar_panel(macro, r09, _h01())

    assert resultado["aplicabilidad"]["aplicable"] is False
    assert resultado["aplicabilidad"]["max_horizontes_por_emision_lote"] == 1
    assert resultado["seleccion"]["configuracion_seleccionada"] is None
    prueba = resultado["seleccion"]["demostracion_funcion_pura"]
    assert prueba["todas_identicas_a_macro"] is True
    assert prueba["cambio_max_abs_kg"] == pytest.approx(0.0)
    assert resultado["metricas"]["holdout_s31_s33"]["semanas"] == [31, 32, 33]


def test_turno_y_reingreso_solo_usan_h01_anterior_a_cada_emision():
    macro, r09 = _run76_sintetico()
    contrato = preparar_contrato(macro, r09)
    original = derivar_turno_reingreso_asof(contrato, _h01())

    mutado = _h01()
    futuro = pd.DataFrame(
        [
            {
                "campania": "C2026",
                "lote_id": 1,
                "fecha": pd.Timestamp("2026-12-31"),
                "turno": "FUTURO",
                "kg": 9_999_999.0,
            }
        ]
    )
    mutado = pd.concat([mutado, futuro], ignore_index=True)
    posterior = derivar_turno_reingreso_asof(contrato, mutado)

    pd.testing.assert_series_equal(original.turno, posterior.turno)
    pd.testing.assert_series_equal(original.dias_reingreso, posterior.dias_reingreso)
    pd.testing.assert_series_equal(
        original.fecha_ultima_cosecha_asof,
        posterior.fecha_ultima_cosecha_asof,
    )


def test_r09_condicionado_reporta_su_cobertura_y_no_convierte_ausencias_en_cero():
    macro, r09 = _run76_sintetico()
    resultado = evaluar_panel(macro, r09, _h01())
    completo = resultado["metricas"]["completo_s13_s33"]

    cobertura = completo["r09_condicionado"]["cobertura"]
    assert cobertura["filas_lote_disponibles"] == 82
    assert cobertura["filas_lote_totales"] == 84
    assert cobertura["cobertura_filas_lote"] == pytest.approx(82 / 84)
    assert completo["r09_condicionado"]["empresa_semana"]["wape"] == pytest.approx(0.05)
    assert completo["macro"]["empresa_semana"]["wape"] == pytest.approx(0.10)


def test_auditoria_exige_dos_horizontes_del_mismo_snapshot_para_aplicar():
    macro, r09 = _run76_sintetico()
    contrato = preparar_contrato(macro, r09)
    auditoria = auditar_aplicabilidad_h1(contrato)

    assert auditoria["grupos_redistribuibles"] == 0
    assert auditoria["cobertura_grupos_redistribuibles"] == 0.0
    assert "al menos dos horizontes" in auditoria["razon_bloqueo"]


def test_fachada_conserva_aliases_publicos_privados_identidad_y_firma():
    nombres_callable = (
        "ConfiguracionTurnoTemporal",
        "aplicar_turno_reingreso_candidate",
        "_normalizar_fundo",
        "_emitio_r09",
        "leer_fuentes",
        "preparar_contrato",
        "derivar_turno_reingreso_asof",
        "auditar_aplicabilidad_h1",
        "_rejilla_configuraciones",
        "demostrar_noop_h1",
        "_metricas_agregadas",
        "_cobertura",
        "_evaluar_split",
        "_keyset_sha256",
        "evaluar_panel",
        "ejecutar",
    )
    for nombre in nombres_callable:
        alias = getattr(fachada, nombre)
        implementacion = getattr(servicio, nombre)
        assert alias is implementacion
        assert inspect.signature(alias) == inspect.signature(implementacion)

    for nombre in (
        "RUN_ID",
        "CAMPANIA",
        "SEMANA_INICIAL",
        "SEMANA_FINAL",
        "SEMANA_DESARROLLO_FINAL",
        "CIERRE_CERTIFICADO",
        "CONTRACT_ID",
        "CLAVE_LOTE",
        "MAPEO_FUNDO",
        "escribir_json_reproducible",
        "postgres_dsn",
    ):
        assert getattr(fachada, nombre) is getattr(servicio, nombre)


def test_fachada_cli_conserva_serializacion_y_ruta_historicas(tmp_path, monkeypatch, capsys):
    salida = tmp_path / "resultado" / "screening.json"
    resultado = {
        "veredicto": "BLOQUEADO",
        "evaluation_contract": {"id": "run76-c2026-h1-s13-s33-closed"},
        "aplicabilidad": {"aplicable": False},
        "feature_turno_reingreso_asof": {"cobertura_filas_lote": 0.5},
        "metricas": {"completo_s13_s33": {"macro": {}}},
    }
    llamadas = []

    def fake_ejecutar():
        llamadas.append(True)
        return resultado

    monkeypatch.setattr(fachada, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(
        sys,
        "argv",
        ["screening_turno_reingreso_h1", "--salida", str(salida)],
    )

    assert fachada.main() == 0
    assert llamadas == [True]
    assert json.loads(salida.read_text(encoding="utf-8")) == resultado
    assert json.loads(capsys.readouterr().out)["contrato"] == resultado["evaluation_contract"]


def test_fachada_es_compuerta_ast_sin_logica_de_negocio():
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
        if isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
    ]
    assert not [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
    ]
