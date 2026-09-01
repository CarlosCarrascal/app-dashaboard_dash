from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.aplicacion.parametros.contexto_exportado import (
    construir_contexto_oleadas_asof,
    construir_contexto_por_lote_oleadas_asof,
)


def _transiciones() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "fundo": ["Nombre operativo", "Nombre operativo"],
            "modulo": ["M01", "M01"],
            "turno": ["T01", "T01"],
            "lote": ["L001", "L001"],
            "fecha_emision_actual": pd.to_datetime(["2026-03-15", "2026-03-20"]),
        }
    )


def _poda() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "fundo": ["Aqu Anqa", "Aqu Anqa"],
            "modulo": ["M01", "M01"],
            "turno": ["T01", "T01"],
            "lote": ["L001", "L002"],
            "fecha_inicio": ["2026-02-01", "2026-02-05"],
            "area": [1.0, 1.2],
        }
    )


def _clima() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha": pd.to_datetime(
                ["2026-02-01", "2026-02-15", "2026-03-13", "2026-03-15", "2026-03-19"]
            ),
            "temp": [10.0, 15.0, 20.0, 30.0, 22.0],
            "humedad": [80.0, 70.0, 60.0, 55.0, 65.0],
            "rad_sol": [1.0, 2.0, 3.0, 99.0, 4.0],
            "et_mm": [0.1, 0.2, 0.3, 9.9, 0.4],
            "lluvia": [0.0, 0.0, 0.0, 0.0, 0.0],
        }
    )


def _flores() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha": ["2026-03-14", "2026-03-14", "2026-03-16"],
            "modulo": ["M01", "M01", "M01"],
            "lote": ["L001", "L001", "L001"],
            "planta": [1, 2, 1],
            "n_flores": [10.0, 20.0, 40.0],
            "cuajo": [5.0, 10.0, 20.0],
        }
    )


def _estados() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha": ["2026-03-14", "2026-03-16"],
            "modulo": ["M01", "M01"],
            "lote": ["L001", "L001"],
            "e1": [10, 0],
            "e2": [10, 0],
            "e3": [0, 10],
            "e4": [0, 10],
            "e5": [0, 0],
        }
    )


def _cosecha() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campania": ["C2026", "C2026", "C2026"],
            "fundo": ["Aqu Anqa"] * 3,
            "modulo": ["M01"] * 3,
            "turno": ["T01"] * 3,
            "lote": ["L001"] * 3,
            "fecha": ["2026-03-01", "2026-03-15", "2026-03-18"],
            "kg": [10.0, 20.0, 30.0],
        }
    )


def test_ensamblador_construye_features_y_excluye_datos_del_dia_de_emision():
    salida, metadata = construir_contexto_oleadas_asof(
        _transiciones(),
        poda=_poda(),
        clima=_clima(),
        flores=_flores(),
        estados=_estados(),
        cosecha=_cosecha(),
    )

    primera = salida.iloc[0]
    segunda = salida.iloc[1]
    assert primera.fecha_contexto_clima == pd.Timestamp("2026-03-13")
    assert segunda.fecha_contexto_clima == pd.Timestamp("2026-03-19")
    assert primera.Rad == 3.0
    assert primera.ETo == 0.3
    assert primera.dias_desde_poda == 42
    assert primera.poda_dispersion_dias == 4
    assert primera.flores_promedio == 15.0
    assert primera.tasa_cuajo == 0.5
    assert primera.kg_real_acumulado == 10.0
    assert primera.kg_ultimas_4_semanas_asof == 10.0
    assert segunda.kg_real_acumulado == 60.0
    assert segunda.kg_ultimas_4_semanas_asof == 60.0
    assert metadata["fuga"] is False
    assert metadata["fuentes"]["flores_union"]["fuga"] is False
    assert metadata["fuentes"]["cosecha_union"]["fuga"] is False
    assert np.isfinite(primera.gdd_acum_poda_obs)
    assert primera.gdd_acum_poda_obs > 0


