from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from test_fenologico_v1 import _datos

from analitica.proyeccion.fenologico_v1 import construir_panel_fenologico
from analitica.proyeccion.hibrido_parametros_asof import (
    NOMBRE_MODELO,
    ConfiguracionParametrosAsOf,
    _desplazamiento_gdd_por_fila,
    aprender_desplazamiento,
    construir_snapshot_parametros,
    ejecutar_emision_parametros_asof,
    normalizar_parametros_excel,
    seleccionar_gdd_config,
    seleccionar_peso_macro,
)
from analitica.proyeccion.parametros_excel import seleccionar_libros_parametros


def _emisiones() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campania": ["C2026"] * 3,
            "fecha_emision": pd.to_datetime(["2026-04-06", "2026-05-04", "2026-06-01"]),
        }
    )


def test_parametros_excel_se_leen_por_nombre_y_no_por_posicion():
    tabla = pd.DataFrame(
        [
            {
                "lote_id": 10,
                "N3": 30,
                "X1": 220,
                "A2": 3.2,
                "B1": -0.002,
                "O1": 25,
                "N1": 100,
                "X2": 290,
                "O2": 27,
                "N2": 40,
                "X3": 353,
                "O3": 28,
                "A1": 3.4,
                "A3": 3.0,
                "B2": -0.002,
                "B3": -0.002,
            }
        ]
    )
    salida = normalizar_parametros_excel(tabla, fuente="excel", archivo_fuente="p.xlsx")
    assert salida.loc[0, "parametros_completos"]
    assert salida.loc[0, "X1"] == 220
    assert salida.loc[0, "B3"] == -0.002
    assert salida.loc[0, "fuente_parametros"] == "excel"


def test_peso_macro_no_es_un_cincuenta_cincuenta_fijo():
    historial = pd.DataFrame(
        {
            "banda_horizonte": ["1_2"] * 40,
            "real_kg": np.repeat(1000.0, 40),
            "legacy_kg": np.repeat(1000.0, 40),
            "residual_kg": np.repeat(900.0, 40),
        }
    )
    peso, detalle = seleccionar_peso_macro(historial, "1_2")
    assert peso > 0.75
    assert peso <= 1.0
    assert detalle["metodo"] == "grid_oos_con_shrinkage"


def test_desplazamiento_no_se_aplica_con_pocas_observaciones():
    historial = pd.DataFrame(
        {
            "lote_id": [1, 1, 1],
            "fecha_objetivo": pd.to_datetime(["2026-01-05", "2026-01-12", "2026-01-19"]),
            "real_kg": [100, 110, 120],
            "legacy_kg": [80, 90, 100],
        }
    )
    shift, detalle = aprender_desplazamiento(historial)
    assert shift == 0
    assert detalle["metodo"] == "insuficiente"


def test_gdd_se_admite_solo_si_predice_desplazamiento_oos():
    fechas = pd.date_range("2026-01-04", periods=60, freq="7D")
    legacy = {fecha: 1000.0 + 25.0 * indice for indice, fecha in enumerate(fechas)}
    filas = []
    for indice, fecha in enumerate(fechas):
        desplazamiento = float(np.clip(np.rint((indice - 30) / 7.0) * 7.0, -14, 14))
        fecha_base = fecha - pd.Timedelta(days=desplazamiento)
        filas.append(
            {
                "lote_id": 1,
                "fecha_objetivo": fecha,
                "real_kg": legacy.get(fecha_base, legacy[fecha]),
                "legacy_kg": legacy[fecha],
                "gdd_7_0_7d": float(indice),
            }
        )
    historial = pd.DataFrame(filas)
    base, ventana, detalle = seleccionar_gdd_config(
        historial,
        ConfiguracionParametrosAsOf(gdd_bases=(7.0,), gdd_ventanas=(7,)),
    )
    assert (base, ventana) == (7.0, 7)
    assert detalle["estado"] == "admitido_oos"
    salida = historial.copy()
    shifts = _desplazamiento_gdd_por_fila(
        salida, 0, {**detalle, "gdd_base": base, "gdd_ventana": ventana}
    )
    assert isinstance(shifts, pd.Series)
    assert shifts.abs().max() <= 14


