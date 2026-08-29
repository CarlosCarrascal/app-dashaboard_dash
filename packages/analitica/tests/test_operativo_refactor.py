from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pandas as pd

from analitica.proyeccion import operativo_excel, validacion_operativa
from analitica.proyeccion.compartido.hashes import sha256_archivo
from analitica.proyeccion.operativo import (
    contratos,
    lectura,
    modelo,
    salida,
    seleccion,
    validacion,
)


def test_las_fachadas_conservan_aliases_y_firmas() -> None:
    assert (
        operativo_excel.construir_modelo_operativo_excel
        is modelo.construir_modelo_operativo_excel
    )
    assert (
        operativo_excel.seleccionar_libros_operativos
        is seleccion.seleccionar_libros_operativos
    )
    assert operativo_excel.datos_proyeccion_operativo is salida.datos_proyeccion_operativo
    assert operativo_excel.leer_libro_operativo is lectura.leer_libro_operativo
    assert operativo_excel.sha256_archivo is sha256_archivo
    assert validacion_operativa.validar_libro_operativo is validacion.validar_libro_operativo
    assert validacion_operativa.validar_libros_semana is validacion.validar_libros_semana
    assert (
        validacion_operativa.ResultadoValidacionOperativa
        is contratos.ResultadoValidacionOperativa
    )
    assert inspect.signature(operativo_excel.construir_modelo_operativo_excel) == inspect.signature(
        modelo.construir_modelo_operativo_excel
    )


def test_la_lectura_opcional_es_lazy_y_no_importa_drivers_en_el_modulo() -> None:
    ruta = Path(lectura.__file__)
    tree = ast.parse(ruta.read_text(encoding="utf-8"))
    imports_superiores = {
        alias.name
        for nodo in tree.body
        if isinstance(nodo, ast.Import)
        for alias in nodo.names
    } | {
        nodo.module
        for nodo in tree.body
        if isinstance(nodo, ast.ImportFrom) and nodo.module
    }
    assert "python_calamine" not in imports_superiores
    assert "pyodbc" not in imports_superiores


def test_validacion_interna_conserva_resultado_y_reporte(monkeypatch) -> None:
    ruta = Path("libro.xlsm")
    fuente = pd.DataFrame(
        [
            {
                "Modulo": "M1",
                "Turno": "T1",
                "Lote": "L1",
                "Paña": 1,
                "Fechaini": "2026-01-01",
                "FeCos": "2026-01-08",
                "Campaña": "C2026",
                "Frtutos": 10.0,
                "Peso": 2.0,
                "Rend": 20.0,
                "Kg": 2.0,
                "Frutototal": 10.0,
            }
        ]
    )
    panel = pd.DataFrame({"FePas1": ["2026-01-01"]})
    motor = fuente.drop(columns="Campaña").copy()

    monkeypatch.setattr(validacion, "sha256_archivo", lambda _: "hash")
    monkeypatch.setattr(
        validacion,
        "leer_libro_operativo",
        lambda _: (pd.DataFrame(), panel, fuente),
    )
    monkeypatch.setattr(
        validacion,
        "ejecutar_proyeccion_semanal_dataframe",
        lambda **_: motor,
    )

    resultado = validacion.validar_libro_operativo(ruta, fundo_nombre="Arena")

    assert resultado.valido
    assert resultado.estado == "validado"
    assert resultado.sha256 == "hash"
    assert resultado.diferencias_filas == 0
    assert resultado.metadatos["campana_fuente"] == "C2026"


def test_selector_y_constantes_historicas_apuntan_a_la_implementacion() -> None:
    assert operativo_excel.LIBROS_OPERATIVOS is seleccion.LIBROS_OPERATIVOS
    assert operativo_excel.FUNDOS_ARCHIVO is seleccion.FUNDOS_ARCHIVO
    assert validacion_operativa.CLAVES_CORRIDA is contratos.CLAVES_CORRIDA
