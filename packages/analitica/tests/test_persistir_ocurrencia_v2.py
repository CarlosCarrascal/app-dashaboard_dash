from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pandas as pd
import pytest

from analitica.scripts import persistir_ocurrencia_v2 as facade
from analitica.servicios import persistir_ocurrencia_v2 as service

SCRIPT = Path(facade.__file__)


def _fuentes_sinteticas() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    filas = []
    fechas_objetivo = pd.to_datetime(["2026-01-05", "2026-01-12"])
    fechas_emision = pd.to_datetime(["2025-12-29", "2026-01-05"])
    for lote_id, real_kg in ((101, (100.0, 80.0)), (102, (60.0, 40.0))):
        for fecha_emision, fecha_objetivo, real in zip(
            fechas_emision, fechas_objetivo, real_kg, strict=True
        ):
            filas.append(
                {
                    "campania": "C2026",
                    "empresa": "Aqu Anqa",
                    "fundo": "Arena",
                    "modulo": "M01",
                    "lote": f"L{lote_id}",
                    "lote_id": lote_id,
                    "fecha_emision": fecha_emision,
                    "fecha_objetivo": fecha_objetivo,
                    "horizonte_semanas": 1,
                    "real_kg": real,
                    "p50_kg": real * 0.9,
                    "version_fuente": "macro-source",
                }
            )
    macro = pd.DataFrame(filas)
    r09 = macro.loc[[0, 1], [*service.CLAVES, "fecha_emision", "p50_kg", "version_fuente"]].copy()
    r09["p50_kg"] = r09["p50_kg"] * 1.1
    r09["version_fuente"] = "r09-source"
    return macro, r09, {"C2026": "2026-01-31"}


def _doblar_calculo(monkeypatch) -> None:
    def leer_fuentes():
        macro, r09, cierres = _fuentes_sinteticas()
        return macro.copy(), r09.copy(), cierres.copy()

    def replay_v1(panel):
        salida = panel.copy()
        salida["p50_kg"] = salida["p50_kg"] + 3.0
        salida["version_fuente"] = "v1-source"
        return salida, pd.DataFrame()

    def replay_v2(panel):
        salida = panel.copy()
        salida["p50_kg"] = salida["p50_kg"] + 5.0
        salida["modelo"] = service.MODELO_V2
        salida["version_modelo"] = service.VERSION_V2
        salida["version_fuente"] = "v2-source"
        salida["componentes"] = [{} for _ in range(len(salida))]
        return salida, pd.DataFrame()

    monkeypatch.setattr(service, "_leer_fuentes", leer_fuentes)
    monkeypatch.setattr(service, "ejecutar_replay_hibrido_ocurrencia", replay_v1)
    monkeypatch.setattr(service, "ejecutar_replay_hibrido_ocurrencia_v2", replay_v2)
    monkeypatch.setattr(
        service,
        "metricas_cobertura_operacional",
        lambda _tabla: {
            "wape_operacional": 0.11,
            "wape_condicionado": 0.12,
            "cobertura_lotes": 1.0,
            "cobertura_volumen": 1.0,
            "volumen_real_kg": 280.0,
        },
    )
    monkeypatch.setattr(
        service,
        "metricas_pronostico",
        lambda semanal: pd.DataFrame(
            [
                {
                    "modelo": semanal.modelo.iloc[0],
                    "banda_horizonte": "operativo",
                    "n": len(semanal),
                    "wape": 0.13,
                    "mase": 0.14,
                    "rmsse": 0.15,
                    "mae_kg": 0.16,
                    "sesgo_pct": 0.17,
                }
            ]
        ),
    )


def test_fachada_conserva_aliases_firmas_y_json() -> None:
    aliases = (
        "argparse",
        "np",
        "pd",
        "settings",
        "RepositorioAnalytics",
        "MODELO_V1",
        "VERSION_V1",
        "ejecutar_replay_hibrido_ocurrencia",
        "MODELO_V2",
        "VERSION_V2",
        "ejecutar_replay_hibrido_ocurrencia_v2",
        "metricas_cobertura_operacional",
        "metricas_pronostico",
        "MODELO_R09",
        "MODELO_MACRO",
        "MODELO_NAIVE",
        "SNAPSHOT_ID",
        "RUNS_ORIGEN",
        "CLAVES",
        "construir_corrida",
        "persistir",
        "_argumentos",
        "_leer_fuentes",
        "_expandir_referencia",
        "_expandir_v1",
        "_naive",
        "_contrato",
        "_metricas_modelo",
    )
    for nombre in aliases:
        assert getattr(facade, nombre) is getattr(service, nombre), nombre
        if callable(getattr(facade, nombre)):
            assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
                getattr(service, nombre)
            ), nombre
    assert facade.json.__name__ == "json"


