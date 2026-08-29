from __future__ import annotations

import ast
import inspect
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.servicios import fenologia_honest as fachada
from analitica.servicios import fenologia_honest_contratos as contratos
from analitica.servicios import fenologia_honest_evaluacion as evaluacion
from analitica.servicios import fenologia_honest_fuentes as fuentes
from analitica.servicios import fenologia_honest_modelo as modelo
from analitica.servicios import fenologia_honest_salida as salida

SERVICIOS = Path(__file__).parents[1] / "servicios"


def test_fachada_conserva_aliases_y_firmas_de_la_api() -> None:
    aliases = {
        contratos: (
            "CAMPANIA",
            "CIERRE_CERTIFICADO",
            "Configuracion",
            "FUNDOS",
            "HORIZONTES",
            "MAPEO_FUNDO",
            "RUN_ID",
            "RUNS_EXTERNOS",
            "SEMANA_DESARROLLO_FINAL",
            "SEMANA_INICIAL",
            "SEMANAS_HOLDOUT",
            "SQL_CLIMA",
            "SQL_ESTADOS",
            "SQL_FLORES",
            "SQL_MACRO",
            "TBASES",
            "VENTANAS",
        ),
        fuentes: (
            "_leer_dataframe",
            "_normalizar_fundo",
            "_preparar_estados",
            "_preparar_flores",
            "agregar_curvas_fundo",
            "construir_clima_asof",
            "construir_fenologia_asof",
            "leer_fuentes",
            "preparar_clima",
            "preparar_macro",
        ),
        modelo: (
            "_columna_clima",
            "_escalar_entrenamiento",
            "aplicar_desplazamientos",
            "calcular_desplazamientos",
            "construir_panel_features",
            "redistribuir_curva",
        ),
        evaluacion: (
            "_cobertura_fuentes",
            "_configuraciones",
            "_evaluar_externa",
            "_filtro_scope",
            "_resumen_config",
            "evaluar",
            "evaluar_gates",
            "metricas",
            "metricas_por_fundo",
            "seleccionar_configuracion",
        ),
        salida: ("_json_limpio",),
    }

    for modulo, nombres in aliases.items():
        for nombre in nombres:
            assert getattr(fachada, nombre) is getattr(modulo, nombre)
            objeto = getattr(fachada, nombre)
            if callable(objeto):
                assert inspect.signature(objeto) == inspect.signature(getattr(modulo, nombre))


def test_fachada_no_contiene_implementacion_y_las_capas_no_importan_hacia_arriba() -> None:
    arbol = ast.parse(
        (SERVICIOS / "fenologia_honest.py").read_text(encoding="utf-8"),
        filename=str(SERVICIOS / "fenologia_honest.py"),
    )
    assert not [
        nodo
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]

    permitido = {
        "fenologia_honest_contratos.py": set(),
        "fenologia_honest_fuentes.py": {"fenologia_honest_contratos"},
        "fenologia_honest_modelo.py": {"fenologia_honest_contratos"},
        "fenologia_honest_evaluacion.py": {
            "fenologia_honest_contratos",
            "fenologia_honest_fuentes",
            "fenologia_honest_modelo",
            "fenologia_honest_salida",
        },
        "fenologia_honest_salida.py": {"fenologia_honest_contratos"},
    }
    for nombre, esperadas in permitido.items():
        modulo = SERVICIOS / nombre
        arbol = ast.parse(modulo.read_text(encoding="utf-8"), filename=str(modulo))
        importaciones = {
            nodo.module
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom)
            and nodo.level
            and nodo.module
            and nodo.module.startswith("fenologia_honest")
        }
        assert importaciones == esperadas


def test_contratos_y_salida_mantienen_literales_criticos() -> None:
    assert contratos.HORIZONTES == (1, 2, 3, 4, 5, 6)
    assert contratos.SEMANAS_HOLDOUT == (31, 32, 33)
    assert contratos.CIERRE_CERTIFICADO.isoformat() == "2026-08-16T00:00:00"
    assert "MacroLegacy_v1" in contratos.SQL_MACRO
    assert "r09" not in " ".join(
        (contratos.SQL_MACRO, contratos.SQL_CLIMA, contratos.SQL_ESTADOS, contratos.SQL_FLORES)
    ).casefold()
    assert salida._json_limpio({"fecha": contratos.CIERRE_CERTIFICADO, "valor": float("nan")}) == {
        "fecha": "2026-08-16T00:00:00",
        "valor": None,
    }


def test_evaluar_conecta_evaluacion_con_salida_sin_alterar_el_contrato(monkeypatch) -> None:
    monkeypatch.setattr(
        evaluacion, "_configuraciones", lambda: [contratos.Configuracion("sin_desplazamiento")]
    )
    emisiones = pd.Timestamp("2026-07-20")
    fundos = ("Arena", "Ayllu", "Kawsay", "Quri")
    macro = pd.DataFrame(
        [
            {
                "campania": "C2026",
                "fecha_emision": emisiones,
                "fecha_objetivo": emisiones + pd.Timedelta(weeks=horizonte),
                "horizonte_semanas": horizonte,
                "lote_id": indice,
                "fundo": fundo,
                "modulo": "M1",
                "p50_kg": 100.0 + horizonte,
                "real_kg": 100.0 + horizonte,
            }
            for indice, fundo in enumerate(fundos, start=1)
            for horizonte in range(1, 7)
        ]
    )
    clima = pd.DataFrame(
        {
            "fecha_hora": pd.date_range("2026-07-01", periods=19, freq="D"),
            "temp": 20.0,
            "temp_alta": 22.0,
            "temp_baja": 18.0,
            "humedad": 70.0,
            "et_mm": 1.0,
        }
    )
    estados = pd.DataFrame(
        {
            "lote_id": range(1, 5),
            "fecha": emisiones - pd.Timedelta(days=7),
            "e1": 1.0,
            "e2": 2.0,
            "e3": 3.0,
            "e4": 4.0,
            "e5": 5.0,
        }
    )
    flores = pd.DataFrame(
        {
            "lote_id": range(1, 5),
            "fecha": emisiones - pd.Timedelta(days=7),
            "planta": 1,
            "n_flores": 10.0,
            "cuajo": 2.0,
        }
    )

    resultado = fachada.evaluar(macro, clima, estados, flores, evaluar_externas=False)

    assert resultado["experimento"] == "screening_gdd_fenologia_honest_v1"
    assert resultado["fuentes"]["filas_estados"] == 4
    assert resultado["fuentes"]["filas_flores"] == 4
    assert set(resultado["resultados"]) == {"h1", "h2_6"}


def test_resumen_config_no_emite_runtimewarning_si_no_hay_wape(monkeypatch) -> None:
    monkeypatch.setattr(evaluacion, "calcular_desplazamientos", lambda *_args: ({}, {}))
    monkeypatch.setattr(evaluacion, "aplicar_desplazamientos", lambda curvas, _cambios: curvas)
    respuestas = iter([{"wape": np.nan}] * 4)
    monkeypatch.setattr(evaluacion, "metricas", lambda *_args, **_kwargs: next(respuestas))

    with warnings.catch_warnings(record=True) as capturadas:
        warnings.simplefilter("always")
        resumen, _, _ = evaluacion._resumen_config(
            pd.DataFrame(),
            pd.DataFrame(),
            contratos.Configuracion("sin_desplazamiento"),
            scope="h1",
        )

    assert not any(issubclass(aviso.category, RuntimeWarning) for aviso in capturadas)
    assert np.isnan(resumen["score_desarrollo"])
