"""HTTP + PostgreSQL real, dentro de una transacción que SIEMPRE se revierte."""

import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from aquanqa_campo_api.api.dependencies import get_current_user, get_evaluation_repository
from aquanqa_campo_api.infrastructure.postgres.evaluaciones_repository import (
    PostgresEvaluationRepository,
)
from aquanqa_campo_api.main import app
from aquanqa_campo_api.modules.seguridad.schemas import AuthUser

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(os.getenv("AQUANQA_RUN_DB_TESTS") != "1", reason="PostgreSQL opt-in"),
]
ROOT = Path(__file__).resolve().parents[4]


class TransactionFactory:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def connect(self):
        with self.connection.transaction():
            yield self.connection
            # Los SAVEPOINT no comprueban los triggers diferidos por sí solos.
            self.connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
            self.connection.execute("SET CONSTRAINTS ALL DEFERRED")


@pytest.fixture
def real_api():
    cfg = dotenv_values(ROOT / ".env")
    assert cfg.get("PGHOST", "localhost") in {"localhost", "127.0.0.1"}
    with psycopg.connect(
        host=cfg.get("PGHOST", "localhost"),
        port=cfg.get("PGPORT", "5432"),
        dbname="aquanqa_migracion",
        user=cfg["PGUSER"],
        password=cfg["PGPASSWORD"],
        row_factory=dict_row,
        autocommit=True,
    ) as conn:
        before = conn.execute("SELECT count(*) n FROM core.api_evaluacion_ingesta").fetchone()["n"]
        with conn.transaction(force_rollback=True):
            migration = (ROOT / "db/migrations/evaluaciones_v1/005_api_canonica.sql").read_text(
                encoding="utf-8"
            )
            conn.execute(
                "\n".join(
                    line
                    for line in migration.splitlines()
                    if not line.startswith("\\") and line not in {"BEGIN;", "COMMIT;"}
                )
            )
            migration = (ROOT / "db/migrations/evaluaciones_v1/006_admin_canonico.sql").read_text(
                encoding="utf-8"
            )
            conn.execute(
                "\n".join(
                    line
                    for line in migration.splitlines()
                    if not line.startswith("\\") and line not in {"BEGIN;", "COMMIT;"}
                )
            )
            conn.execute("SET LOCAL ROLE aquanqa_app")
            evaluator = conn.execute(
                "SELECT evaluador_id FROM core.m_evaluador WHERE activo AND en_maestro LIMIT 1"
            ).fetchone()
            lot = conn.execute("""SELECT l.lote_id FROM core.m_lote l
                JOIN core.m_modulo m ON m.modulo_id=l.modulo_id
                JOIN core.m_fundo f ON f.fundo_id=m.fundo_id
                JOIN core.m_empresa e ON e.empresa_id=f.empresa_id
                WHERE NOT l.es_sentinel AND NOT l.es_ficticio AND NOT m.es_sentinel
                  AND NOT f.es_sentinel AND NOT e.es_sentinel
                  AND m.activo AND f.activo AND e.activo LIMIT 1""").fetchone()
            assert evaluator and lot
            repository = PostgresEvaluationRepository(TransactionFactory(conn))
            app.dependency_overrides[get_evaluation_repository] = lambda: repository
            app.dependency_overrides[get_current_user] = lambda: AuthUser(
                usuario_id=1,
                email="prueba@test.invalid",
                nombre="Prueba transaccional",
                rol="evaluador",
                permisos=["api:evaluaciones:capturar"],
            )
            try:
                yield (
                    TestClient(app),
                    conn,
                    dict(
                        lote_id=lot["lote_id"],
                        evaluador_id=evaluator["evaluador_id"],
                        fecha="2099-01-01",
                        captured_at="2099-01-01T15:30:00Z",
                        cortina=1,
                        hilera=1,
                        planta=1,
                    ),
                )
            finally:
                app.dependency_overrides.clear()
        assert (
            conn.execute("SELECT count(*) n FROM core.api_evaluacion_ingesta").fetchone()["n"]
            == before
        )