def test_construccion_sintetica_conserva_paridad_y_universo_comun(monkeypatch) -> None:
    _doblar_calculo(monkeypatch)

    pred_fachada, metricas_fachada, resumen_fachada = facade.construir_corrida()
    pred_servicio, metricas_servicio, resumen_servicio = service.construir_corrida()

    pd.testing.assert_frame_equal(pred_fachada, pred_servicio)
    pd.testing.assert_frame_equal(metricas_fachada, metricas_servicio)
    assert resumen_fachada == resumen_servicio
    assert resumen_servicio["snapshot_id"] == 40
    assert resumen_servicio["runs_origen"] == {"C2024": 71, "C2025": 72, "C2026": 73}

    claves_base = set(map(tuple, _fuentes_sinteticas()[0][service.CLAVES].to_numpy()))
    assert set(pred_servicio.modelo) == {
        service.MODELO_R09,
        service.MODELO_MACRO,
        service.MODELO_V1,
        service.MODELO_V2,
        service.MODELO_NAIVE,
    }
    for modelo in resumen_servicio["modelos"]:
        claves_modelo = set(
            map(
                tuple,
                pred_servicio.loc[pred_servicio.modelo.eq(modelo), service.CLAVES].to_numpy(),
            )
        )
        assert claves_modelo == claves_base

    referencia_faltante = pred_servicio.loc[
        pred_servicio.modelo.eq(service.MODELO_R09) & pred_servicio.lote_id.eq(102)
    ].iloc[0]
    assert referencia_faltante.p50_kg == 0.0
    assert bool(referencia_faltante.emitio_prediccion) is False


def test_formulas_historicas_de_referencia_y_naive() -> None:
    macro, r09, _ = _fuentes_sinteticas()
    referencia = service._expandir_referencia(macro, r09, service.MODELO_R09)
    naive = service._naive(macro)

    assert referencia.loc[referencia.lote_id.eq(102), "p50_kg"].tolist() == [0.0, 0.0]
    assert referencia.loc[
        referencia.lote_id.eq(102), "emitio_prediccion"
    ].tolist() == [False, False]
    assert naive.loc[naive.lote_id.eq(101), "p50_kg"].tolist() == [0.0, 100.0]
    assert naive.loc[naive.lote_id.eq(102), "p50_kg"].tolist() == [0.0, 60.0]
    assert naive.version_modelo.eq("ultimo_real_lote_v1").all()


def test_dry_run_no_instancia_ni_escribe_en_repositorio(monkeypatch) -> None:
    resumen = {"snapshot_id": service.SNAPSHOT_ID, "runs_origen": service.RUNS_ORIGEN.copy()}
    eventos: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, *_args, **_kwargs):
            eventos.append(("init",))

        def __getattr__(self, nombre):
            def registrar(*args, **kwargs):
                eventos.append((nombre, args, kwargs))

            return registrar

    monkeypatch.setattr(
        service,
        "construir_corrida",
        lambda: (pd.DataFrame(), pd.DataFrame(), resumen),
    )
    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(
        service.settings,
        "postgres_dsn",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run no debe pedir DSN")),
    )

    assert facade.persistir(dry_run=True) == resumen
    assert eventos == []


def test_persistencia_conserva_orden_y_finaliza_failed(monkeypatch) -> None:
    predicciones = pd.DataFrame({"modelo": [service.MODELO_MACRO]})
    metricas = pd.DataFrame({"modelo": [service.MODELO_MACRO]})
    resumen = {"snapshot_id": service.SNAPSHOT_ID}
    eventos: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, dsn):
            eventos.append(("init", dsn))

        def crear_run(self, *args):
            eventos.append(("crear_run", *args))
            return 901

        def guardar_predicciones(self, *args):
            eventos.append(("guardar_predicciones", *args))

        def guardar_metricas(self, *args):
            eventos.append(("guardar_metricas", *args))
            raise RuntimeError("fallo sintetico")

        def finalizar_run(self, *args):
            eventos.append(("finalizar_run", *args))

    monkeypatch.setattr(
        service,
        "construir_corrida",
        lambda: (predicciones, metricas, resumen.copy()),
    )
    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")

    with pytest.raises(RuntimeError, match="fallo sintetico"):
        service.persistir()

    assert [evento[0] for evento in eventos] == [
        "init",
        "crear_run",
        "guardar_predicciones",
        "guardar_metricas",
        "finalizar_run",
    ]
    assert eventos[-1] == ("finalizar_run", 901, "failed", "fallo sintetico")


def test_fachada_es_adaptador_cli_delgado() -> None:
    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    definiciones = [
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not any(
        isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
        for nodo in ast.walk(arbol)
    )
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
        for nodo in ast.walk(arbol)
    )
