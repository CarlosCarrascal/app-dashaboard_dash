from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from analitica.aplicacion.servicios import persistir_nowcast_cierre_adaptativo as service
from analitica.interfaces.scripts import persistir_nowcast_cierre_adaptativo as facade


def _salida_sintetica() -> pd.DataFrame:
    filas: list[dict[str, object]] = []
    for fundo, factor in (
        ("Arena", 1.0),
        ("Ayllu", 0.8),
        ("Kawsay", 1.2),
        ("Quri", 0.9),
    ):
        real = 100.0 * factor
        filas.append(
            {
                "campania": "C2026",
                "fecha_objetivo": pd.Timestamp("2026-08-10"),
                "fecha_corte_asof": pd.Timestamp("2026-08-11"),
                "fundo_operativo": fundo,
                "macro_kg": real * 1.1,
                "montue_kg": real * 0.4,
                "real_kg": real,
                "candidate_kg": real * 1.02,
                "r09_presemana_kg": real * 0.95,
                "r09_misma_semana_kg": real * 1.03,
                "estado_nowcast": "calculado",
                "recon_total_empresa_kg": 400.0,
            }
        )
    return pd.DataFrame(filas)


def _metricas_sinteticas() -> dict[str, object]:
    return {
        "configuration_id": "synthetic-config",
        "candidate": {
            "wape": 0.02,
            "bias": 0.01,
            "mae_kg": 4.0,
            "n_weeks": 1,
            "real_kg": 400.0,
        },
        "macro": {
            "wape": 0.10,
            "bias": 0.10,
            "mae_kg": 20.0,
            "n_weeks": 1,
            "real_kg": 400.0,
        },
    }


def _archivos_fuente(tmp_path: Path) -> tuple[Path, Path, Path]:
    paths = (tmp_path / "artifact.json", tmp_path / "real.accdb", tmp_path / "r09.accdb")
    paths[0].write_text("{}", encoding="utf-8")
    paths[1].write_bytes(b"real")
    paths[2].write_bytes(b"r09")
    return paths


def test_fachada_conserva_aliases_publicos_privados_y_firmas() -> None:
    nombres = (
        "MODELO",
        "VERSION",
        "CAMPAIGN",
        "FUNDOS",
        "ROOT",
        "ARTEFACTO_DEFAULT",
        "REAL_ACCESS_DEFAULT",
        "R09_ACCESS_DEFAULT",
        "MACRO_RUN_HISTORY",
        "MACRO_RUN_S34",
        "build_candidate",
        "persist",
    )
    nombres_privados = (
        "_sha256_archivo",
        "_json_hash",
        "_records_hash",
        "_normalizar_detalle_artifact",
        "_append_latest_closed_week",
        "_metric",
        "_bootstrap",
        "_publication_rows",
        "_baseline_release_hashes",
    )

    for nombre in (*nombres, *nombres_privados):
        assert getattr(facade, nombre) is getattr(service, nombre), nombre

    for nombre in (*nombres_privados, "build_candidate", "persist"):
        assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
            getattr(service, nombre)
        ), nombre

    assert inspect.signature(facade.main) == inspect.Signature(
        [
            inspect.Parameter(
                "argv",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation="list[str] | None",
                default=None,
            )
        ],
        return_annotation="int",
    )


def test_fachada_y_servicio_producen_el_mismo_reporte_dry_run(tmp_path) -> None:
    artifact, real_access, r09_access = _archivos_fuente(tmp_path)
    argumentos = {
        "artifact": artifact,
        "real_access": real_access,
        "r09_access": r09_access,
        "apply": False,
    }

    reporte_facade = facade.persist(_salida_sintetica(), _metricas_sinteticas(), **argumentos)
    reporte_service = service.persist(_salida_sintetica(), _metricas_sinteticas(), **argumentos)

    assert reporte_facade == reporte_service


def test_dry_run_no_escribe_en_repositorio_ni_conexion(tmp_path, monkeypatch) -> None:
    artifact, real_access, r09_access = _archivos_fuente(tmp_path)
    escrituras: list[str] = []

    class RepositorioFalso:
        def __init__(self, *_args, **_kwargs):
            escrituras.append("repo_init")

    def connect_falso(*_args, **_kwargs):
        escrituras.append("connect")
        raise AssertionError("dry-run no debe abrir una conexión")

    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(service.psycopg, "connect", connect_falso)
    monkeypatch.setattr(
        service.settings,
        "postgres_dsn",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run no debe leer DSN")),
    )

    resultado = service.persist(
        _salida_sintetica(),
        _metricas_sinteticas(),
        artifact=artifact,
        real_access=real_access,
        r09_access=r09_access,
        apply=False,
    )

    assert resultado["status"] == "dry_run_passed"
    assert resultado["apply"] is False
    assert escrituras == []


