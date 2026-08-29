from __future__ import annotations

from copy import deepcopy
from datetime import date

import pandas as pd
import pytest

from analitica.proyeccion.candidate_param_delta import CandidateParamDelta


def _parametros_previos() -> dict:
    return {
        "X1": 200.0,
        "O1": 20.0,
        "N1": 100.0,
        "A1": 3.0,
        "B1": -0.0020,
        "%Caida": 0.90,
        "Finicio": date(2026, 5, 1),
        "FePas1": date(2026, 8, 1),
        "sin_modelar": "se conserva",
    }


def _parametros_objetivo(previos: dict, *, x_delta: float = 7.0) -> dict:
    return {
        **previos,
        "X1": previos["X1"] + x_delta,
        "O1": previos["O1"] * 1.10,
        "N1": previos["N1"] * 1.20,
        "A1": previos["A1"] * 0.95,
        "B1": previos["B1"] + 0.0002,
        "%Caida": 0.80,
        "Finicio": previos["Finicio"] + pd.Timedelta(3, unit="D"),
        "FePas1": previos["FePas1"] + pd.Timedelta(5, unit="D"),
    }


def _transicion(
    *,
    fundo: str = "Arena",
    modulo: str = "M01",
    lote: str = "L001",
    variedad: str = "Sekoya Pop",
    x_delta: float = 7.0,
) -> dict:
    previos = _parametros_previos()
    return {
        "parametros_previos": previos,
        "parametros_objetivo": _parametros_objetivo(previos, x_delta=x_delta),
        "contexto": {
            "fundo": fundo,
            "modulo": modulo,
            "lote": lote,
            "variedad": variedad,
        },
        "emision_previa": "2026-08-03",
        "emision_objetivo": "2026-08-10",
    }


def test_aprende_cada_familia_en_su_escala_y_no_muta_entradas():
    transiciones = [_transicion() for _ in range(3)]
    modelo = CandidateParamDelta(regularizacion=0, cuantiles=(0, 1)).fit(transiciones)
    previos = _parametros_previos()
    copia = deepcopy(previos)

    resultado = modelo.predict(
        previos,
        {"fundo": "Arena", "modulo": "M01", "lote": "L001", "variedad": "Sekoya Pop"},
    )
    finales = resultado["parametros"]

    assert previos == copia
    assert finales["X1"] == pytest.approx(207.0)
    assert finales["O1"] == pytest.approx(22.0)
    assert finales["N1"] == pytest.approx(120.0)
    assert finales["A1"] == pytest.approx(2.85)
    assert finales["B1"] == pytest.approx(-0.0018)
    assert finales["%Caida"] == pytest.approx(0.80)
    assert finales["Finicio"] == date(2026, 5, 4)
    assert finales["FePas1"] == date(2026, 8, 6)
    assert finales["sin_modelar"] == "se conserva"
    assert resultado["nivel_calibracion"] == "lote"
    assert resultado["n_observaciones"] == 3
    assert resultado["detalle_calibracion"]["B1"]["transformacion"] == "b_estandarizado"


def test_aplica_jerarquia_y_shrinkage_con_soporte_explicito():
    transiciones = [
        _transicion(lote="L001", x_delta=10),
        _transicion(lote="L001", x_delta=10),
        _transicion(lote="L002", x_delta=2),
        _transicion(fundo="Quri", modulo="M09", lote="L900", x_delta=-2),
    ]
    modelo = CandidateParamDelta(regularizacion=2, cuantiles=(0, 1)).fit(transiciones)

    lote = modelo.predict(
        {"X1": 200.0},
        {"fundo": "Arena", "modulo": "M01", "lote": "L001", "variedad": "Sekoya Pop"},
    )
    modulo = modelo.predict(
        {"X1": 200.0},
        {"fundo": "Arena", "modulo": "M01", "lote": "NUEVO", "variedad": "Sekoya Pop"},
    )
    global_ = modelo.predict(
        {"X1": 200.0},
        {"fundo": "Sin historia", "modulo": "M00", "lote": "NUEVO"},
    )

    assert lote["nivel_calibracion"] == "lote"
    assert lote["n_observaciones"] == 2
    assert modulo["nivel_calibracion"] == "modulo"
    assert modulo["n_observaciones"] == 3
    assert global_["nivel_calibracion"] == "global"
    assert global_["n_observaciones"] == 4
    assert lote["parametros"]["X1"] > modulo["parametros"]["X1"]


