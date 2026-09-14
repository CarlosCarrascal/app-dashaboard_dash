from datetime import UTC, date, datetime
from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from openpyxl import Workbook

from aquanqa_campo_api.api.dependencies import (
    get_admin_repository,
    get_admin_user,
    get_evaluation_service,
)
from aquanqa_campo_api.main import app
from aquanqa_campo_api.modules.admin.schemas import (
    AdminEvaluationDetail,
    AdminEvaluationItem,
    AdminEvaluationPage,
    AdminEvaluationSummary,
    AdminLoadPage,
    AdminMasterPage,
    AdminMutation,
    AdminQABulkResolution,
    AdminQAPage,
    AdminQAReview,
    AdminQASummary,
    ImportManifest,
    PageInfo,
)
from aquanqa_campo_api.modules.evaluaciones.schemas import EvaluationCreate, EvaluationReceipt
from aquanqa_campo_api.modules.seguridad.schemas import AuthUser


def _meta(total: int = 1) -> PageInfo:
    return PageInfo(page=1, page_size=50, total=total, pages=1 if total else 0)


def _evaluation() -> AdminEvaluationItem:
    return AdminEvaluationItem(
        id="ev_estados:7",
        source_table="ev_estados",
        source_id=7,
        module_key="estadios",
        fecha=date(2026, 9, 2),
        captured_at=datetime(2026, 9, 2, 15, 0, tzinfo=UTC),
        lote_id=12,
        empresa="Aqu Anqa",
        fundo="AQUANQA 1",
        modulo="M01",
        lote="L001",
        evaluador_id=4,
        evaluador="Diana Sipiran",
        evaluador_dni="10616663",
        detalle={"e1": 2},
    )


class FakeAdminRepository:
    preview = None

    def list_evaluations(self, query):
        return AdminEvaluationPage(items=[_evaluation()], meta=_meta())

    def evaluation_counts(self, query):
        from aquanqa_campo_api.modules.admin.schemas import EvaluationCounts
        return EvaluationCounts(total=1,lotes=1,evaluadores=1,por_modulo=[{'module_key':'estadios','total':1}])

    def evaluation_summary(self, query):
        return AdminEvaluationSummary(
            total=1,
            por_modulo=[{"module_key": "estadios", "total": 1}],
            evaluadores=1,
            lotes=1,
            desde=date(2026, 9, 2),
            hasta=date(2026, 9, 2),
            ultima_captura=datetime(2026, 9, 2, 15, 0, tzinfo=UTC),
        )

    def get_evaluation(self, module_key, source_id, source_table=None):
        return AdminEvaluationDetail.model_validate(_evaluation().model_dump())

    def correct_evaluation(self, module_key, source_id, request, values, usuario_id):
        return AdminMutation(
            cambio_id=21,
            recurso=f"evaluacion:{request.source_table}",
            recurso_id=source_id,
            accion="corregir",
            antes={"e1": 1},
            despues={"e1": 2},
            idempotency_key=request.idempotency_key,
            mensaje="Evaluación corregida y auditada.",
        )

    def list_master(self, resource, query):
        return AdminMasterPage(items=[{"empresa_id": 1, "nombre": "Aqu Anqa"}], meta=_meta())

    def mutate_master(self, resource, resource_id, request, usuario_id):
        return AdminMutation(
            cambio_id=22,
            recurso=f"maestro:{resource}",
            recurso_id=resource_id or 2,
            accion="crear" if resource_id is None else "actualizar",
            antes=None,
            despues=request.valores,
            idempotency_key=request.idempotency_key,
            mensaje="Maestro actualizado y auditado.",
        )

    def list_roles(self, query):
        return AdminMasterPage(items=[{"rol_id": 1, "codigo": "admin"}], meta=_meta())

    def list_users(self, query):
        return AdminMasterPage(items=[], meta=PageInfo(page=1, page_size=50, total=0, pages=0))

    def mutate_user(self, usuario_id, request, actor_id, values):
        return AdminMutation(
            cambio_id=23,
            recurso="usuario",
            recurso_id=usuario_id or 3,
            accion="crear" if usuario_id is None else "actualizar",
            antes=None,
            despues={"email": values.get("email", "usuario@test.local")},
            idempotency_key=request.idempotency_key,
            mensaje="Usuario actualizado y auditado.",
        )

    def list_imports(self, query):
        return AdminLoadPage(items=[], meta=PageInfo(page=1, page_size=50, total=0, pages=0))

    def qa_summary(self):
        return AdminQASummary(total_rechazos=1, motivos=[], alertas=0)

    def list_qa(self, query):
        return AdminQAPage(items=[], meta=PageInfo(page=1, page_size=50, total=0, pages=0))

    def review_qa(self, rechazo_id, request, usuario_id):
        return AdminQAReview(
            rechazo_id=rechazo_id,
            estado_revision=request.estado,
            idempotency_key=request.idempotency_key,
            comentario_revision=request.comentario,
            revisado_en=datetime(2026, 9, 2, 15, 0, tzinfo=UTC),
            revisado_por=usuario_id,
        )

    def confirm_qa_duplicates(self, request, usuario_id):
        return AdminQABulkResolution(
            procesados=len(request.rechazo_ids),
            idempotency_key=request.idempotency_key,
        )

    def create_import_preview(self, preview, usuario_id):
        self.preview = preview
        return preview

    def claim_import(self, preview_id, file_sha256, usuario_id):
        assert self.preview is not None
        return ImportManifest(
            carga_id=preview_id,
            filename=self.preview.filename,
            file_sha256=file_sha256,
            estado="processing",
            payloads=[
                EvaluationCreate.model_validate(row.payload)
                for row in self.preview.rows
                if row.valid and row.payload
            ],
            total_rows=self.preview.total_rows,
            valid_rows=self.preview.valid_rows,
            invalid_rows=self.preview.invalid_rows,
        )

    def complete_import(self, preview_id, usuario_id, result):
        return None

    def fail_import(self, preview_id, usuario_id, error):
        return None


