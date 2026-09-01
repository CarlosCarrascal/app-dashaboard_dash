"""Contratos de compatibilidad de la fachada ``analitica.cli``."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

from analitica import cli
from analitica.interfaces.commands import bhattacharya, common, operational, relations, torneo


def _subcomandos(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    accion = next(
        accion
        for accion in parser._actions
        if isinstance(accion, argparse._SubParsersAction)
    )
    return accion.choices


def test_parser_conserva_todos_los_subcomandos_y_el_entrypoint() -> None:
    parser = cli.parser()

    assert parser.prog == "aquanqa-analytics"
    subcomandos = _subcomandos(parser)
    assert set(subcomandos) == {
        "relations",
        "backtest",
        "train",
        "project",
        "export",
        "bhattacharya",
        "validate-operational",
        "operational-project",
    }
    assert subcomandos["relations"].parse_args([]).func is relations.ejecutar_relaciones
    assert subcomandos["backtest"].parse_args([]).func is torneo.ejecutar_backtest
    assert subcomandos["train"].parse_args([]).func is torneo.ejecutar_train
    assert subcomandos["project"].parse_args([]).func is torneo.ejecutar_project
    assert subcomandos["export"].parse_args([]).func is torneo.ejecutar_export
    assert subcomandos["bhattacharya"].parse_args([]).func is bhattacharya.ejecutar_bhattacharya
    assert (
        subcomandos["validate-operational"].parse_args([]).func
        is operational.ejecutar_validar_operativo
    )
    assert (
        subcomandos["operational-project"].parse_args(["--fecha-emision", "2026-08-28"]).func
        is operational.ejecutar_project_operativo
    )


def test_parser_conserva_argumentos_de_project_y_operacion() -> None:
    parser = cli.parser()

    project = parser.parse_args(
        [
            "project",
            "--source",
            "postgres",
            "--no-persist",
            "--corte-asof",
            "2026-08-01",
            "--modelo-proyeccion",
            "R09_publicado",
            "--horizontes",
            "1,2,6",
            "--escenario-frutos-pct",
            "5",
            "--open-meteo-lat",
            "-12.1",
            "--open-meteo-lon",
            "-77.0",
        ]
    )
    assert project.comando == "project"
    assert project.source == "postgres"
    assert project.no_persist is True
    assert project.corte_asof == "2026-08-01"
    assert project.modelo_proyeccion == "R09_publicado"
    assert project.horizontes == "1,2,6"
    assert project.escenario_frutos_pct == 5.0
    assert project.open_meteo_lat == -12.1
    assert project.open_meteo_lon == -77.0

    operational_project = parser.parse_args(
        [
            "operational-project",
            "--root",
            "C:/datos",
            "--fecha-emision",
            "2026-08-28",
            "--fuente-parametros",
            "excel",
            "--no-persist",
        ]
    )
    assert operational_project.comando == "operational-project"
    assert operational_project.root == "C:/datos"
    assert operational_project.fecha_emision == "2026-08-28"
    assert operational_project.fuente_parametros == "excel"
    assert operational_project.no_persist is True

    integrado = parser.parse_args(
        [
            "project",
            "--modelo-proyeccion",
            "HibridoGaussEstado_v1",
            "--incluir-gauss-estado",
        ]
    )
    assert integrado.modelo_proyeccion == "HibridoGaussEstado_v1"
    assert integrado.incluir_gauss_estado is True


def test_fachada_reexporta_handlers_y_utilidades_historicas() -> None:
    assert cli.ejecutar_relaciones is relations.ejecutar_relaciones
    assert cli.ejecutar_backtest is torneo.ejecutar_backtest
    assert cli.ejecutar_train is torneo.ejecutar_train
    assert cli.ejecutar_project is torneo.ejecutar_project
    assert cli.ejecutar_export is torneo.ejecutar_export
    assert cli.ejecutar_validar_operativo is operational.ejecutar_validar_operativo
    assert cli.ejecutar_project_operativo is operational.ejecutar_project_operativo
    assert cli.ejecutar_bhattacharya is bhattacharya.ejecutar_bhattacharya
    assert cli._torneo is torneo._torneo
    assert cli._repositorio is common._repositorio
    assert cli._registrar_inicio is common._registrar_inicio
    assert cli._salida is common._salida
    assert cli._raiz_operativa is common._raiz_operativa
    assert cli._parsear_horizontes is common._parsear_horizontes


def test_registrar_inicio_conserva_orden_snapshot_y_run() -> None:
    eventos: list[str] = []

    class RepositorioFalso:
        def snapshot(self, datos):
            eventos.append("snapshot")
            return "snapshot-1"

        def crear_run(self, snapshot_id, tipo, config, mlflow_id):
            eventos.append("run")
            assert snapshot_id == "snapshot-1"
            return "run-1"

    assert common._registrar_inicio(RepositorioFalso(), object(), "project", {}, None) == (
        "snapshot-1",
        "run-1",
    )
    assert eventos == ["snapshot", "run"]


def test_main_conserva_error_controlado_y_codigo_no_cero(capsys) -> None:
    codigo = cli.main(["validate-operational"])

    assert codigo == 1
    assert "ERROR ValueError:" in capsys.readouterr().err


def test_main_devuelve_el_codigo_del_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_args) -> int:
        return 7

    class ParserFalso:
        def parse_args(self, _argv):
            return SimpleNamespace(func=handler)

    monkeypatch.setattr(cli, "parser", lambda: ParserFalso())

    assert cli.main(["ignored"]) == 7


def test_parser_respeta_reemplazo_historico_de_un_handler(monkeypatch) -> None:
    def handler(_args) -> int:
        return 0

    monkeypatch.setattr(cli, "ejecutar_bhattacharya", handler)

    subcomandos = _subcomandos(cli.parser())

    assert subcomandos["bhattacharya"].parse_args([]).func is handler
