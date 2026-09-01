from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analitica.aplicacion.parametros.contexto_oleadas import (
    ConfiguracionContextoOleadas,
    ModeloContextoOleadas,
    unir_contexto_asof,
)
from analitica.aplicacion.parametros.oleadas_candidato import (
    proyectar_automatico_oleadas,
    proyectar_universo_automatico_oleadas,
)


def _transiciones() -> pd.DataFrame:
    filas = []
    for indice in range(20):
        fecha = pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=indice)
        gdd = float(indice)
        filas.append(
            {
                "campania": "C2026",
                "fundo": "Arena",
                "modulo": "M01",
                "lote": "L001",
                "fecha_emision_actual": fecha,
                "X1_anterior": 200.0,
                "X1_actual": 200.0 + 0.4 * gdd,
                "gdd_acum_poda_obs": gdd,
                "dias_desde_poda": 120.0 + gdd,
            }
        )
    return pd.DataFrame(filas)


def _modelo() -> ModeloContextoOleadas:
    return ModeloContextoOleadas(
        feature_names=("gdd_acum_poda_obs", "dias_desde_poda"),
        config=ConfiguracionContextoOleadas(
            regularizacion=1.0,
            minimo_observaciones=8,
            minima_cobertura=0.5,
        ),
    ).fit(_transiciones(), fecha_corte="2026-05-01")


def test_modelo_aprende_delta_de_contexto_y_entrega_driver_mecanico():
    modelo = _modelo()

    bajo = modelo.predict(
        {"X1": 200.0},
        {"gdd_acum_poda_obs": 1.0, "dias_desde_poda": 121.0},
    )
    alto = modelo.predict(
        {"X1": 200.0},
        {"gdd_acum_poda_obs": 11.0, "dias_desde_poda": 131.0},
    )

    assert modelo.parametros_aprendidos_ == ("X1",)
    assert modelo.n_transiciones_ < len(_transiciones())
    assert alto["parametros"]["X1"] > bajo["parametros"]["X1"]
    assert alto["nivel_calibracion"] == "contexto_continuo"
    assert alto["detalle_calibracion"]["X1"]["driver_principal"] in {
        "gdd_acum_poda_obs",
        "dias_desde_poda",
    }
    assert alto["etiqueta_causal"] is False


def test_fit_asof_no_lee_transiciones_posteriores_al_corte():
    base = _transiciones()
    mutada = base.copy()
    futuro = pd.to_datetime(mutada.fecha_emision_actual).ge(pd.Timestamp("2026-05-01"))
    mutada.loc[futuro, "X1_actual"] = 9999.0

    primero = _modelo().predict(
        {"X1": 200.0},
        {"gdd_acum_poda_obs": 6.0, "dias_desde_poda": 126.0},
    )
    segundo = ModeloContextoOleadas(
        feature_names=("gdd_acum_poda_obs", "dias_desde_poda"),
        config=ConfiguracionContextoOleadas(
            regularizacion=1.0,
            minimo_observaciones=8,
            minima_cobertura=0.5,
        ),
    ).fit(mutada, fecha_corte="2026-05-01").predict(
        {"X1": 200.0},
        {"gdd_acum_poda_obs": 6.0, "dias_desde_poda": 126.0},
    )

    assert segundo["parametros"]["X1"] == pytest.approx(primero["parametros"]["X1"])


def test_union_contexto_excluye_fecha_de_emision():
    transiciones = pd.DataFrame(
        {
            "campania": ["C2026"],
            "fundo": ["Arena"],
            "modulo": ["M01"],
            "lote": ["L001"],
            "fecha_emision_actual": [pd.Timestamp("2026-03-15")],
        }
    )
    contexto = pd.DataFrame(
        {
            "campania": ["C2026", "C2026", "C2026"],
            "fundo": ["Arena"] * 3,
            "modulo": ["M01"] * 3,
            "lote": ["L001"] * 3,
            "fecha_dato": pd.to_datetime(["2026-03-01", "2026-03-15", "2026-03-20"]),
            "gdd_acum_poda_obs": [10.0, 99.0, 200.0],
        }
    )

    salida, metadata = unir_contexto_asof(transiciones, contexto)

    assert salida.loc[0, "gdd_acum_poda_obs"] == 10.0
    assert salida.loc[0, "fecha_contexto_asof"] == pd.Timestamp("2026-03-01")
    assert metadata["fuga"] is False
    assert metadata["filas_con_contexto"] == 1