def test_limita_un_delta_local_por_cuantiles_del_entrenamiento():
    transiciones = [
        _transicion(lote="L001", x_delta=1),
        _transicion(lote="L002", x_delta=2),
        _transicion(lote="OUTLIER", x_delta=100),
    ]
    modelo = CandidateParamDelta(regularizacion=0, cuantiles=(0.10, 0.90)).fit(transiciones)
    resultado = modelo.predict(
        {"X1": 200.0},
        {"fundo": "Arena", "modulo": "M01", "lote": "OUTLIER"},
    )

    limite_superior = modelo.limites_["X1"][1]
    aplicado = resultado["detalle_calibracion"]["X1"]["delta_aplicado"]
    assert aplicado == pytest.approx(limite_superior)
    assert aplicado < 100


def test_emision_objetivo_y_kilos_r09_no_entran_como_features():
    base = [_transicion(), _transicion(lote="L002", x_delta=4)]
    contaminado = deepcopy(base)
    for indice, fila in enumerate(contaminado):
        fila["emision_objetivo"] = f"2099-12-{indice + 1:02d}"
        fila["kg_r09"] = 10**12 * (indice + 1)
        fila["contexto"]["r09_kg"] = -(10**15)

    primero = CandidateParamDelta(regularizacion=1).fit(base)
    segundo = CandidateParamDelta(regularizacion=1).fit(contaminado)
    contexto = {
        "fundo": "Arena",
        "modulo": "M01",
        "lote": "L001",
        "variedad": "Sekoya Pop",
        "kg_r09": 999_999_999,
        "emision_objetivo": "2100-01-01",
    }

    pred_primero = primero.predict({"X1": 200, "N1": 100}, contexto)
    pred_segundo = segundo.predict({"X1": 200, "N1": 100}, contexto)

    assert primero.feature_names_ == ("fundo", "modulo", "lote", "variedad")
    assert pred_primero == pred_segundo


def test_acepta_formato_plano_y_fepas_dinamicas():
    tabla = pd.DataFrame(
        {
            "fundo": ["Ayllu", "Ayllu"],
            "modulo": ["M02", "M02"],
            "lote_id": ["L010", "L010"],
            "X1_prev": [200.0, 202.0],
            "X1_next": [204.0, 206.0],
            "FePas6_anterior": pd.to_datetime(["2026-09-01", "2026-09-08"]),
            "FePas6_objetivo": pd.to_datetime(["2026-09-03", "2026-09-10"]),
        }
    )
    modelo = CandidateParamDelta(regularizacion=0, cuantiles=(0, 1)).fit(tabla)
    resultado = modelo.predict(
        {"X1": 210.0, "FePas6": date(2026, 10, 1)},
        {"fundo": "Ayllu", "modulo": "M02", "lote_id": "L010"},
    )

    assert resultado["parametros"]["X1"] == pytest.approx(214.0)
    assert resultado["parametros"]["FePas6"] == date(2026, 10, 3)


def test_rechaza_fit_sin_pares_validos_y_predict_sin_fit():
    with pytest.raises(ValueError, match="No hay pares válidos"):
        CandidateParamDelta().fit([{"fundo": "Arena", "kg_r09": 1000}])
    with pytest.raises(RuntimeError, match="ajustarse"):
        CandidateParamDelta().predict({"X1": 200}, {"fundo": "Arena"})
