"""Protege la superficie que ya consume Flutter."""

from aquanqa_campo_api.main import app

EXPECTED_OPERATIONS = {
    "/v1/health/live": {"get"},
    "/v1/health/ready": {"get"},
    "/v1/sesion/evaluador": {"post"},
    "/v1/sesion/evaluadores": {"get"},
    "/v1/catalogos/fundos": {"get"},
    "/v1/catalogos/modulos": {"get"},
    "/v1/catalogos/lotes": {"get"},
    "/v1/evaluaciones": {"post"},
    "/v1/evaluaciones/historial": {"get"},
    "/v1/evaluaciones/{client_id}": {"get"},
}
EXPECTED_EVALUATION_FIELDS = {
    "client_id", "module_key", "fecha", "captured_at", "lote_id", "fundo",
    "modulo", "lote", "cortina", "hilera", "planta", "evaluador",
    "evaluador_id", "evaluador_dni", "item", "piso", "hora", "valores",
}


def test_rutas_y_metodos_siguen_compatibles():
    paths = app.openapi()["paths"]
    actual = {
        path: {method for method in item if method in {"get", "post", "put", "patch", "delete"}}
        for path, item in paths.items()
    }
    assert actual == EXPECTED_OPERATIONS


def test_payload_de_evaluacion_conserva_campos_y_obligatorios():
    schema = app.openapi()["components"]["schemas"]["EvaluationCreate"]
    assert set(schema["properties"]) == EXPECTED_EVALUATION_FIELDS
    assert set(schema["required"]) == {
        "client_id", "module_key", "fecha", "cortina", "hilera", "planta"
    }
    assert schema["properties"]["module_key"]["enum"] == [
        "estadios", "flores", "baya", "pesos", "brotes", "ramas"
    ]
