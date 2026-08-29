from __future__ import annotations

import pandas as pd
from test_fenologico_v1 import _datos

from analitica.proyeccion.hibrido import priors


def test_cache_de_fuentes_de_calibracion_es_por_snapshot():
    datos = _datos()

    primero = priors._legacy_input_cache(datos)
    segundo = priors._legacy_input_cache(datos)

    assert primero is segundo
    assert ("C2026", "1") in primero["cosecha"]
    assert primero["plantas"]["1"] == 2050.0


def test_cache_de_identidad_agronomica_conserva_lote_fisico():
    datos = _datos()

    primero = priors._metadatos_lotes(datos)
    segundo = priors._metadatos_lotes(datos)

    assert primero is segundo
    assert priors._identidad_lote(datos, 1) == {
        "fundo": "F1",
        "modulo": "M1",
        "variedad": "Sekoya Pop",
    }


def test_prior_grupal_se_reutiliza_solo_para_el_mismo_corte():
    datos = _datos()
    fecha = pd.Timestamp("2026-06-01")

    primero, nivel_primero = priors._prior_grupal_historico(datos, "C2026", 1, 2050.0, fecha)
    segundo, nivel_segundo = priors._prior_grupal_historico(datos, "C2026", 1, 2050.0, fecha)

    assert primero is not None
    assert segundo is primero
    assert nivel_segundo == nivel_primero
    assert datos._legacy_prior_grupo_cache
