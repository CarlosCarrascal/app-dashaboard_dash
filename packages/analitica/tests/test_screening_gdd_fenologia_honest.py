from __future__ import annotations

import ast
import inspect
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.scripts.screening_gdd_fenologia_honest import (
    SQL_CLIMA,
    SQL_ESTADOS,
    SQL_FLORES,
    SQL_MACRO,
    Configuracion,
    aplicar_desplazamientos,
    construir_clima_asof,
    evaluar_gates,
    preparar_clima,
    redistribuir_curva,
    seleccionar_configuracion,
)
from analitica.servicios import fenologia_honest as SERVICIO

SCRIPT = Path(__file__).parents[1] / "scripts" / "screening_gdd_fenologia_honest.py"


def test_la_fachada_reexporta_el_servicio_unico_y_conserva_firmas() -> None:
    nombres = (
        "leer_fuentes",
        "preparar_macro",
        "preparar_clima",
        "construir_clima_asof",
        "construir_fenologia_asof",
        "agregar_curvas_fundo",
        "redistribuir_curva",
        "construir_panel_features",
        "calcular_desplazamientos",
        "aplicar_desplazamientos",
        "metricas",
        "metricas_por_fundo",
        "seleccionar_configuracion",
        "evaluar_gates",
        "evaluar",
    )
    import analitica.scripts.screening_gdd_fenologia_honest as FACHADA

    for nombre in nombres:
        fachada = getattr(FACHADA, nombre)
        servicio = getattr(SERVICIO, nombre)
        assert fachada is servicio
        assert inspect.signature(fachada) == inspect.signature(servicio)

    for nombre in (
        "CAMPANIA",
        "RUN_ID",
        "HORIZONTES",
        "TBASES",
        "VENTANAS",
        "FUNDOS",
        "SQL_MACRO",
        "SQL_CLIMA",
        "SQL_ESTADOS",
        "SQL_FLORES",
    ):
        assert getattr(FACHADA, nombre) is getattr(SERVICIO, nombre)
    assert FACHADA.Configuracion is SERVICIO.Configuracion


def test_el_script_solo_conserva_el_adaptador_cli() -> None:
    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    definiciones = [
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
    ]


def _curvas_sinteticas() -> tuple[pd.DataFrame, pd.DataFrame]:
    curvas: list[dict[str, object]] = []
    features: list[dict[str, object]] = []
    for semana in range(13, 34):
        objetivo_h1 = pd.Timestamp.fromisocalendar(2026, semana, 1)
        emision = objetivo_h1 - pd.Timedelta(days=7)
        split = (
            "desarrollo_temprano"
            if semana <= 24
            else "desarrollo_tardio"
            if semana <= 30
            else "holdout_s31_s33"
        )
        for indice_fundo, fundo in enumerate(("Arena", "Ayllu", "Kawsay", "Quri")):
            features.append(
                {
                    "fecha_emision": emision,
                    "fundo_operativo": fundo,
                    "semana_h1": semana,
                    "indice_estado": 2.0 + 0.05 * semana + 0.1 * indice_fundo,
                    "cobertura_estados": 1.0,
                    "cobertura_flores": 1.0,
                }
            )
            for horizonte in range(1, 7):
                macro = float(100 + 15 * horizonte + 3 * indice_fundo)
                # En desarrollo el real favorece un desplazamiento suave; el
                # holdout no debe intervenir en la selección.
                real = macro * (1.0 + 0.02 * np.sin(semana + horizonte))
                curvas.append(
                    {
                        "campania": "C2026",
                        "fecha_emision": emision,
                        "fecha_objetivo": emision + pd.Timedelta(weeks=horizonte),
                        "horizonte_semanas": horizonte,
                        "semana_objetivo": int(
                            (emision + pd.Timedelta(weeks=horizonte)).isocalendar().week
                        ),
                        "split": split
                        if horizonte == 1
                        else (
                            "desarrollo_temprano"
                            if int((emision + pd.Timedelta(weeks=horizonte)).isocalendar().week)
                            <= 24
                            else "desarrollo_tardio"
                            if int((emision + pd.Timedelta(weeks=horizonte)).isocalendar().week)
                            <= 30
                            else "holdout_s31_s33"
                            if int((emision + pd.Timedelta(weeks=horizonte)).isocalendar().week)
                            <= 33
                            else "fuera_evaluacion"
                        ),
                        "fundo_operativo": fundo,
                        "macro_kg": macro,
                        "real_kg": real,
                    }
                )
    return pd.DataFrame(curvas), pd.DataFrame(features)


