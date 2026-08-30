"""Caracterización local de la fachada del repositorio, sin PostgreSQL real."""

from __future__ import annotations

import csv
import io
import json
from contextlib import contextmanager

import pandas as pd

from analitica.infraestructura.persistencia.artefactos import ArtefactosMixin
from analitica.infraestructura.persistencia.conexiones_snapshots import ConexionSnapshotsMixin
from analitica.infraestructura.persistencia.escenarios_decisiones import EscenariosDecisionesMixin
from analitica.infraestructura.persistencia.metricas_claims import MetricasClaimsMixin
from analitica.infraestructura.persistencia.repositorio import RepositorioAnalytics
from analitica.infraestructura.persistencia.runs_predicciones import RunsPrediccionesMixin


class _CursorCapturado:
    def __init__(self):
        self.executemany_calls = []
        self.copy_sql = None
        self.copy_capturado = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def executemany(self, sql, params):
        self.executemany_calls.append((sql, params))

    def copy(self, sql):
        self.copy_sql = sql
        self.copy_capturado = _CopyCapturado()
        return self.copy_capturado


class _CopyCapturado:
    def __init__(self):
        self.chunks = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def write(self, contenido):
        self.chunks.append(contenido)


class _ConexionCapturada:
    def __init__(self):
        self.cursor_capturado = _CursorCapturado()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_capturado


def test_la_fachada_expone_la_api_historica_desde_responsabilidades_fisicas():
    propietarios = {
        ConexionSnapshotsMixin: {
            "__init__",
            "conexion",
            "snapshot",
            "guardar_validacion_operativa",
            "resolver_lote_ids",
        },
        RunsPrediccionesMixin: {
            "crear_run",
            "finalizar_run",
            "guardar_predicciones",
            "guardar_nowcast_semanal",
        },
        MetricasClaimsMixin: {
            "guardar_metricas",
            "guardar_parametros_legacy",
            "guardar_metricas_comparacion",
            "guardar_claims",
            "guardar_evidencia_features",
            "guardar_pronostico_clima",
        },
        EscenariosDecisionesMixin: {
            "guardar_escenario",
            "cambiar_estado_escenario",
            "guardar_decisiones",
            "decisiones_vigentes",
        },
        ArtefactosMixin: {"guardar_calidad", "guardar_artifacto"},
    }

    for mixin, nombres in propietarios.items():
        for nombre in nombres:
            assert getattr(RepositorioAnalytics, nombre) is getattr(mixin, nombre)

    assert not {nombre for nombre in RepositorioAnalytics.__dict__ if not nombre.startswith("_")}


def test_metricas_conserva_sql_y_transaccion_sin_dsn_real():
    conexion = _ConexionCapturada()
    repositorio = RepositorioAnalytics("postgresql://captura-local")

    @contextmanager
    def conexion_falsa():
        yield conexion

    repositorio.conexion = conexion_falsa
    repositorio.guardar_metricas(
        11,
        pd.DataFrame(
            [
                {
                    "modelo": "R09",
                    "banda_horizonte": "h1",
                    "n": 3,
                    "campania": "C2026",
                    "fundo": "F1",
                    "horizonte_semanas": 1,
                    "wape": 0.2,
                    "base_plantas_evaluada": "real",
                }
            ]
        ),
    )

    assert len(conexion.cursor_capturado.executemany_calls) == 1
    sql, filas = conexion.cursor_capturado.executemany_calls[0]
    assert "INSERT INTO analytics.metric" in sql
    assert "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)" in sql
    assert filas[0][:9] == (11, "R09", "wape", 0.2, 3, "C2026", "F1", 1, "h1")
    assert '"base_plantas_evaluada": "real"' in filas[0][9]


def test_predicciones_conserva_contrato_csv_de_copy_y_componentes_extra():
    conexion = _ConexionCapturada()
    repositorio = RepositorioAnalytics("postgresql://captura-local")

    @contextmanager
    def conexion_falsa():
        yield conexion

    repositorio.conexion = conexion_falsa
    repositorio.guardar_predicciones(
        19,
        pd.DataFrame(
            [
                {
                    "modelo": "R09",
                    "version_modelo": "v1",
                    "campania": "C2026",
                    "fecha_emision": pd.Timestamp("2026-08-26"),
                    "fecha_objetivo": pd.Timestamp("2026-09-02"),
                    "horizonte_semanas": 1,
                    "p50_kg": 12.5,
                    "componentes": {"nota": "A, B"},
                    "metadato_extra": "línea, dos",
                }
            ]
        ),
    )

    assert "COPY analytics.prediction" in conexion.cursor_capturado.copy_sql
    assert "FORMAT CSV" in conexion.cursor_capturado.copy_sql
    filas = list(csv.reader(io.StringIO("".join(conexion.cursor_capturado.copy_capturado.chunks))))
    assert len(filas) == 1
    assert filas[0][0:4] == ["19", "R09", "v1", "C2026"]
    assert json.loads(filas[0][27]) == {
        "metadato_extra": "línea, dos",
        "nota": "A, B",
    }
