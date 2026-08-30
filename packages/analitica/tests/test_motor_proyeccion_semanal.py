from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

from analitica.proyeccion.motor_proyeccion_semanal import (
    LoteParametrosProyeccion,
    ajustar_dia_habil,
    extraer_fechas_pasadas,
    norm_cdf,
    proyectar_lote_pasadas,
    semana_iso_21,
)
from analitica.proyeccion.operativo import (
    construir_modelo_operativo_excel,
    seleccionar_libros_operativos,
    validar_libro_operativo,
)


def test_extraer_fechas_pasadas_detecta_calendario_completo():
    fila = pd.Series(
        {
            "FePas1": date(2026, 8, 15),
            "FePas2": date(2026, 8, 25),
            "FePas3": date(2026, 9, 5),
            "FePas6": date(2026, 10, 5),
        }
    )
    with pytest.raises(ValueError, match="índices incompletos"):
        extraer_fechas_pasadas(fila)

    fila["FePas4"] = date(2026, 9, 15)
    fila["FePas5"] = date(2026, 9, 25)
    assert len(extraer_fechas_pasadas(fila)) == 6


def test_extraer_fechas_pasadas_rechaza_vacias_repetidas_y_desordenadas():
    with pytest.raises(ValueError, match="vacío"):
        extraer_fechas_pasadas(pd.Series({"FePas1": date(2026, 8, 15), "FePas2": None}))
    with pytest.raises(ValueError, match="repetirse"):
        extraer_fechas_pasadas(
            pd.Series({"FePas1": date(2026, 8, 15), "FePas2": date(2026, 8, 15)})
        )
    with pytest.raises(ValueError, match="creciente"):
        extraer_fechas_pasadas(
            pd.Series({"FePas1": date(2026, 8, 25), "FePas2": date(2026, 8, 15)})
        )


def test_norm_cdf_precisa():
    assert norm_cdf(0.0, 0.0, 1.0) == pytest.approx(0.5, abs=1e-7)
    assert norm_cdf(1.96, 0.0, 1.0) == pytest.approx(0.9750021, abs=1e-5)
    assert norm_cdf(200.0, 200.0, 25.0) == pytest.approx(0.5, abs=1e-7)


def test_semana_iso_21_calendario():
    # 2026-08-10 is Monday of Week 33
    d1 = date(2026, 8, 10)
    assert semana_iso_21(d1) == 33

    # 2026-08-03 is Monday of Week 32
    d2 = date(2026, 8, 3)
    assert semana_iso_21(d2) == 32


def test_ajuste_dia_habil():
    # 2026-08-08 is Saturday (weekday 5) -> should adjust to Monday 2026-08-10 (+2)
    sat = date(2026, 8, 8)
    assert ajustar_dia_habil(sat) == date(2026, 8, 10)

    # 2026-08-09 is Sunday (weekday 6) -> should adjust to Monday 2026-08-10 (+1)
    sun = date(2026, 8, 9)
    assert ajustar_dia_habil(sun) == date(2026, 8, 10)

    # 2026-08-10 is Monday -> should remain Monday
    mon = date(2026, 8, 10)
    assert ajustar_dia_habil(mon) == date(2026, 8, 10)


def test_proyeccion_lote_individual_identidad_matematica():
    # Parámetros exactos de L039 en Arena.xlsm
    lp = LoteParametrosProyeccion(
        fundo="Aqu Anqa - ArenaAzul",
        fundo_ppto="Aqu Anqa",
        modulo="M01",
        turno="T01",
        lote="L039",
        area_ha=1.37,
        n_plantas=6112.0,
        fecha_poda=date(2026, 1, 21),
        x1=202.20375917143667,
        o1=20.22037591714367,
        n1=463.0439999999999,
        x2=268.7037591714367,
        o2=26.87037591714367,
        n2=232.95,
        x3=366.7037591714367,
        o3=25.66926314200057,
        n3=69.88499999999999,
        a1=4.5,
        b1=-0.00138729414819607,
        a2=4.3,
        b2=-0.0013672941481960698,
        a3=4.7,
        b3=-0.0013672941481960698,
    )

    fechas_pasadas = [
        date(2026, 8, 13),
        date(2026, 8, 23),
        date(2026, 9, 2),
        date(2026, 9, 14),
        date(2026, 9, 24),
    ]

    regs = proyectar_lote_pasadas(
        params=lp,
        pana_inicial=2.0,
        fecha_inicio_primera_pana=date(2026, 8, 3),
        fechas_cosecha_pasadas=fechas_pasadas,
        factor_caida=0.9,
        campana="C2026",
        fundo_q="Aqu Anqa 1",
    )

    assert len(regs) == 5

    # Check first paña matches Excel BDProy exactly
    # Excel: Frtutos=81.5083, Peso=3.3889, Rend=1232.33, Kg=1688.30
    p1 = regs[0]
    assert p1.pana == 2.0
    assert p1.fecha_cos == date(2026, 8, 13)
    assert p1.semana == 33
    assert p1.frutos_planta == pytest.approx(81.50833, rel=1e-4)
    assert p1.peso_promedio_g == pytest.approx(3.388936, rel=1e-4)
    assert p1.kg == pytest.approx(1688.297, rel=1e-4)
    assert p1.rendimiento_kg_ha == pytest.approx(1232.333, rel=1e-4)

    # Verify mathematical identity Kg = Frutos * Peso * Plantas / 1000
    for r in regs:
        calc_kg = (r.frutos_planta * r.peso_promedio_g * lp.n_plantas) / 1000.0
        assert r.kg == pytest.approx(calc_kg, rel=1e-7)
        assert r.rendimiento_kg_ha == pytest.approx(r.kg / lp.area_ha, rel=1e-7)
        assert r.frutos_total == pytest.approx(r.frutos_planta * lp.n_plantas, rel=1e-7)


