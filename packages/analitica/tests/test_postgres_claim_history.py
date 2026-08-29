"""Prueba de integración real para el historial de claims analíticos.

La prueba no crea ni modifica el esquema: el workflow aplica las migraciones antes
de ejecutarla. Fuera de CI se omite explícitamente si no se declara un DSN de prueba.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest


@pytest.fixture
def postgres_context():
    dsn = os.environ.get("AQUANQA_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Se omite la integración PostgreSQL: falta AQUANQA_TEST_POSTGRES_DSN.")

    host = urlparse(dsn).hostname
    if host not in {"localhost", "127.0.0.1", "::1", "postgres"}:
        pytest.fail(
            "AQUANQA_TEST_POSTGRES_DSN debe apuntar a un host local o al servicio "
            f"de CI; recibido: {host!r}."
        )

    # Con DSN configurado, una dependencia ausente debe fallar la prueba y no convertirse
    # en un skip que dé una falsa sensación de cobertura.
    import pandas
    import psycopg

    from analitica.proyeccion.persistencia.repositorio import (
        ClaimHistoryConflictError,
        RepositorioAnalytics,
    )

    return dsn, psycopg, pandas, RepositorioAnalytics, ClaimHistoryConflictError


def _snapshot_datos(firma: str):
    fuente = SimpleNamespace(
        nombre="fixture",
        firma=firma,
        corte=datetime.now(UTC),
        conteos={},
        fallback=False,
        advertencias=[],
    )
    return SimpleNamespace(fuente=fuente)


def _claim(claim_id: str, firma: str, *, afirmacion: str):
    return {
        "claim_id": claim_id,
        "hipotesis_id": f"it-{firma}",
        "hipotesis": "La persistencia conserva la evidencia por corrida.",
        "clase_evidencia": "descriptiva",
        "estado": "exploratorio",
        "afirmacion": afirmacion,
        "estimacion": 10.0,
        "intervalo_inferior": 8.0,
        "intervalo_superior": 12.0,
        "unidad": "kg",
        "n_efectivo": 1.0,
        "alcance": {"entorno": "integration", "firma": firma},
        "supuestos": ["datos de prueba"],
        "limitaciones": ["solo integración"],
        "referencias": [f"urn:aquanqa:integration:{firma}"],
    }


def _history_rows(psycopg, dsn: str, claim_id: str):
    with psycopg.connect(dsn) as con, con.cursor() as cur:
        cur.execute(
            """
            SELECT claim_id, run_id, hipotesis_id, hipotesis, clase_evidencia, estado,
                   afirmacion, estimacion, intervalo_inferior, intervalo_superior,
                   unidad, n_efectivo, alcance, supuestos, limitaciones, referencias,
                   actualizado_en, registrado_en
            FROM analytics.evidence_claim_history
            WHERE claim_id = %s
            ORDER BY run_id
            """,
            (claim_id,),
        )
        return cur.fetchall()


def _current_claim(psycopg, dsn: str, claim_id: str):
    with psycopg.connect(dsn) as con, con.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*), MIN(run_id), MAX(run_id)
            FROM analytics.evidence_claim
            WHERE claim_id = %s
            """,
            (claim_id,),
        )
        return cur.fetchone()


def _run_snapshot_ids(psycopg, dsn: str, run_ids: list[int]):
    with psycopg.connect(dsn) as con, con.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT snapshot_id), MIN(snapshot_id), MAX(snapshot_id)
            FROM analytics.forecast_run
            WHERE run_id = ANY(%s)
            """,
            (run_ids,),
        )
        return cur.fetchone()


def _cleanup(psycopg, dsn: str, claim_id: str, run_ids: list[int], snapshot_id: int | None):
    """Elimina solo las filas identificadas por esta prueba."""
    with psycopg.connect(dsn) as con, con.cursor() as cur:
        cur.execute(
            "DELETE FROM analytics.evidence_claim_history WHERE claim_id = %s",
            (claim_id,),
        )
        cur.execute(
            "DELETE FROM analytics.evidence_claim WHERE claim_id = %s",
            (claim_id,),
        )
        for run_id in run_ids:
            cur.execute("DELETE FROM analytics.forecast_run WHERE run_id = %s", (run_id,))
        if snapshot_id is not None:
            cur.execute(
                "DELETE FROM analytics.dataset_snapshot WHERE snapshot_id = %s",
                (snapshot_id,),
            )


def test_claim_history_postgres_real(postgres_context):
    dsn, psycopg, pd, repositorio_cls, conflict_error = postgres_context
    test_uuid = str(uuid.uuid4())
    firma = f"postgres-integration-{test_uuid}"
    claim_id = f"claim-{test_uuid}"
    snapshot_id = None
    run_ids: list[int] = []
    repo = repositorio_cls(dsn=dsn)

    try:
        snapshot_id = repo.snapshot(_snapshot_datos(firma))
        run_ids.append(
            repo.crear_run(
                snapshot_id,
                "backtest",
                {"integration_test": test_uuid, "run": 1},
                mlflow_run_id=f"integration-{test_uuid}-run-1",
            )
        )
        run_ids.append(
            repo.crear_run(
                snapshot_id,
                "backtest",
                {"integration_test": test_uuid, "run": 2},
                mlflow_run_id=f"integration-{test_uuid}-run-2",
            )
        )
        assert _run_snapshot_ids(psycopg, dsn, run_ids) == (2, 1, snapshot_id, snapshot_id)
        claims = pd.DataFrame(
            [_claim(claim_id, test_uuid, afirmacion="La corrida conserva el claim.")]
        )

        repo.guardar_claims(run_ids[0], claims)
        repo.guardar_claims(run_ids[1], claims)

        assert len(_history_rows(psycopg, dsn, claim_id)) == 2
        assert _current_claim(psycopg, dsn, claim_id) == (1, run_ids[1], run_ids[1])

        repo.guardar_claims(run_ids[1], claims)
        history_before_conflict = _history_rows(psycopg, dsn, claim_id)
        assert len(history_before_conflict) == 2

        different_claim = pd.DataFrame(
            [_claim(claim_id, test_uuid, afirmacion="Contenido incompatible de prueba.")]
        )
        with pytest.raises(conflict_error, match="claim histórico"):
            repo.guardar_claims(run_ids[1], different_claim)

        assert _history_rows(psycopg, dsn, claim_id) == history_before_conflict
        assert _current_claim(psycopg, dsn, claim_id) == (1, run_ids[1], run_ids[1])
    finally:
        _cleanup(psycopg, dsn, claim_id, run_ids, snapshot_id)

        with psycopg.connect(dsn) as con, con.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM analytics.evidence_claim WHERE claim_id = %s",
                (claim_id,),
            )
            assert cur.fetchone() == (0,)
            cur.execute(
                "SELECT COUNT(*) FROM analytics.evidence_claim_history WHERE claim_id = %s",
                (claim_id,),
            )
            assert cur.fetchone() == (0,)
            if run_ids:
                cur.execute(
                    "SELECT COUNT(*) FROM analytics.forecast_run WHERE run_id = ANY(%s)",
                    (run_ids,),
                )
                assert cur.fetchone() == (0,)
            if snapshot_id is not None:
                cur.execute(
                    "SELECT COUNT(*) FROM analytics.dataset_snapshot WHERE snapshot_id = %s",
                    (snapshot_id,),
                )
                assert cur.fetchone() == (0,)
