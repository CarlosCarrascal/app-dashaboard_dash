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


@pytest.mark.parametrize(
    "state,expected",
    [
        ("Flor", "FLOR"),
        ("Cuajo", "CUAJO"),
        ("E1", "E1"),
        ("E2", "E2"),
        ("E3", "E3"),
        ("E4", "E4"),
        ("E5", "E5"),
        ("Desh", "DESH"),
        ("Caído", "CAIDO"),
        ("CAIDO", "CAIDO"),
        ("X", "X"),
    ],
)
def test_estados_fruto_con_y_sin_diametro(state, expected):
    evaluation = EvaluationCreate.model_validate(
        _payload(
            module_key="baya",
            valores={"m4_est01": state, "m4_diam01": 12.5, "m4_est50": state},
        )
    )
    observations = normalize_evaluation(evaluation).data["observaciones"]
    assert [row["estado_codigo"] for row in observations] == [expected, expected]
    assert observations[0]["diametro_mm"] == Decimal("12.5")
    assert observations[1]["diametro_mm"] is None


def test_rechaza_estado_fruto_desconocido():
    evaluation = EvaluationCreate.model_validate(
        _payload(
            module_key="baya",
            valores={"m4_est01": "INVALIDO"},
        )
    )
    with pytest.raises(EvaluationValidationError, match="no es un estado válido"):
        normalize_evaluation(evaluation)


def test_brotes_exige_piso_explicito():
    evaluation = EvaluationCreate.model_validate(
        _payload(module_key="brotes", valores={"m6_brotes": 4})
    )
    with pytest.raises(EvaluationValidationError, match="requiere piso"):
        normalize_evaluation(evaluation)


def test_flores_normaliza_yemas_muertas_y_brotes_tiernos():
    evaluation = EvaluationCreate.model_validate(
        _payload(
            module_key="flores",
            valores={
                "m2_flores": 12,
                "m2_cuajos": 4,
                "m2_yp": 3,
                "m2_ya": 2,
                "m2_ymuerta": 1,
                "m2_brotes_tiernos": 5,
            },
        )
    )

    normalized = normalize_evaluation(evaluation)

    assert normalized.data["yemas_muertas"] == 1
    assert normalized.data["brotes_tiernos"] == 5


def test_no_inventa_ceros_para_conteos_ausentes():
    result = normalize_evaluation(EvaluationCreate.model_validate(_payload(valores={"m1_e1": 0})))
    assert result.data["e1"] == 0
    assert result.data["e2"] is None


def test_rechaza_campos_fuera_del_contrato_en_vez_de_guardar_ceros():
    with pytest.raises(EvaluationValidationError, match="conteo explícito"):
        normalize_evaluation(EvaluationCreate.model_validate(_payload(valores={"e1": 2})))


@pytest.mark.parametrize(
    "values",
    [
        {"muestras": [{"numero_muestra": 1, "peso_g": 2, "diametro_mm": 3}], "m5_peso01": 2},
        {"muestras": [{"numero_muestra": 1, "peso_g": 2, "diametro_mm": 3}] * 2},
        {"muestras": [{"numero_muestra": True, "peso_g": 2, "diametro_mm": 3}]},
        {"m5_peso01": 2},
        {"m5_diam01": 3},
        {"m5_peso01": "NaN", "m5_diam01": 3},
    ],
)
def test_rechaza_muestras_ambiguas_o_incompletas(values):
    with pytest.raises(EvaluationValidationError):
        normalize_evaluation(
            EvaluationCreate.model_validate(_payload(module_key="pesos", valores=values))
        )
