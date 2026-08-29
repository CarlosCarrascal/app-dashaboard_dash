from __future__ import annotations

import ast
from pathlib import Path

from analitica.servicios import turno_reingreso, turno_reingreso_h1


def _arbol(modulo: object) -> ast.Module:
    ruta = Path(modulo.__file__)  # type: ignore[attr-defined]
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def test_las_rutas_historicas_son_fachadas_y_reexportan_la_implementacion_fisica() -> None:
    for modulo in (turno_reingreso, turno_reingreso_h1):
        arbol = _arbol(modulo)
        assert not [
            nodo
            for nodo in arbol.body
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        assert not [
            nodo
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom)
            and nodo.module
            and nodo.module.startswith("analitica.scripts.")
        ]

    from analitica.servicios import (
        turno_reingreso_configuracion,
        turno_reingreso_contexto,
        turno_reingreso_fuentes,
        turno_reingreso_h1_configuracion,
        turno_reingreso_h1_contexto,
        turno_reingreso_h1_fuentes,
        turno_reingreso_h1_metricas,
        turno_reingreso_h1_reporte,
        turno_reingreso_metricas,
        turno_reingreso_reporte,
    )

    assert turno_reingreso.preparar_macro is turno_reingreso_fuentes.preparar_macro
    assert turno_reingreso.derivar_contexto_asof is turno_reingreso_contexto.derivar_contexto_asof
    assert (
        turno_reingreso.aplicar_configuracion
        is turno_reingreso_configuracion.aplicar_configuracion
    )
    assert (
        turno_reingreso.seleccionar_configuracion
        is turno_reingreso_metricas.seleccionar_configuracion
    )
    assert turno_reingreso.evaluar_panel is turno_reingreso_reporte.evaluar_panel

    assert turno_reingreso_h1.preparar_contrato is turno_reingreso_h1_fuentes.preparar_contrato
    assert (
        turno_reingreso_h1.derivar_turno_reingreso_asof
        is turno_reingreso_h1_contexto.derivar_turno_reingreso_asof
    )
    assert (
        turno_reingreso_h1.demostrar_noop_h1
        is turno_reingreso_h1_configuracion.demostrar_noop_h1
    )
    assert (
        turno_reingreso_h1.auditar_aplicabilidad_h1
        is turno_reingreso_h1_metricas.auditar_aplicabilidad_h1
    )
    assert turno_reingreso_h1.evaluar_panel is turno_reingreso_h1_reporte.evaluar_panel


def test_los_componentes_no_importan_las_fachadas_historicas() -> None:
    modulos = (
        "turno_reingreso_fuentes",
        "turno_reingreso_contexto",
        "turno_reingreso_configuracion",
        "turno_reingreso_metricas",
        "turno_reingreso_reporte",
        "turno_reingreso_h1_fuentes",
        "turno_reingreso_h1_contexto",
        "turno_reingreso_h1_configuracion",
        "turno_reingreso_h1_metricas",
        "turno_reingreso_h1_reporte",
    )
    raiz = Path(turno_reingreso.__file__).parent  # type: ignore[arg-type]
    for nombre in modulos:
        arbol = ast.parse(
            (raiz / f"{nombre}.py").read_text(encoding="utf-8"),
            filename=nombre,
        )
        imports = [
            nodo.module
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom) and nodo.module
        ]
        assert "analitica.servicios.turno_reingreso" not in imports
        assert "analitica.servicios.turno_reingreso_h1" not in imports
