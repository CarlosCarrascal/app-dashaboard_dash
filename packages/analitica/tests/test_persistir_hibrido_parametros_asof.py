from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from analitica.aplicacion.servicios import persistir_hibrido_parametros_asof as service
from analitica.interfaces.scripts import persistir_hibrido_parametros_asof as facade


def test_flujo_se_divide_por_responsabilidad_sin_importar_la_fachada_historica() -> None:
    nombres = {
        "configuracion": "persistir_hibrido_parametros_asof_configuracion.py",
        "lectura": "persistir_hibrido_parametros_asof_lectura.py",
        "candidate": "persistir_hibrido_parametros_asof_candidate.py",
        "preflight": "persistir_hibrido_parametros_asof_preflight.py",
        "persistencia": "persistir_hibrido_parametros_asof_persistencia.py",
        "orquestacion": "persistir_hibrido_parametros_asof_orquestacion.py",
    }
    directorio = Path(service.__file__).parent
    for nombre in nombres.values():
        ruta = directorio / nombre
        assert ruta.exists(), nombre
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        imports_historicos = [
            nodo
            for nodo in ast.walk(arbol)
            if isinstance(nodo, (ast.Import, ast.ImportFrom))
            and (
                (isinstance(nodo, ast.ImportFrom) and nodo.module)
                or isinstance(nodo, ast.Import)
            )
            and any(
                alias.name.startswith("analitica.interfaces.scripts")
                for alias in (
                    nodo.names
                    if isinstance(nodo, ast.Import)
                    else [ast.alias(name=nodo.module or "", asname=None)]
                )
            )
        ]
        assert not imports_historicos, nombre

    assert len(Path(service.__file__).read_text(encoding="utf-8").splitlines()) < 400
    assert "ejecutar" in {
        nodo.name
        for nodo in ast.walk(
            ast.parse(
                (directorio / nombres["orquestacion"]).read_text(encoding="utf-8")
            )
        )
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_fachada_y_servicio_conservan_aliases_firmas_y_argumentos() -> None:
    aliases = (
        "BASELINES_PERMITIDOS",
        "BASELINES_REQUERIDOS",
        "EXIT_CONTRACT_REJECTED",
        "EXIT_EXECUTION_ERROR",
        "EXIT_OK",
        "MODELO_MACRO",
        "MODELO_OCURRENCIA",
        "MODELO_R09",
        "NOMBRE_MODELO",
        "PROJECT_ROOT",
        "VERSION_MODELO",
        "CacheCandidate",
        "construir_candidato",
        "ejecutar",
        "escribir_json_reproducible",
        "json_reproducible",
    )
    for nombre in aliases:
        assert getattr(facade, nombre) is getattr(service, nombre), nombre

    for nombre in (
        "_argumentos",
        "_parsear_mapa",
        "_validar_referencias",
        "_firma_directorio",
        "_emisiones_desde_forecast",
        "_cargar_priors_excel",
        "_completar_candidato",
        "_candidate_cache",
        "_calidad_preflight",
        "construir_candidato",
        "ejecutar",
    ):
        assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
            getattr(service, nombre)
        ), nombre

    argv = [
        "--campania",
        "C2026",
        "--horizonte-semanas",
        "12",
        "--max-cortes",
        "3",
        "--excel-root",
        "excel",
        "--baseline-run-id",
        "MacroLegacy_v1=76",
        "--expected-baseline-hash",
        "MacroLegacy_v1=hash",
        "--expected-keyset-hash",
        "keyset",
        "--preflight",
        "--dry-run",
        "--cache-dir",
        "cache",
        "--no-cache",
        "--output-json",
        "result.json",
    ]
    assert vars(facade._argumentos(argv)) == vars(service._argumentos(argv))


def test_dry_run_no_escribe_en_repositorio_y_conserva_contrato(monkeypatch) -> None:
    referencias = {"MacroLegacy_v1": 76}
    emisiones = pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "fecha_emision": pd.to_datetime(["2026-04-06", "2026-05-04"]),
        }
    )
    datos = SimpleNamespace(
        cosecha=pd.DataFrame(columns=["campania", "fecha", "kg"]),
    )
    contrato = SimpleNamespace(
        evaluation_contract_id=42,
        keyset_sha256="keyset-sha256",
        closed_calendar_sha256="calendar-sha256",
        cerrado_hasta=pd.Timestamp("2026-06-30"),
        source_hashes={"MacroLegacy_v1": "baseline-sha256"},
    )
    micro = pd.DataFrame({"modelo": [service.NOMBRE_MODELO], "p50_kg": [100.0]})
    full = micro.copy()
    snapshots = pd.DataFrame()
    llamadas_datos: list[tuple[str, object]] = []
    escrituras: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, *_args, **_kwargs):
            escrituras.append(("init",))

        def __getattr__(self, nombre):
            def registrar(*args, **kwargs):
                escrituras.append((nombre, args, kwargs))

            return registrar

    def cache_falso(_datos, _emisiones, *, fase, **_kwargs):
        llamadas_datos.append(("cache", fase))
        return (
            (micro if fase == "micro" else full).copy(),
            snapshots.copy(),
            {"fase": fase, "cache_hit": False},
        )

    reporte = {
        "estado": "passed",
        "exit_code": service.EXIT_OK,
        "contratos": [],
        "gates": [],
        "baseline_hashes": {"MacroLegacy_v1": "baseline-sha256"},
        "keyset_sha256": "keyset-sha256",
        "closed_calendar_sha256": "calendar-sha256",
    }
    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-de-prueba")
    monkeypatch.setattr(service, "cargar_contrato_baselines", lambda *_args: contrato)
    monkeypatch.setattr(
        service,
        "cargar_o_construir_snapshot_datos",
        lambda *_args, **_kwargs: (datos, {"snapshot": "doble"}),
    )
    monkeypatch.setattr(
        service,
        "cargar_datos",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no cargar fuente")),
    )
    monkeypatch.setattr(
        service,
        "_emisiones_desde_forecast",
        lambda *_args, **_kwargs: emisiones.copy(),
    )
    monkeypatch.setattr(
        service,
        "seleccionar_emisiones_micro_desde_fuente",
        lambda *_args, **_kwargs: emisiones.iloc[[0]].copy(),
    )
    monkeypatch.setattr(
        service,
        "cargar_baselines_por_run",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(service, "_candidate_cache", cache_falso)
    monkeypatch.setattr(service, "evaluar_preflight", lambda *_args, **_kwargs: reporte.copy())
    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)

    resultado_facade = facade.ejecutar(
        campania="C2026",
        referencias=referencias,
        hashes_esperados={"MacroLegacy_v1": "baseline-sha256"},
        expected_keyset_hash="keyset-sha256",
        horizonte=10,
        max_cortes=0,
        preflight_only=False,
        dry_run=True,
        cache_dir=None,
    )
    resultado_service = service.ejecutar(
        campania="C2026",
        referencias=referencias,
        hashes_esperados={"MacroLegacy_v1": "baseline-sha256"},
        expected_keyset_hash="keyset-sha256",
        horizonte=10,
        max_cortes=0,
        preflight_only=False,
        dry_run=True,
        cache_dir=None,
    )

    assert resultado_facade == resultado_service
    assert resultado_facade["estado"] == "passed"
    assert resultado_facade["exit_code"] == service.EXIT_OK
    assert resultado_facade["persistido"] is False
    assert llamadas_datos == [("cache", "micro"), ("cache", "full")] * 2
    assert escrituras == []
