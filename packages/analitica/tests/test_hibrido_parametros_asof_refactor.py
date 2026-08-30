from __future__ import annotations

import ast
import importlib
from pathlib import Path


def test_el_paquete_reexporta_las_implementaciones_fisicas():
    modulos = {
        "normalizacion": ("normalizar_parametros_excel",),
        "seleccion": ("seleccionar_peso_macro",),
        "desplazamientos": ("aprender_desplazamiento", "seleccionar_gdd_config"),
        "mezcla": ("_interpolar_componentes", "_mezclar_componentes"),
        "ejecucion": ("ejecutar_emision_parametros_asof", "backtest_hibrido_parametros_asof"),
        "snapshots": ("construir_snapshot_parametros",),
    }

    for nombre, funciones in modulos.items():
        modulo = importlib.import_module(f"analitica.proyeccion.parametros.{nombre}")
        for funcion in funciones:
            modulo_implementacion = (
                "analitica.proyeccion.parametros.mezcla"
                if nombre == "seleccion"
                else modulo.__name__
            )
            assert getattr(modulo, funcion).__module__ == modulo_implementacion

    contratos = importlib.import_module("analitica.proyeccion.parametros.contratos")
    parametros = importlib.import_module("analitica.proyeccion.parametros")
    assert parametros.ConfiguracionParametrosAsOf is contratos.ConfiguracionParametrosAsOf


def test_los_modulos_internos_no_importan_la_fachada_historica():
    raiz = Path(__file__).resolve().parents[1] / "proyeccion" / "parametros"
    for ruta in raiz.glob("*.py"):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        imports = [
            nodo.module
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom) and nodo.module is not None
        ]
        imports.extend(
            alias.name
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Import)
            for alias in nodo.names
        )
        assert "analitica.proyeccion.hibrido_parametros_asof" not in imports
        assert "hibrido_parametros_asof" not in imports


def test_ejecucion_depende_de_las_implementaciones_internas_y_no_de_la_fachada_legacy():
    ejecucion = importlib.import_module("analitica.proyeccion.parametros.ejecucion")
    priors = importlib.import_module("analitica.proyeccion.hibrido.priors")
    replay = importlib.import_module("analitica.proyeccion.hibrido.replay")
    servicio = importlib.import_module("analitica.proyeccion.hibrido.servicio")

    assert ejecucion._campania_defecto is priors._campania_defecto
    assert ejecucion._normalizar_emisiones is priors._normalizar_emisiones
    assert ejecucion._panel_corte_replay is replay.panel_corte_replay
    assert ejecucion._panel_replay_cache is replay.panel_replay_cache
    assert ejecucion._legacy_panel is servicio._legacy_panel
    assert ejecucion.proyectar_hibrido_v1 is servicio.proyectar_hibrido_v1
    assert ejecucion.proyectar_macro_legacy_v1 is servicio.proyectar_macro_legacy_v1

    fuente = Path(ejecucion.__file__).read_text(encoding="utf-8")
    assert "hibrido_legacy" not in fuente