def test_union_contexto_puede_forzar_claves_fisicas_y_no_deja_auxiliares():
    transiciones = pd.DataFrame(
        {
            "campania": ["C2026"],
            "fundo": ["nombre_distinto"],
            "modulo": ["M01"],
            "turno": ["T01"],
            "lote": ["L001"],
            "fecha_emision_actual": [pd.Timestamp("2026-03-15")],
        }
    )
    contexto = pd.DataFrame(
        {
            "campania": ["C2026"],
            "fundo": ["otro_nombre"],
            "modulo": ["M01"],
            "turno": ["T01"],
            "lote": ["L001"],
            "fecha_dato": [pd.Timestamp("2026-03-01")],
            "gdd_acum_poda_obs": [10.0],
        }
    )

    salida, metadata = unir_contexto_asof(
        transiciones,
        contexto,
        claves_union=("campania", "modulo", "turno", "lote"),
    )

    assert salida.loc[0, "gdd_acum_poda_obs"] == 10.0
    assert "__contexto_gdd_acum_poda_obs" not in salida.columns
    assert metadata["claves_union"] == ["campania", "modulo", "turno", "lote"]


def test_contexto_se_integra_en_la_ruta_automatica_sin_excel():
    modelo = _modelo()
    bajo, meta_bajo = proyectar_automatico_oleadas(
        "2026-06-01",
        fecha_pivote="2025-10-01",
        plantas=5000,
        modelo_contexto=modelo,
        contexto={"gdd_acum_poda_obs": 1.0, "dias_desde_poda": 121.0},
    )
    alto, meta_alto = proyectar_automatico_oleadas(
        "2026-06-01",
        fecha_pivote="2025-10-01",
        plantas=5000,
        modelo_contexto=modelo,
        contexto={"gdd_acum_poda_obs": 11.0, "dias_desde_poda": 131.0},
    )

    assert meta_alto["nivel_contexto"] == "contexto_continuo"
    assert meta_alto["detalle_contexto"]
    assert not np.allclose(alto.kg.to_numpy(), bajo.kg.to_numpy())
    assert meta_bajo["publicable"] is False


def test_contexto_se_propaga_al_universo_automatico():
    modelo = _modelo()
    lotes = pd.DataFrame(
        {
            "campania": ["C2026"],
            "fundo": ["Arena"],
            "modulo": ["M01"],
            "turno": ["T01"],
            "lote": ["L001"],
            "area": [1.0],
            "n_plantas": [1000],
            "fecha_inicio": ["2025-10-01"],
        }
    )
    salida, metadata = proyectar_universo_automatico_oleadas(
        lotes,
        None,
        "2026-06-01",
        modelo_contexto=modelo,
        contexto_por_lote={
            ("C2026", "Arena", "M01", "T01", "L001"): {
                "gdd_acum_poda_obs": 11.0,
                "dias_desde_poda": 131.0,
            }
        },
    )

    assert len(salida) == 6
    assert salida["nivel_contexto"].eq("contexto_continuo").all()
    assert metadata["lotes_con_modelo_contexto"] == 1


def test_universo_automatico_usa_identidad_fisica_si_el_fundo_cambia_de_nombre():
    lotes = pd.DataFrame(
        {
            "campania": ["C2026"],
            "fundo": ["Nombre del maestro"],
            "modulo": ["M01"],
            "turno": ["T01"],
            "lote": ["L001"],
            "area": [1.0],
            "n_plantas": [1000],
            "fecha_inicio": ["2025-10-01"],
        }
    )
    cosecha = pd.DataFrame(
        {
            "campania": ["C2026"],
            "fundo": ["Nombre de H01"],
            "modulo": ["M01"],
            "turno": ["T01"],
            "lote": ["L001"],
            "fecha": ["2026-05-25"],
            "kg": [100.0],
            "peso": [4.0],
        }
    )

    salida, metadata = proyectar_universo_automatico_oleadas(
        lotes,
        cosecha,
        "2026-06-01",
        semanas=6,
    )

    assert salida["tiene_historia_asof"].all()
    assert metadata["lotes_con_historia_asof"] == 1
