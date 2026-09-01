from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from aquanqa_campo_api.api.dependencies import (
    get_catalog_repository,
    get_evaluation_repository,
    get_health_repository,
    get_identity_repository,
)
from aquanqa_campo_api.main import app
from aquanqa_campo_api.modules.evaluaciones.repository import (
    StoredEvaluation,
    StoredHistoryPage,
)
from aquanqa_campo_api.modules.evaluaciones.schemas import (
    EvaluationHistoryItem,
    EvaluationReceipt,
)


class FakeRepository:
    def __init__(self):
        self.saved = []

    def save(self, normalized):
        self.saved.append(normalized)
        return StoredEvaluation(
            EvaluationReceipt(
                client_id=normalized.source.client_id,
                evaluation_id=99,
                module_key=normalized.source.module_key,
                status="accepted",
                received_at=datetime.now(UTC),
            )
        )

    def get_by_client_id(self, client_id: UUID):
        if not self.saved:
            return None
        return StoredEvaluation(
            EvaluationReceipt(
                client_id=client_id,
                evaluation_id=99,
                module_key=self.saved[0].source.module_key,
                status="accepted",
                received_at=datetime.now(UTC),
            )
        )

    def list_history(self, **_):
        if not self.saved:
            return StoredHistoryPage(items=[], has_more=False)
        source = self.saved[0].source
        return StoredHistoryPage(
            items=[
                EvaluationHistoryItem(
                    id=source.client_id,
                    module_key=source.module_key,
                    fecha=source.fecha,
                    captured_at=source.captured_at or datetime.now(UTC),
                    evaluador="DIANA LUPITA SIPIRAN DIAZ",
                    evaluador_id=200,
                    evaluador_dni="10616663",
                    lote_id=12,
                    fundo="AQUANQA 1",
                    modulo="M01",
                    lote="L01",
                    cortina=source.cortina,
                    hilera=source.hilera,
                    planta=source.planta,
                    valores=source.valores,
                )
            ],
            has_more=False,
        )

    def list_fundos(self):
        return []

    def list_modulos(self, fundo_id=None):
        return []

    def list_lotes(self, modulo_id=None):
        return []

    def list_evaluadores(self):
        return []

    def find_evaluador_by_dni(self, dni):
        return {
            "evaluador_id": 200,
            "dni": dni,
            "nombre": "DIANA LUPITA SIPIRAN DIAZ",
            "codigo": "DSIP",
            "zona": "PAIJAN",
            "activo": True,
        }

    def ping(self):
        return None


def _client(repository: FakeRepository) -> TestClient:
    for dependency in (
        get_catalog_repository,
        get_evaluation_repository,
        get_health_repository,
        get_identity_repository,
    ):
        app.dependency_overrides[dependency] = lambda: repository
    return TestClient(app)


def test_las_diez_operaciones_responden_sin_postgres():
    repository = FakeRepository()
    client = _client(repository)
    try:
        assert client.get("/v1/health/live").status_code == 200
        assert client.get("/v1/health/ready").status_code == 200
        assert client.get("/v1/catalogos/fundos").status_code == 200
        assert client.get("/v1/catalogos/modulos?fundo_id=1").status_code == 200
        assert client.get("/v1/catalogos/lotes?modulo_id=1").status_code == 200
        assert client.get("/v1/sesion/evaluadores").status_code == 200
        assert client.post("/v1/sesion/evaluador", json={"dni": "10616663"}).status_code == 200
        response = client.post(
            "/v1/evaluaciones",
            json={
                "id": "11111111-1111-4111-8111-111111111111",
                "module_key": "estadios",
                "fecha": "2026-08-31",
                "lote_id": 12,
                "cortina": 1,
                "hilera": 2,
                "planta": 3,
                "evaluador_dni": "10616663",
                "valores": {"m1_e1": 1},
            },
        )
        assert response.status_code == 201
        assert response.json()["evaluation_id"] == 99
        history = client.get("/v1/evaluaciones/historial?evaluador_id=200")
        assert history.status_code == 200
        assert history.json()["items"][0]["id"] == "11111111-1111-4111-8111-111111111111"
        lookup = client.get("/v1/evaluaciones/11111111-1111-4111-8111-111111111111")
        assert lookup.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_swagger_redoc_y_openapi_estan_disponibles():
    client = TestClient(app)
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_historial_requiere_identidad_del_evaluador():
    repository = FakeRepository()
    client = _client(repository)
    try:
        assert client.get("/v1/evaluaciones/historial").status_code == 422
    finally:
        app.dependency_overrides.clear()