class FakeEvaluationService:
    def register_many(self, payloads):
        return [
            EvaluationReceipt(
                client_id=payload.client_id,
                evaluation_id=index,
                module_key=payload.module_key,
                status="accepted",
                received_at=datetime(2026, 9, 2, 15, 0, tzinfo=UTC),
            )
            for index, payload in enumerate(payloads, start=1)
        ]


def _client(repository: FakeAdminRepository) -> TestClient:
    app.dependency_overrides[get_admin_repository] = lambda: repository
    app.dependency_overrides[get_evaluation_service] = lambda: FakeEvaluationService()
    app.dependency_overrides[get_admin_user] = lambda: AuthUser(
        usuario_id=1,
        email="admin@test.local",
        nombre="Admin",
        rol="admin",
        permisos=["*"],
    )
    return TestClient(app)


def test_superficie_admin_lee_sin_postgres():
    client = _client(FakeAdminRepository())
    try:
        evaluations = client.get("/v1/admin/evaluaciones?module_key=estadios")
        assert evaluations.status_code == 200
        assert evaluations.json()["items"][0]["id"] == "ev_estados:7"
        assert client.get("/v1/admin/evaluaciones/resumen").json()["total"] == 1
        assert client.get("/v1/admin/evaluaciones/conteos").json()["total"] == 1
        records = client.get("/v1/admin/evaluaciones/registros?module_key=estadios")
        assert records.status_code == 200
        assert records.json()["items"][0]["id"] == "ev_estados:7"
        assert client.get("/v1/admin/evaluaciones/indicadores").json()["total"] == 1
        assert client.get("/v1/admin/evaluaciones/registros/ev_estados:7").status_code == 200
        assert client.get("/v1/admin/evaluaciones/registros/incorrecto").status_code == 422
        assert client.get("/v1/admin/evaluaciones/estadios/7").status_code == 200
        assert client.get("/v1/admin/maestros/empresas").status_code == 200
        assert client.get("/v1/admin/roles").status_code == 200
        assert client.get("/v1/admin/usuarios").status_code == 200
        assert client.get("/v1/admin/cargas?estado=accepted").status_code == 200
        assert client.get("/v1/admin/qa/resumen").status_code == 200
        assert client.get("/v1/admin/qa/rechazos").status_code == 200
        reviewed = client.patch(
            "/v1/admin/qa/rechazos/9/revision",
            json={
                "estado": "corregir",
                "idempotency_key": str(uuid4()),
                "comentario": "Revisar con Agronomía",
            },
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["estado_revision"] == "corregir"
        bulk_key = str(uuid4())
        bulk = client.post(
            "/v1/admin/qa/duplicados/confirmar",
            json={
                "rechazo_ids": [9, 10],
                "idempotency_key": bulk_key,
                "comentario": "Duplicados verificados",
            },
        )
        assert bulk.status_code == 200
        assert bulk.json() == {
            "procesados": 2,
            "idempotency_key": bulk_key,
            "accion": "confirmar_duplicados",
        }
    finally:
        app.dependency_overrides.clear()


def test_superficie_admin_expone_correcciones_y_mutaciones_auditadas():
    client = _client(FakeAdminRepository())
    try:
        correction = client.patch(
            "/v1/admin/evaluaciones/estadios/7",
            json={
                "source_table": "ev_estados",
                "fecha": "2026-09-02",
                "lote_id": 12,
                "cortina": 1,
                "hilera": 2,
                "planta": 3,
                "evaluador_id": 4,
                "valores": {"m1_e1": 2},
                "idempotency_key": str(uuid4()),
                "comentario": "Corrección de prueba",
            },
        )
        assert correction.status_code == 200, correction.text
        assert correction.json()["mutation"]["accion"] == "corregir"

        master = client.post(
            "/v1/admin/maestros/empresas",
            json={
                "valores": {"nombre": "Empresa de prueba"},
                "idempotency_key": str(uuid4()),
            },
        )
        assert master.status_code == 200, master.text
        assert master.json()["accion"] == "crear"

        user = client.post(
            "/v1/admin/usuarios",
            json={
                "email": "nuevo@test.local",
                "nombre": "Usuario nuevo",
                "rol": "admin",
                "password": "Clave segura 2026!",
                "idempotency_key": str(uuid4()),
            },
        )
        assert user.status_code == 200, user.text
        assert user.json()["recurso"] == "usuario"
        assert "hash_password" not in user.json()["despues"]
    finally:
        app.dependency_overrides.clear()


def test_plantilla_y_carga_masiva_son_auditables():
    client = _client(FakeAdminRepository())
    try:
        template = client.get("/v1/admin/evaluaciones/plantilla")
        assert template.status_code == 200
        assert template.content[:2] == b"PK"
        assert "attachment" in template.headers["content-disposition"]

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Evaluaciones"
        sheet.append(
            [
                "module_key",
                "fecha",
                "lote_id",
                "cortina",
                "hilera",
                "planta",
                "evaluador_dni",
                "valores_json",
            ]
        )
        sheet.append(["estadios", "2026-09-02", 12, 1, 2, 3, "10616663", '{"m1_e1": 2}'])
        buffer = BytesIO()
        workbook.save(buffer)
        preview = client.post(
            "/v1/admin/evaluaciones/previsualizar",
            files={
                "archivo": (
                    "evaluaciones.xlsx",
                    buffer.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["total_rows"] == 1
        assert body["valid_rows"] == 1
        assert body["invalid_rows"] == 0

        loaded = client.post(
            "/v1/admin/evaluaciones/cargar",
            json={"preview_id": body["preview_id"], "file_sha256": body["file_sha256"]},
        )
        assert loaded.status_code == 200, loaded.text
        assert loaded.json()["accepted_rows"] == 1
        assert loaded.json()["atomic"] is True
    finally:
        app.dependency_overrides.clear()


def test_previsualizacion_rechaza_extension_no_soportada():
    client = _client(FakeAdminRepository())
    try:
        response = client.post(
            "/v1/admin/evaluaciones/previsualizar",
            files={"archivo": ("evaluaciones.xls", b"no es xlsx", "application/vnd.ms-excel")},
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()
