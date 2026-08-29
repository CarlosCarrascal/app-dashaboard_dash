from __future__ import annotations

import ast
import inspect
from pathlib import Path

from analitica.scripts import (
    evaluar_ocurrencia_v3,
    replay_campania_completo,
    screening_lagged_parameters_horizons,
    screening_param_delta_momentum,
    screening_parameter_delta_replay,
    screening_router_horizonte,
    screening_router_parametros_lagged,
)
from analitica.servicios import parametros_replay, replay, router_horizonte

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TARGETS = {
    "replay_campania_completo",
    "evaluar_ocurrencia_v3",
    "screening_parameter_delta_replay",
    "screening_param_delta_momentum",
    "screening_lagged_parameters_horizons",
    "screening_router_parametros_lagged",
    "screening_router_horizonte",
}
SERVICE_FILES = {
    "replay.py",
    "parametros_replay.py",
    "router_horizonte.py",
}


def _imports_de_scripts(ruta: Path) -> list[str]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    encontrados: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            encontrados.extend(
                alias.name
                for alias in nodo.names
                if nodo.module.startswith("analitica.scripts.")
            )
        elif isinstance(nodo, ast.Import):
            encontrados.extend(
                alias.name
                for alias in nodo.names
                if alias.name.startswith("analitica.scripts.")
            )
    return encontrados


def test_la_cadena_no_importa_un_script_desde_otro_script():
    problemas = {
        ruta.name: _imports_de_scripts(ruta)
        for ruta in (SCRIPTS / f"{nombre}.py" for nombre in sorted(TARGETS))
        if _imports_de_scripts(ruta)
    }
    assert not problemas


def test_los_servicios_compartidos_no_dependen_de_scripts():
    problemas = {
        ruta.name: _imports_de_scripts(ruta)
        for ruta in (ROOT / "servicios" / nombre for nombre in SERVICE_FILES)
        if _imports_de_scripts(ruta)
    }
    assert not problemas


def test_replay_conserva_fachadas_y_firmas():
    assert replay_campania_completo.emisiones_completas is replay.emisiones_completas
    assert replay_campania_completo.normalizar_modelo is replay.normalizar_modelo
    assert replay_campania_completo._emisiones_completas is replay.emisiones_completas
    assert replay_campania_completo._normalizar_modelo is replay.normalizar_modelo
    assert inspect.signature(replay_campania_completo.emisiones_completas) == inspect.signature(
        replay.emisiones_completas
    )
    assert inspect.signature(replay_campania_completo.normalizar_modelo) == inspect.signature(
        replay.normalizar_modelo
    )
    assert evaluar_ocurrencia_v3.emisiones_completas is replay.emisiones_completas
    assert evaluar_ocurrencia_v3.normalizar_modelo is replay.normalizar_modelo


def test_parametros_conserva_constantes_y_utilidades_publicas():
    nombres = (
        "ACCESS_DEFAULT",
        "PARAMETROS_CALENDARIO",
        "PARAMETROS_CURVA",
        "ROOT_DEFAULT",
        "TRANSITIONS_DEFAULT",
        "cargar_reales_y_r09",
        "columna_campania",
        "proyectar_emision_detallada",
    )
    for nombre in nombres:
        assert getattr(screening_parameter_delta_replay, nombre) is getattr(
            parametros_replay, nombre
        )
    assert screening_parameter_delta_replay._proyectar_emision_detallada is (
        parametros_replay.proyectar_emision_detallada
    )
    assert screening_param_delta_momentum.ACCESS_DEFAULT is parametros_replay.ACCESS_DEFAULT
    assert screening_param_delta_momentum.proyectar_emision_detallada is (
        parametros_replay.proyectar_emision_detallada
    )
    assert screening_lagged_parameters_horizons.cargar_reales_y_r09 is (
        parametros_replay.cargar_reales_y_r09
    )


def test_router_conserva_fachadas_y_constantes():
    for nombre in ("CIERRES", "RUNS_H1", "RUNS_MULTI", "leer", "agregar"):
        assert getattr(screening_router_horizonte, nombre) is getattr(router_horizonte, nombre)
    assert screening_router_horizonte._leer is router_horizonte.leer
    assert screening_router_horizonte._agregar is router_horizonte.agregar
    assert screening_router_parametros_lagged.leer is router_horizonte.leer
    assert screening_router_parametros_lagged.agregar is router_horizonte.agregar
    assert screening_router_parametros_lagged.ACCESS_DEFAULT is parametros_replay.ACCESS_DEFAULT
    assert inspect.signature(screening_router_horizonte.leer) == inspect.signature(
        router_horizonte.leer
    )
    assert inspect.signature(screening_router_horizonte.agregar) == inspect.signature(
        router_horizonte.agregar
    )
