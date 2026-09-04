from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from aquanqa_campo_api.api.dependencies import (
    get_catalog_repository,
    get_current_user,
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
from aquanqa_campo_api.modules.seguridad.schemas import AuthUser


class FakeRepository:
    def __init__(self):
        self.saved = []
        self.updated = []

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

    def update(self, normalized):
        self.updated.append(normalized)
        return StoredEvaluation(
            EvaluationReceipt(
                client_id=normalized.source.client_id,
                evaluation_id=99,
                module_key=normalized.source.module_key,
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
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        usuario_id=1,
        email="evaluador@test.local",
        nombre="Evaluador",
        rol="evaluador",
        permisos=["api:evaluaciones:capturar"],
    )
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


def test_captura_evaluacion_conserva_el_contrato_movil_por_dni():
    client = _client(FakeRepository())
    response = client.post(
        "/v1/evaluaciones",
        json={
            "id": "33333333-3333-4333-8333-333333333333",
            "module_key": "estadios",
            "fecha": "2026-09-01",
            "lote_id": 12,
            "cortina": 1,
            "hilera": 2,
            "planta": 3,
            "evaluador_dni": "10616663",
            "valores": {"m1_e1": 1},
        },
    )
    assert response.status_code == 201


def test_edicion_de_evaluacion_usa_patch_y_conserva_la_identidad():
    repository = FakeRepository()
    client = _client(repository)
    try:
        response = client.patch(
            "/v1/evaluaciones/33333333-3333-4333-8333-333333333333",
            json={
                "id": "33333333-3333-4333-8333-333333333333",
                "module_key": "estadios",
                "fecha": "2026-09-01",
                "captured_at": "2026-09-01T15:00:00Z",
                "updated_at": "2026-09-04T15:00:00Z",
                "lote_id": 12,
                "cortina": 1,
                "hilera": 2,
                "planta": 3,
                "evaluador_dni": "10616663",
                "valores": {"m1_e1": 8},
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["evaluation_id"] == 99
        assert repository.updated[0].source.client_id == UUID(
            "33333333-3333-4333-8333-333333333333"
        )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("module_key", "valores"),
    [
        ("estadios", {"m1_e1": 1, "m1_e2": 2, "m1_total": 3}),
        ("flores", {"m2_flores": 12, "m2_cuajos": 4}),
        ("baya", {"m4_diam01": 12.5, "m4_est01": "E2"}),
        ("pesos", {"m5_peso01": 8.2, "m5_diam01": 13.1}),
        ("brotes", {"m6_piso": "BROTE1", "m6_brotes": 7}),
        (
            "ramas",
            {"m7_ram_lt5": 3, "m7_ram_gt5": 2, "m7_diam01": 5.4},
        ),
    ],
)
def test_api_acepta_los_seis_payloads_reales_de_capturar(module_key, valores):
    repository = FakeRepository()
    client = _client(repository)
    try:
        response = client.post(
            "/v1/evaluaciones",
            json={
                "id": "22222222-2222-4222-8222-222222222222",
                "module_key": module_key,
                "fecha": "2026-09-01",
                "captured_at": "2026-09-01T15:00:00Z",
                "evaluador_id": 200,
                "evaluador_dni": "10616663",
                "lote_id": 12,
                "fundo": "Aqu Anqa 1",
                "modulo": "M01",
                "lote": "L-001",
                "cortina": 12,
                "hilera": 45,
                "planta": 123,
                "valores": valores,
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["module_key"] == module_key
        assert repository.saved[0].module_key == module_key
    finally:
        app.dependency_overrides.clear()