def test_contexto_por_lote_queda_listo_para_la_ruta_automatica():
    lotes = pd.DataFrame(
        {
            "campania": ["C2026"],
            "fundo": ["Nombre operativo"],
            "modulo": ["M01"],
            "turno": ["T01"],
            "lote": ["L001"],
            "area": [1.0],
            "n_plantas": [1000],
            "fecha_inicio": ["2026-02-01"],
        }
    )

    contexto, metadata = construir_contexto_por_lote_oleadas_asof(
        lotes,
        "2026-03-15",
        poda=_poda(),
        clima=_clima(),
        flores=_flores(),
        estados=_estados(),
        cosecha=_cosecha(),
    )

    clave = ("C2026", "Nombre operativo", "M01", "T01", "L001")
    assert set(contexto) == {clave}
    assert contexto[clave]["Rad"] == 3.0
    assert contexto[clave]["kg_real_acumulado"] == 10.0
    assert metadata["lotes"] == 1
    assert metadata["lotes_con_contexto"] == 1


def test_acepta_encabezados_de_las_hojas_revisadas_y_corta_as_of():
    clima = pd.DataFrame(
        {
            "Fecha": pd.to_datetime(["2026-03-18", "2026-03-19", "2026-03-20"]),
            "Temperatura maxima": [30.0, 31.0, 99.0],
            "Temperatura minima": [20.0, 21.0, 99.0],
            "Radiacion Solar": [100.0, 110.0, 999.0],
            "ETO": [4.0, 5.0, 99.0],
            "Suma de GDD": [10.0, 11.0, 999.0],
            "Suma Lluvia": [0.0, 0.0, 99.0],
        }
    )
    flores = pd.DataFrame(
        {
            "FundoAc": ["Aqu Anqa I", "Aqu Anqa I"],
            "Modulo": ["M01", "M01"],
            "Turno": ["T01", "T01"],
            "Promedio de Fecha": pd.to_datetime(["2026-03-18", "2026-03-20"]),
            "Cantidad Flores": [40.0, 999.0],
            "Dias desde Poda": [70.0, 999.0],
        }
    )
    riego = pd.DataFrame(
        {
            "Fundo": ["Aqu Anqa I", "Aqu Anqa I"],
            "Modulo": ["M01", "M01"],
            "Fecha": pd.to_datetime(["2026-03-18", "2026-03-19"]),
            "Agua/ha": [10.0, 20.0],
        }
    )

    salida, metadata = construir_contexto_oleadas_asof(
        _transiciones().iloc[[1]].assign(
            fecha_emision_actual=pd.Timestamp("2026-03-20")
        ),
        clima=clima,
        flores=flores,
        riego=riego,
    )

    fila = salida.iloc[0]
    assert fila.fecha_contexto_clima == pd.Timestamp("2026-03-19")
    assert fila.Rad == 110.0
    assert fila.ETo == 5.0
    assert fila.gdd_28d == 21.0
    assert fila.fecha_contexto_flores == pd.Timestamp("2026-03-18")
    assert fila.flores_promedio == 40.0
    assert fila.dias_desde_poda == 70.0
    assert fila.fecha_contexto_riego == pd.Timestamp("2026-03-19")
    assert fila.riego_agua_ha == 30.0
    assert pd.isna(fila.riego_m3_ha)
    assert metadata["fuentes"]["clima"]["gdd_directo"] is True
    assert metadata["fuga"] is False


def test_conserva_m3_ha_cuando_la_unidad_esta_declara_en_el_encabezado():
    riego = pd.DataFrame(
        {
            "Modulo": ["M01", "M01"],
            "Fecha": pd.to_datetime(["2026-03-18", "2026-03-19"]),
            "m3/ha": [10.0, 20.0],
        }
    )

    salida, _ = construir_contexto_oleadas_asof(
        _transiciones().iloc[[1]].assign(
            fecha_emision_actual=pd.Timestamp("2026-03-20")
        ),
        riego=riego,
    )

    assert salida.iloc[0].riego_m3_ha == 30.0
    assert salida.iloc[0].riego_agua_ha == 30.0