@pytest.mark.parametrize(
    "module,values,table",
    [
        ("estadios", {f"m1_e{i}": i for i in range(1, 6)}, "ev_estadios"),
        (
            "flores",
            {
                "m2_flores": 4,
                "m2_cuajos": 3,
                "m2_yp": 2,
                "m2_ya": 1,
                "m2_ymuerta": 5,
                "m2_brotes_tiernos": 6,
            },
            "ev_conteo_flores",
        ),
        ("brotes", {"m6_piso": "1", "m6_brotes": 7, "m6_des1": "8"}, "ev_conteo_brotes"),
        (
            "ramas",
            {"m7_ram_lt5": 2, "m7_ram_gt5": 3, "m7_diam100": "5.12345678"},
            "ev_rama_observacion",
        ),
        ("baya", {"m4_est100": "E3", "m4_diam100": "12.12345678"}, "ev_fruto_observacion"),
        (
            "pesos",
            {"m5_peso100": "2.12345678", "m5_diam100": "12.12345678"},
            "ev_fruto_observacion",
        ),
    ],
)
def test_mobile_canonical_lifecycle(real_api, module, values, table):
    client, conn, context = real_api
    payload = dict(context, id=str(uuid4()), module_key=module, valores=values)
    response = client.post("/v1/evaluaciones", json=payload)
    assert response.status_code == 201, response.text
    evaluation_id = response.json()["evaluation_id"]
    assert (
        conn.execute(
            f"SELECT count(*) n FROM core.{table} WHERE evaluacion_id=%s", (evaluation_id,)
        ).fetchone()["n"]
        == 1
    )
    repeated = client.post("/v1/evaluaciones", json=payload)
    assert repeated.status_code == 200 and repeated.json()["status"] == "duplicate"
    assert repeated.json()["evaluation_id"] == evaluation_id
    other = client.post("/v1/evaluaciones", json={**payload, "id": str(uuid4())})
    assert other.status_code == 201 and other.json()["evaluation_id"] != evaluation_id
    conflict = client.post("/v1/evaluaciones", json={**payload, "planta": 2})
    assert conflict.status_code == 409
    updated = client.patch(f"/v1/evaluaciones/{payload['id']}", json={**payload, "planta": 2})
    assert updated.status_code == 200, updated.text
    header = conn.execute(
        "SELECT planta,revision,origen FROM core.ev_evaluacion WHERE evaluacion_id=%s",
        (evaluation_id,),
    ).fetchone()
    assert header == {"planta": 2, "revision": 2, "origen": "mobile"}
    history = client.get(
        "/v1/evaluaciones/historial",
        params={"evaluador_id": context["evaluador_id"], "module_key": module, "limit": 10},
    )
    assert history.status_code == 200, history.text
    row = next(x for x in history.json()["items"] if x["id"] == payload["id"])
    assert row["planta"] == 2
    for key, value in values.items():
        assert (
            str(row["valores"][key]) == str(float(value))
            if "." in str(value)
            else str(row["valores"][key]) == str(value)
        )


def test_mobile_100_samples_and_invalid_weight(real_api):
    client, conn, context = real_api
    payload = dict(
        context,
        id=str(uuid4()),
        module_key="pesos",
        valores={
            "muestras": [
                {"numero_muestra": i, "peso_g": "2.12345678", "diametro_mm": "12.98765432"}
                for i in range(1, 101)
            ]
        },
    )
    result = client.post("/v1/evaluaciones", json=payload)
    assert result.status_code == 201, result.text
    rows = conn.execute(
        "SELECT count(*) n,min(peso_g)::text peso FROM core.ev_fruto_observacion "
        "WHERE evaluacion_id=%s",
        (result.json()["evaluation_id"],),
    ).fetchone()
    assert rows == {"n": 100, "peso": "2.12345678"}
    history = client.get(
        "/v1/evaluaciones/historial",
        params={
            "evaluador_id": context["evaluador_id"],
            "module_key": "pesos",
            "limit": 10,
        },
    )
    assert history.status_code == 200, history.text
    item = next(row for row in history.json()["items"] if row["id"] == payload["id"])
    edited = client.patch(
        f"/v1/evaluaciones/{payload['id']}", json={**payload, "valores": item["valores"]}
    )
    assert edited.status_code == 200, edited.text
    bad = dict(context, id=str(uuid4()), module_key="pesos", valores={"m5_peso01": 3})
    assert client.post("/v1/evaluaciones", json=bad).status_code == 422
    assert not conn.execute(
        "SELECT FROM core.api_evaluacion_ingesta WHERE client_id=%s", (bad["id"],)
    ).fetchone()


