from __future__ import annotations

from decimal import Decimal

import pytest

from aquanqa_campo_api.modules.evaluaciones.rules import (
    EvaluationValidationError,
    normalize_evaluation,
)
from aquanqa_campo_api.modules.evaluaciones.schemas import EvaluationCreate


def _payload(**overrides):
    payload = {
        "id": "11111111-1111-4111-8111-111111111111",
        "module_key": "estadios",
        "fecha": "2026-08-31T10:30:00Z",
        "lote_id": "12",
        "cortina": "1",
        "hilera": "2",
        "planta": "3",
        "evaluador_dni": "10616663",
        "valores": {
            "m1_e1": 1,
            "m1_e2": 2,
            "m1_e3": 3,
            "m1_e4": 4,
            "m1_e5": 5,
            "m1_total": 15,
        },
    }
    payload.update(overrides)
    return payload


def test_acepta_payload_actual_de_flutter_y_normaliza_estadios():
    evaluation = EvaluationCreate.model_validate(_payload())
    normalized = normalize_evaluation(evaluation)
    assert evaluation.client_id.hex == "11111111111141118111111111111111"
    assert evaluation.fecha.isoformat() == "2026-08-31"
    assert evaluation.lote_id == 12
    assert normalized.data["e5"] == 5
    assert normalized.data["total_origen"] == 15
    assert normalized.data["item"] == "mobile"


def test_normaliza_muestras_de_baya_hasta_la_muestra_50():
    evaluation = EvaluationCreate.model_validate(
        _payload(
            module_key="baya",
            valores={
                "m4_diam01": 12.5,
                "m4_est01": "e3",
                "m4_est02": "Desh",
                "m4_diam50": 20.1,
                "m4_est50": "e5",
            },
        )
    )
    assert normalize_evaluation(evaluation).data["observaciones"] == [
        {"numero_muestra": 1, "estado_codigo": "E3", "diametro_mm": 12.5},
        {"numero_muestra": 2, "estado_codigo": "DESH", "diametro_mm": None},
        {"numero_muestra": 50, "estado_codigo": "E5", "diametro_mm": Decimal("20.1")},
    ]


def test_rechaza_medida_negativa():
    evaluation = EvaluationCreate.model_validate(
        _payload(module_key="baya", valores={"m4_diam01": -1})
    )
    with pytest.raises(EvaluationValidationError, match="mayor que cero"):
        normalize_evaluation(evaluation)


def test_brotes_exige_piso_explicito():
    evaluation = EvaluationCreate.model_validate(
        _payload(module_key="brotes", valores={"m6_brotes": 4})
    )
    with pytest.raises(EvaluationValidationError, match="requiere piso"):
        normalize_evaluation(evaluation)
