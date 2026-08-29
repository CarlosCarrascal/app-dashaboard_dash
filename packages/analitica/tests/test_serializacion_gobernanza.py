import json

import numpy as np
import pandas as pd

from analitica import settings
from analitica.proyeccion import tracking
from analitica.proyeccion.gobernanza import (
    RepositorioAnalytics,
    _json,
    _limpio,
    commit_actual,
    log_metricas_mlflow,
    registrar_modelos_mlflow,
    tracking_mlflow,
)
from analitica.proyeccion.infraestructura.git import commit_actual as commit_actual_git
from analitica.proyeccion.infraestructura.serializacion import (
    limpiar_valor,
    serializar_json,
    serializar_jsonb,
)
from analitica.proyeccion.persistencia.repositorio import (
    RepositorioAnalytics as RepositorioPersistencia,
)


def test_serializador_json_conserva_metadatos_validos_para_jsonb():
    resultado = serializar_json(
        {
            "entero": np.int64(4),
            "fecha": pd.Timestamp("2026-08-26"),
            "faltante": np.nan,
            "lista": [pd.NA, 2.5],
        }
    )

    assert json.loads(resultado) == {
        "entero": 4,
        "fecha": "2026-08-26T00:00:00",
        "faltante": None,
        "lista": [None, 2.5],
    }


def test_serializador_jsonb_desenvuelve_objetos_y_listas_json():
    assert json.loads(serializar_jsonb('{"campania": "C2026"}')) == {"campania": "C2026"}
    assert json.loads(serializar_jsonb('["as-of"]')) == ["as-of"]
    assert json.loads(serializar_jsonb({"campania": "C2026"})) == {"campania": "C2026"}
    assert json.loads(serializar_jsonb(["as-of"])) == ["as-of"]


def test_fachadas_privadas_de_gobernanza_conservan_los_serializadores():
    assert _json is serializar_json
    assert _limpio is limpiar_valor
    assert limpiar_valor(np.float64(3.5)) == 3.5
    assert limpiar_valor(np.nan) is None
    assert limpiar_valor([np.nan, np.float64(2.0)]) == [None, 2.0]


def test_gobernanza_conserva_fachadas_de_tracking_y_commit():
    assert commit_actual is commit_actual_git
    assert RepositorioAnalytics is RepositorioPersistencia
    assert tracking_mlflow is tracking.tracking_mlflow
    assert log_metricas_mlflow is tracking.log_metricas_mlflow
    assert registrar_modelos_mlflow is tracking.registrar_modelos_mlflow


def test_tracking_sin_uri_no_abre_un_run_implicitamente(monkeypatch):
    monkeypatch.setattr(settings, "MLFLOW_TRACKING_URI", None)
    fuente = type(
        "Fuente",
        (),
        {"nombre": "test", "firma": "abc", "fallback": False, "conteos": {}},
    )()
    with tracking_mlflow("test", fuente, {}) as run_id:
        assert run_id is None