def test_admin_canonical_reads_and_audited_correction(real_api):
    from aquanqa_campo_api.infrastructure.postgres.admin_repository import PostgresAdminRepository
    from aquanqa_campo_api.modules.admin.schemas import (
        AdminEvaluationQuery,
        EvaluationCorrectionRequest,
    )
    from aquanqa_campo_api.modules.admin.service import AdminService

    client, conn, context = real_api
    actor = conn.execute("""SELECT u.usuario_id FROM core.m_usuario u
        JOIN core.m_rol r ON r.rol_id=u.rol_id
        WHERE u.activo AND r.codigo='admin' LIMIT 1""").fetchone()
    assert actor
    service = AdminService(
        PostgresAdminRepository(
            TransactionFactory(conn), usuario_id=actor["usuario_id"], unrestricted=True
        )
    )
    result = client.post(
        "/v1/evaluaciones",
        json=dict(
            context,
            id=str(uuid4()),
            module_key="flores",
            valores={"m2_ymuerta": 17, "m2_brotes_tiernos": 19},
        ),
    )
    assert result.status_code == 201, result.text
    evaluation_id = result.json()["evaluation_id"]
    detail = service.get_evaluation("flores", evaluation_id, "ev_evaluacion")
    assert detail.detalle["yemas_muertas"] == 17
    request = EvaluationCorrectionRequest.model_validate(
        dict(
            source_table="ev_evaluacion",
            fecha=context["fecha"],
            lote_id=context["lote_id"],
            cortina=1,
            hilera=1,
            planta=1,
            evaluador_id=context["evaluador_id"],
            valores={"m2_ymuerta": 21, "m2_brotes_tiernos": 23},
            idempotency_key=str(uuid4()),
        )
    )
    changed = service.correct_evaluation("flores", evaluation_id, request, actor["usuario_id"])
    assert changed.evaluacion.detalle["yemas_muertas"] == 21
    repeated = service.correct_evaluation("flores", evaluation_id, request, actor["usuario_id"])
    assert repeated.mutation.cambio_id == changed.mutation.cambio_id
    summary = service.evaluation_summary(AdminEvaluationQuery())
    assert (
        summary.total
        == conn.execute(
            "SELECT count(*) n FROM core.ev_evaluacion WHERE estado_registro='vigente'"
        ).fetchone()["n"]
    )


def test_atomic_bulk_failure_leaves_no_rows(real_api):
    from aquanqa_campo_api.modules.evaluaciones.repository import LocationNotFoundError
    from aquanqa_campo_api.modules.evaluaciones.rules import normalize_evaluation
    from aquanqa_campo_api.modules.evaluaciones.schemas import EvaluationCreate

    _, conn, context = real_api
    ids = [str(uuid4()), str(uuid4())]
    payload = dict(context, module_key="estadios", valores={"m1_e1": 4})
    records = [
        normalize_evaluation(EvaluationCreate.model_validate({**payload, "id": ids[0]})),
        normalize_evaluation(
            EvaluationCreate.model_validate({**payload, "id": ids[1], "lote_id": 2147483647})
        ),
    ]
    repository = PostgresEvaluationRepository(TransactionFactory(conn))
    with pytest.raises(LocationNotFoundError):
        repository.save_many(records)
    assert (
        conn.execute(
            "SELECT count(*) n FROM core.api_evaluacion_ingesta WHERE client_id=ANY(%s)", (ids,)
        ).fetchone()["n"]
        == 0
    )