def test_clima_asof_excluye_dia_de_emision_y_futuro() -> None:
    clima = pd.DataFrame(
        {
            "fecha_hora": pd.date_range("2026-01-01", periods=12, freq="D"),
            "temp": np.arange(12, dtype=float) + 20,
            "temp_alta": np.arange(12, dtype=float) + 22,
            "temp_baja": np.arange(12, dtype=float) + 18,
            "humedad": 70.0,
            "et_mm": 1.0,
        }
    )
    emision = pd.Timestamp("2026-01-10")
    original = construir_clima_asof([emision], preparar_clima(clima))

    mutado = clima.copy()
    mutado.loc[mutado.fecha_hora.ge(emision), ["temp", "temp_alta", "temp_baja"]] = 9999
    repetido = construir_clima_asof([emision], preparar_clima(mutado))

    pd.testing.assert_frame_equal(original, repetido)
    assert original.loc[0, "clima_cobertura_7d"] == 1.0


def test_desplazamiento_solo_mueve_calendario_y_conserva_kg() -> None:
    curva = np.asarray([10, 20, 30, 40, 50, 60], dtype=float)
    adelantada = redistribuir_curva(curva, -0.5)
    retrasada = redistribuir_curva(curva, 0.5)

    assert adelantada.sum() == curva.sum()
    assert retrasada.sum() == curva.sum()
    assert not np.array_equal(adelantada, curva)
    assert not np.array_equal(retrasada, curva)


def test_seleccion_no_cambia_al_mutar_real_del_holdout() -> None:
    curvas, panel = _curvas_sinteticas()
    configs = [
        Configuracion("sin_desplazamiento"),
        Configuracion(
            "fenologia",
            variable_fenologia="indice_estado",
            coef_fenologia=-0.25,
        ),
        Configuracion(
            "fenologia",
            variable_fenologia="indice_estado",
            coef_fenologia=0.25,
        ),
    ]
    elegido, _, top = seleccionar_configuracion(curvas, panel, scope="h1", configuraciones=configs)

    mutado = curvas.copy()
    mutado.loc[mutado.split.eq("holdout_s31_s33"), "real_kg"] *= 1000
    elegido_mutado, _, top_mutado = seleccionar_configuracion(
        mutado, panel, scope="h1", configuraciones=configs
    )

    assert elegido.id == elegido_mutado.id
    assert [fila["score_desarrollo"] for fila in top] == [
        fila["score_desarrollo"] for fila in top_mutado
    ]


def test_gate_rechaza_cobertura_temporal_insuficiente() -> None:
    curvas, _ = _curvas_sinteticas()
    desplazamientos = curvas[["fecha_emision", "fundo_operativo"]].drop_duplicates()
    desplazamientos["desplazamiento_semanas"] = 0.0
    desplazamientos["feature_usable"] = False
    candidato = aplicar_desplazamientos(curvas, desplazamientos)

    resultado = evaluar_gates(candidato, scope="h1")

    assert resultado["aceptado"] is False
    assert resultado["cobertura_feature"] == 0.0
    assert any("cobertura temporal" in razon for razon in resultado["razones_rechazo"])


def test_el_screening_no_admite_r09_como_variable() -> None:
    campos = set(Configuracion.__dataclass_fields__)
    assert not any("r09" in campo.casefold() for campo in campos)

    consultas = "\n".join((SQL_MACRO, SQL_CLIMA, SQL_ESTADOS, SQL_FLORES))
    assert "r09" not in consultas.casefold()