class _CursorFalso:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self.events = events
        self.query = ""

    def __enter__(self) -> _CursorFalso:
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, params=None) -> None:
        self.query = query
        normalized = " ".join(query.split())
        self.events.append(("sql", normalized))

    def fetchone(self):
        if "dataset_snapshot" in self.query:
            return (101,)
        if "INSERT INTO analytics.forecast_run" in self.query:
            return (202,)
        if "evaluation_contract" in self.query:
            return (303,)
        if "INSERT INTO analytics.model_series_release" in self.query:
            return (404,)
        if "SELECT release_id, run_id" in self.query:
            return None
        raise AssertionError(f"fetchone inesperado: {self.query}")

    def fetchall(self):
        assert "model_series_release" in self.query
        return [("C2026", "MacroLegacy_v1", "historico", "baseline-hash")]


class _ConexionFalsa:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self.events = events

    def __enter__(self) -> _ConexionFalsa:
        return self

    def __exit__(self, exc_type, *_args) -> None:
        self.events.append(("commit" if exc_type is None else "rollback", None))
        return None

    def cursor(self) -> _CursorFalso:
        return _CursorFalso(self.events)


def _tipo_evento(evento: tuple[str, object]) -> str:
    if evento[0] != "sql":
        return evento[0]
    query = str(evento[1])
    if query.startswith("SELECT campania, modelo, uso"):
        return "baseline_hashes"
    if query.startswith("SELECT release_id, run_id"):
        return "idempotency_check"
    if query.startswith("INSERT INTO analytics.dataset_snapshot"):
        return "snapshot"
    if query.startswith("INSERT INTO analytics.forecast_run"):
        return "run_start"
    if query.startswith("INSERT INTO analytics.evaluation_contract"):
        return "evaluation_contract"
    if query.startswith("UPDATE analytics.model_series_release"):
        return "withdraw_previous_release"
    if query.startswith("INSERT INTO analytics.model_series_release"):
        return "release"
    if query.startswith("UPDATE analytics.forecast_run"):
        return "run_success"
    raise AssertionError(f"SQL no clasificado: {query}")


def test_apply_conserva_orden_de_persistencia_y_finaliza_run_fallido(
    tmp_path, monkeypatch
) -> None:
    artifact, real_access, r09_access = _archivos_fuente(tmp_path)
    events: list[tuple[str, object]] = []

    class RepositorioFalso:
        def __init__(self, *_args, **_kwargs):
            events.append(("repo_init", None))

        def guardar_nowcast_semanal(self, run_id, rows) -> None:
            events.append(("guardar_nowcast_semanal", (run_id, len(rows))))

        def guardar_metricas(self, run_id, metrics) -> None:
            events.append(("guardar_metricas", (run_id, len(metrics))))

        def finalizar_run(self, run_id, estado, error) -> None:
            events.append(("finalizar_run", (run_id, estado, error)))

    conexiones: list[_ConexionFalsa] = []

    def connect_falso(_dsn):
        conexion = _ConexionFalsa(events)
        conexiones.append(conexion)
        return conexion

    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")
    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(service.psycopg, "connect", connect_falso)

    resultado = service.persist(
        _salida_sintetica(),
        _metricas_sinteticas(),
        artifact=artifact,
        real_access=real_access,
        r09_access=r09_access,
        apply=True,
    )

    tipos = [_tipo_evento(evento) for evento in events]
    assert tipos == [
        "repo_init",
        "baseline_hashes",
        "idempotency_check",
        "snapshot",
        "run_start",
        "commit",
        "guardar_nowcast_semanal",
        "guardar_metricas",
        "evaluation_contract",
        "withdraw_previous_release",
        "release",
        "run_success",
        "baseline_hashes",
        "commit",
    ]
    assert resultado["status"] == "published_historical_nowcast"
    assert resultado["baseline_release_hashes_unchanged"] is True
    assert len(conexiones) == 2

    events.clear()
    monkeypatch.setattr(
        RepositorioFalso,
        "guardar_nowcast_semanal",
        lambda self, run_id, rows: (_ for _ in ()).throw(RuntimeError("fallo sintetico")),
    )

    with pytest.raises(RuntimeError, match="fallo sintetico"):
        service.persist(
            _salida_sintetica(),
            _metricas_sinteticas(),
            artifact=artifact,
            real_access=real_access,
            r09_access=r09_access,
            apply=True,
        )

    assert any(
        evento[0] == "finalizar_run" and evento[1][0:2] == (202, "failed")
        for evento in events
    )
