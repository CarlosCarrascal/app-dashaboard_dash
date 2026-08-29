from __future__ import annotations

import pandas as pd
import pytest

from analitica.proyeccion.componentes import FEATURES_FRUTOS, FEATURES_PESO
from analitica.proyeccion.engine import (
    ProjectionConfig,
    ProjectionScenario,
    proyectar_desde_corte,
)


def _r09() -> pd.DataFrame:
    filas = []
    emision = pd.Timestamp("2026-08-03")
    for horizonte in (1, 2, 6, 11):
        objetivo = emision + pd.Timedelta(weeks=horizonte)
        filas.append(
            {
                "modelo": "R09_publicado",
                "campania": "C2026",
                "lote_id": 10,
                "lote": "L010",
                "fundo": "F1",
                "modulo": "M1",
                "fecha_emision": emision,
                "fecha_objetivo": objetivo,
                "horizonte_semanas": horizonte,
                "banda_horizonte": "operativo" if horizonte <= 2 else "planificacion",
                "p10_kg": 80.0,
                "p50_kg": 100.0,
                "p90_kg": 120.0,
                "real_kg": None,
                "plantas": 1000.0,
                "frutos_por_planta": 20.0,
                "peso_baya_g": 5.0,
            }
        )
    return pd.DataFrame(filas)


def test_el_motor_permite_horizonte_y_semanas_explicitas():
    salida = proyectar_desde_corte(
        _r09(),
        config=ProjectionConfig(
            fecha_emision="2026-08-03",
            horizonte_semanas=6,
            modelo="R09_publicado",
            horizontes=(2, 6),
        ),
    )
    assert set(salida.horizonte_semanas) == {2, 6}
    assert salida.modo_proyeccion.eq("ciega_asof").all()
    assert salida.calendario_fuente.eq("R09_publicado").all()


def test_r09_operativo_conserva_la_semana_de_emision_sin_relajar_el_replay():
    tabla = _r09()
    actual = tabla.iloc[[0]].copy()
    actual["fecha_objetivo"] = actual["fecha_emision"]
    actual["horizonte_semanas"] = 0
    tabla = pd.concat([actual, tabla], ignore_index=True)

    salida = proyectar_desde_corte(
        tabla,
        config=ProjectionConfig(
            fecha_emision="2026-08-03",
            horizonte_semanas=2,
            modelo="R09_publicado",
        ),
    )

    assert set(salida.horizonte_semanas) == {0, 1, 2}


def test_el_escenario_recalcula_las_piezas_y_deja_trazabilidad():
    salida = proyectar_desde_corte(
        _r09(),
        config=ProjectionConfig(
            fecha_emision="2026-08-03",
            horizonte_semanas=2,
            modelo="R09_publicado",
            escenario=ProjectionScenario(nombre="carga_mayor", frutos_pct=10, peso_pct=5),
        ),
    )
    fila = salida.iloc[0]
    assert fila.frutos_por_planta == pytest.approx(22.0)
    assert fila.peso_baya_g == pytest.approx(5.25)
    assert fila.p50_kg == pytest.approx(100 * 1.10 * 1.05)
    assert fila.componentes["escenario"]["interpretacion"] == "escenario mecánico, no efecto causal"


def test_el_modelo_nuevo_no_usa_los_componentes_publicados_por_r09():
    assert "frutos_por_planta" not in FEATURES_FRUTOS
    assert "peso_baya_g" not in FEATURES_PESO


def test_el_observado_se_conserva_solo_para_evaluar_el_replay():
    tabla = _r09()
    tabla.loc[tabla.horizonte_semanas.eq(2), "real_kg"] = 85.0
    salida = proyectar_desde_corte(
        tabla,
        config=ProjectionConfig(
            fecha_emision="2026-08-03",
            horizonte_semanas=2,
            modelo="R09_publicado",
        ),
    )
    assert salida.loc[salida.horizonte_semanas.eq(2), "real_kg"].iloc[0] == pytest.approx(85.0)