def test_gdd_no_se_aplica_si_no_mejora_el_holdout():
    historial = pd.DataFrame(
        {
            "lote_id": [1] * 30,
            "fecha_objetivo": pd.date_range("2026-01-04", periods=30, freq="7D"),
            "real_kg": [1000.0] * 30,
            "legacy_kg": [1000.0] * 30,
            "gdd_7_0_7d": np.arange(30, dtype=float),
        }
    )
    base, ventana, detalle = seleccionar_gdd_config(
        historial,
        ConfiguracionParametrosAsOf(gdd_bases=(7.0,), gdd_ventanas=(7,)),
    )
    assert base is None and ventana is None
    assert detalle["estado"] in {"sin_mejora_oos", "sin_curva_vecina"}


def test_emision_asof_conserva_identidad_y_no_mira_el_futuro():
    emisiones = _emisiones()
    datos_original = _datos()
    panel_original = construir_panel_fenologico(datos_original, emisiones, horizonte_semanas=3)
    original, _, _ = ejecutar_emision_parametros_asof(
        panel_original,
        datos_original,
        "2026-06-01",
        config=ConfiguracionParametrosAsOf(minimo_entrenamiento=5),
    )
    datos_mutado = _datos()
    datos_mutado.cosecha.loc[
        pd.to_datetime(datos_mutado.cosecha.fecha) > pd.Timestamp("2026-06-01"), "kg"
    ] *= 100
    panel_mutado = construir_panel_fenologico(datos_mutado, emisiones, horizonte_semanas=3)
    mutado, _, _ = ejecutar_emision_parametros_asof(
        panel_mutado,
        datos_mutado,
        "2026-06-01",
        config=ConfiguracionParametrosAsOf(minimo_entrenamiento=5),
    )
    columnas = ["lote_id", "fecha_objetivo", "frutos_por_planta", "peso_baya_g", "p50_kg"]
    assert_frame_equal(
        original.sort_values(columnas[:2])[columnas].reset_index(drop=True),
        mutado.sort_values(columnas[:2])[columnas].reset_index(drop=True),
        check_dtype=False,
    )
    esperado = original.plantas * original.frutos_por_planta * original.peso_baya_g / 1000
    np.testing.assert_allclose(original.p50_kg, esperado, rtol=1e-8, atol=1e-8)
    assert set(original.modelo) == {NOMBRE_MODELO}
    assert original.componentes.map(lambda x: x["etiqueta_causal"] is False).all()


def test_snapshot_de_parametros_expone_corte_y_nivel():
    pred = pd.DataFrame(
        [
            {
                "campania": "C2026",
                "fecha_emision": pd.Timestamp("2026-06-01"),
                "lote_id": 1,
                "fundo": "Arena",
                "modulo": "M01",
                "legacy_fuente_parametros": "postgres_auto_asof",
                "legacy_n_observaciones": 5,
                "parametros_legacy": {"X1": 220},
                "correccion_frutos_factor": 1.1,
                "correccion_peso_factor": 0.98,
                "desplazamiento_dias": 7,
                "peso_macro": 0.75,
                "gdd_base": 7.0,
                "gdd_ventana": 21,
            }
        ]
    )
    snapshot = construir_snapshot_parametros(pred)
    assert len(snapshot) == 1
    assert snapshot.loc[0, "fecha_corte"] == pd.Timestamp("2026-06-01")
    assert snapshot.loc[0, "n_observaciones_asof"] == 5
    assert snapshot.loc[0, "correcciones_json"]["peso_macro"] == 0.75


def test_selector_excel_no_mezcla_variantes_y_expone_faltantes(tmp_path):
    carpeta = tmp_path / "ProyeccionSemanal_35"
    carpeta.mkdir()
    (carpeta / "ProySemanal_35_Arena.xlsm").write_bytes(b"base")
    (carpeta / "ProySemanal_35_Arena_v2.xlsm").write_bytes(b"variante")
    (carpeta / "ProySemanal_35_Ayllu.xlsm").write_bytes(b"base")
    (carpeta / "ProySemanal_35_Kawsayoli.xlsm").write_bytes(b"variante")

    manifest, faltantes = seleccionar_libros_parametros(tmp_path, semanas=[35])

    assert set(manifest.fundo_operativo) == {"Arena", "Ayllu"}
    assert len(manifest) == 2
    assert set(faltantes.fundo) == {"Kawsay", "Quri"}
    assert not manifest.archivo_fuente.str.contains("v2", case=False).any()
