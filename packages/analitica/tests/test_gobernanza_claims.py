import json
from contextlib import contextmanager

import pandas as pd
import pytest

from analitica.proyeccion.persistencia import RepositorioAnalytics
from analitica.proyeccion.persistencia.repositorio import ClaimHistoryConflictError


class _Cursor:
    def __init__(self):
        self.calls = []
        self.rowcounts = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if self.rowcounts:
            self.rowcount = self.rowcounts.pop(0)


class _Conexion:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_obj


def test_guardar_claims_envia_un_valor_por_columna_sql():
    conexion = _Conexion()
    repositorio = RepositorioAnalytics("postgresql://prueba")

    @contextmanager
    def conexion_falsa():
        yield conexion

    repositorio.conexion = conexion_falsa
    claims = pd.DataFrame(
        [
            {
                "claim_id": "claim-1",
                "hipotesis_id": "H1",
                "hipotesis": "Poda",
                "referencias": ["fuente-1"],
                "clase_evidencia": "temporal",
                "estado": "consistente",
                "afirmacion": "La poda precede la floración.",
                "estimacion": 0.5,
                "intervalo_inferior": 0.1,
                "intervalo_superior": 0.9,
                "unidad": "rho",
                "n_efectivo": 12,
                "alcance": {"campania": "C2026"},
                "supuestos": ["as-of"],
                "limitaciones": ["observacional"],
            }
        ]
    )

    repositorio.guardar_claims(7, claims)

    assert len(conexion.cursor_obj.calls) == 2
    historial_sql, historial_params = conexion.cursor_obj.calls[0]
    vigente_sql, params = conexion.cursor_obj.calls[1]
    assert "analytics.evidence_claim_history" in historial_sql
    assert "ON CONFLICT (claim_id, run_id) DO UPDATE SET" in historial_sql
    assert (
        "WHERE historial.hipotesis_id IS NOT DISTINCT FROM EXCLUDED.hipotesis_id" in historial_sql
    )
    assert "historial.referencias IS NOT DISTINCT FROM EXCLUDED.referencias" in historial_sql
    assert "analytics.evidence_claim" in vigente_sql
    assert historial_params == params
    assert len(params) == 16
    assert params[:3] == ("claim-1", 7, "H1")
    assert params[3:] == (
        "Poda",
        "temporal",
        "consistente",
        "La poda precede la floración.",
        0.5,
        0.1,
        0.9,
        "rho",
        12,
        '{"campania": "C2026"}',
        '["as-of"]',
        '["observacional"]',
        '["fuente-1"]',
    )


def test_guardar_claims_no_doble_serializa_strings_json_de_generar_claims():
    conexion = _Conexion()
    repositorio = RepositorioAnalytics("postgresql://prueba")

    @contextmanager
    def conexion_falsa():
        yield conexion

    repositorio.conexion = conexion_falsa
    claims = pd.DataFrame(
        [
            {
                "claim_id": "claim-json-string",
                "hipotesis_id": "H1",
                "hipotesis": "Poda",
                "clase_evidencia": "temporal",
                "estado": "consistente",
                "afirmacion": "La poda precede la floración.",
                "estimacion": 0.5,
                "intervalo_inferior": 0.1,
                "intervalo_superior": 0.9,
                "unidad": "rho",
                "n_efectivo": 12,
                "alcance": '{"campania": "C2026", "modulos": 2}',
                "supuestos": '["as-of", "estacionalidad"]',
                "limitaciones": '["observacional"]',
                "referencias": '["fuente-1"]',
            }
        ]
    )

    repositorio.guardar_claims(7, claims)

    assert len(conexion.cursor_obj.calls) == 2
    params = conexion.cursor_obj.calls[1][1]
    assert json.loads(params[12]) == {"campania": "C2026", "modulos": 2}
    assert json.loads(params[13]) == ["as-of", "estacionalidad"]
    assert json.loads(params[14]) == ["observacional"]
    assert json.loads(params[15]) == ["fuente-1"]
    assert all(not isinstance(json.loads(params[indice]), str) for indice in range(12, 16))


def test_guardar_claims_historial_precede_upsert_en_dos_corridas():
    conexion = _Conexion()
    repositorio = RepositorioAnalytics("postgresql://prueba")

    @contextmanager
    def conexion_falsa():
        yield conexion

    repositorio.conexion = conexion_falsa
    claims = pd.DataFrame(
        [
            {
                "claim_id": "claim-1",
                "hipotesis_id": "H1",
                "hipotesis": "Poda",
                "clase_evidencia": "temporal",
                "estado": "consistente",
                "afirmacion": "La poda precede la floración.",
                "alcance": {"campania": "C2026"},
                "supuestos": ["as-of"],
                "limitaciones": ["observacional"],
                "referencias": ["fuente-1"],
            }
        ]
    )

    repositorio.guardar_claims(7, claims)
    repositorio.guardar_claims(8, claims)

    assert len(conexion.cursor_obj.calls) == 4
    for indice in (0, 2):
        historial_sql, historial_params = conexion.cursor_obj.calls[indice]
        vigente_sql, vigente_params = conexion.cursor_obj.calls[indice + 1]
        assert "evidence_claim_history" in historial_sql
        assert "ON CONFLICT (claim_id, run_id) DO UPDATE SET" in historial_sql
        assert (
            "WHERE historial.hipotesis_id IS NOT DISTINCT FROM EXCLUDED.hipotesis_id"
            in historial_sql
        )
        assert "evidence_claim_history" not in vigente_sql
        assert "ON CONFLICT (claim_id) DO UPDATE SET" in vigente_sql
        assert historial_params == vigente_params

    assert conexion.cursor_obj.calls[0][1][1] == 7
    assert conexion.cursor_obj.calls[2][1][1] == 8


def test_guardar_claims_reintento_de_la_misma_corrida_es_idempotente_en_historial():
    conexion = _Conexion()
    repositorio = RepositorioAnalytics("postgresql://prueba")

    @contextmanager
    def conexion_falsa():
        yield conexion

    repositorio.conexion = conexion_falsa
    claims = pd.DataFrame(
        [
            {
                "claim_id": "claim-reintento",
                "hipotesis": "Poda",
                "clase_evidencia": "temporal",
                "estado": "consistente",
                "afirmacion": "Afirmación",
            }
        ]
    )

    repositorio.guardar_claims(7, claims)
    repositorio.guardar_claims(7, claims)

    historiales = [
        sql for sql, _params in conexion.cursor_obj.calls if "evidence_claim_history" in sql
    ]
    assert len(historiales) == 2
    assert all("ON CONFLICT (claim_id, run_id) DO UPDATE SET" in sql for sql in historiales)


def test_guardar_claims_detecta_conflicto_de_contenido_en_reintento():
    conexion = _Conexion()
    conexion.cursor_obj.rowcounts = [0]
    repositorio = RepositorioAnalytics("postgresql://prueba")

    @contextmanager
    def conexion_falsa():
        yield conexion

    repositorio.conexion = conexion_falsa
    claims = pd.DataFrame(
        [
            {
                "claim_id": "claim-conflicto",
                "hipotesis": "Poda",
                "clase_evidencia": "temporal",
                "estado": "consistente",
                "afirmacion": "Contenido nuevo",
            }
        ]
    )

    with pytest.raises(ClaimHistoryConflictError, match="contenido diferente"):
        repositorio.guardar_claims(7, claims)

    assert len(conexion.cursor_obj.calls) == 1
    assert "evidence_claim_history" in conexion.cursor_obj.calls[0][0]