def test_validacion_fidedigna_contra_archivos_excel_semana_33():
    """Valida la concordancia con los libros Excel de la semana 33."""
    folder = r"C:\Users\CCARRASCAL\Downloads\Proyecciones\ProyeccionSemanal_33"

    try:
        __import__("python_calamine")
    except ImportError:
        pytest.skip("python-calamine no disponible en entorno de test")

    archivos = [
        ("ProySemanal_33_Arena.xlsm", "Arena"),
        ("ProySemanal_33_Ayllu.xlsm", "Ayllu"),
        ("ProySemanal_33_Kawsay Allpa.xlsm", "Kawsay"),
        ("ProySemanal_33_Quri.xlsm", "Quri"),
    ]

    for filename, fundo_nom in archivos:
        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            continue

        resultado = validar_libro_operativo(path, fundo_nombre=fundo_nom)
        assert resultado.filas_motor > 0, f"{filename}: el motor no produjo filas"

        # Los cuatro libros disponibles tienen FePas1..FePas6 en Panel, pero BDProy
        # conserva salidas de cinco pasadas o de otra emisión. La validación debe
        # bloquear esa comparación y dejar evidencia, no convertirla en paridad.
        filas_esperadas = {
            "Arena": 510,
            "Ayllu": 1278,
            "Kawsay": 1974,
            "Quri": 1140,
        }[fundo_nom]
        assert resultado.filas_motor == filas_esperadas
        assert resultado.estado == "fuente_inconsistente", (
            f"{filename}: se esperaba bloquear la fuente, pero quedó "
            f"{resultado.estado}; {resultado.advertencias}"
        )
        assert resultado.advertencias


def test_el_motor_no_trunca_ayllu_a_cinco_pasadas():
    folder = r"C:\Users\CCARRASCAL\Downloads\Proyecciones\ProyeccionSemanal_33"
    path = os.path.join(folder, "ProySemanal_33_Ayllu.xlsm")
    if not os.path.exists(path):
        pytest.skip("libro operativo Ayllu no disponible")
    resultado = validar_libro_operativo(path, fundo_nombre="Ayllu")
    assert resultado.filas_motor == 1278


def test_adaptador_operativo_construye_los_cuatro_libros_y_conserva_formula():
    root = r"C:\Users\CCARRASCAL\Downloads\Proyecciones\ProyeccionSemanal_33"
    if not os.path.isdir(root):
        pytest.skip("libros operativos no disponibles")
    predicciones, fuente, detalles = construir_modelo_operativo_excel(
        root,
        campania="C2026",
        fecha_emision="2026-08-10",
    )
    assert len(predicciones) == 4902
    assert predicciones.modelo.eq("ModeloOperativoActual_v1").all()
    assert "lote_id" not in predicciones  # se resuelve al persistir contra dim.lote
    assert predicciones.p10_kg.isna().all()
    assert predicciones.p90_kg.isna().all()
    assert predicciones.p50_kg.ge(0).all()
    assert fuente.nombre == "excel"
    assert len(detalles["manifest"]) == 4


def test_selector_semanal_acepta_espaciado_de_kawsay_y_elige_cuatro_bases(tmp_path):
    for nombre in (
        "ProySemanal_34_Arena.xlsm",
        "ProySemanal_34_Ayllu.xlsm",
        "ProySemanal_34 _Kawsay Allpa.xlsm",
        "ProySemanal_34_Quri.xlsm",
        "ProySemanal_34_Arena_v2.xlsm",
    ):
        (tmp_path / nombre).touch()
    seleccion = seleccionar_libros_operativos(tmp_path, "ProySemanal_34")
    assert len(seleccion) == 4
    assert ("ProySemanal_34_Arena_v2.xlsm", "Arena") not in seleccion
    assert {fundo for _, fundo in seleccion} == {"Arena", "Ayllu", "Kawsay", "Quri"}


def test_una_variante_solo_entra_si_el_manifiesto_la_promueve(tmp_path):
    for nombre in (
        "ProySemanal_34_Arena.xlsm",
        "ProySemanal_34_Arena_v2.xlsm",
        "ProySemanal_34_Ayllu.xlsm",
        "ProySemanal_34_Kawsay Allpa.xlsm",
        "ProySemanal_34_Quri.xlsm",
    ):
        (tmp_path / nombre).touch()
    seleccion = seleccionar_libros_operativos(
        tmp_path,
        "ProySemanal_34",
        promociones={"Arena": "ProySemanal_34_Arena_v2.xlsm"},
    )
    assert ("ProySemanal_34_Arena_v2.xlsm", "Arena") in seleccion
