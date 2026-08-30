from __future__ import annotations

import ast
import importlib
import tomllib
from pathlib import Path

import pytest

FRONTERAS_NUEVAS = (
    "analitica.proyeccion.fenologico.incertidumbre",
    "analitica.proyeccion.fenologico.servicio",
    "analitica.proyeccion.hibrido.servicio",
    "analitica.proyeccion.persistencia.mlflow",
    "analitica.proyeccion.compartido.fechas",
    "analitica.proyeccion.compartido.normalizacion",
    "analitica.proyeccion.compartido.serializacion",
    "analitica.proyeccion.operativo",
    "analitica.proyeccion.relaciones_partes",
    "analitica.proyeccion.relaciones_partes.panel",
    "analitica.proyeccion.relaciones_partes.estadistica",
    "analitica.proyeccion.relaciones_partes.packing",
    "analitica.proyeccion.relaciones_partes.evidencia",
)


@pytest.mark.parametrize("nombre_modulo", FRONTERAS_NUEVAS)
def test_fronteras_nuevas_se_pueden_importar(nombre_modulo: str):
    modulo = importlib.import_module(nombre_modulo)

    assert modulo.__name__ == nombre_modulo


def test_los_aliases_conservan_identidad_de_la_implementacion_unica():
    from analitica.proyeccion import (
        candidate_residual_asof,
        candidate_turno_temporal,
        fenologico_v1,
        hibrido_legacy,
        infraestructura,
        relaciones,
        temporal,
        tracking,
    )
    from analitica.proyeccion.candidatos import fuentes, preflight, snapshot
    from analitica.proyeccion.compartido import fechas, normalizacion
    from analitica.proyeccion.compartido import serializacion as serializacion_comun
    from analitica.proyeccion.fenologico import ajuste, incertidumbre, metricas
    from analitica.proyeccion.fenologico import servicio as servicio_fenologico
    from analitica.proyeccion.hibrido import replay
    from analitica.proyeccion.hibrido import servicio as servicio_hibrido
    from analitica.proyeccion.persistencia import mlflow
    from analitica.proyeccion.relaciones_partes import estadistica, evidencia, packing
    from analitica.proyeccion.relaciones_partes import panel as panel_relaciones

    modelos = importlib.import_module("analitica.proyeccion.fenologico.modelos")
    assert modelos.ajustar_regresor is ajuste.ajustar_regresor
    assert incertidumbre.sensibilidades is metricas.sensibilidades
    assert servicio_fenologico.proyectar_fenologico_v1 is fenologico_v1.proyectar_fenologico_v1
    assert servicio_hibrido.proyectar_hibrido_v1 is hibrido_legacy.proyectar_hibrido_v1
    assert servicio_hibrido.backtest_hibrido_v1 is replay.backtest_hibrido_v1
    assert mlflow.tracking_mlflow is tracking.tracking_mlflow
    assert fechas.lunes_semana is temporal.lunes_semana
    assert fechas.ultimo_disponible is temporal.ultimo_disponible
    assert normalizacion.normalizar_panel is candidate_residual_asof.normalizar_panel
    assert (
        normalizacion.normalizar_forecast_candidate
        is candidate_turno_temporal.normalizar_forecast_candidate
    )
    assert serializacion_comun.serializar_json is infraestructura.serializar_json
    assert serializacion_comun.serializar_jsonb is infraestructura.serializar_jsonb
    assert snapshot.cargar_o_construir_snapshot_datos is (
        importlib.import_module("analitica.proyeccion.candidatos.snapshot")
        .cargar_o_construir_snapshot_datos
    )
    assert fuentes.cargar_baselines_por_run is (
        importlib.import_module("analitica.proyeccion.candidatos.fuentes")
        .cargar_baselines_por_run
    )
    assert preflight.evaluar_preflight is (
        importlib.import_module("analitica.proyeccion.candidatos.preflight").evaluar_preflight
    )
    assert panel_relaciones.construir_panel_relaciones is relaciones.construir_panel_relaciones
    assert estadistica.evaluar_relaciones is relaciones.evaluar_relaciones
    assert packing.relaciones_packing is relaciones.relaciones_packing
    assert evidencia.generar_claims is relaciones.generar_claims


def test_relaciones_partes_son_implementaciones_fisicas_y_no_importan_la_fachada():
    from analitica.proyeccion import relaciones
    from analitica.proyeccion.relaciones_partes import estadistica, evidencia, packing
    from analitica.proyeccion.relaciones_partes import panel as panel_relaciones

    assert relaciones.construir_panel_relaciones.__module__ == panel_relaciones.__name__
    assert relaciones.evaluar_relaciones.__module__ == estadistica.__name__
    assert relaciones.relaciones_packing.__module__ == packing.__name__
    assert relaciones.generar_claims.__module__ == evidencia.__name__
    assert relaciones.Hipotesis is estadistica.Hipotesis
    assert relaciones.HIPOTESIS is estadistica.HIPOTESIS

    raiz_partes = Path(__file__).resolve().parents[1] / "proyeccion" / "relaciones_partes"
    for nombre in ("panel.py", "estadistica.py", "packing.py", "evidencia.py"):
        fuente = (raiz_partes / nombre).read_text(encoding="utf-8")
        assert "from ..relaciones" not in fuente
        assert "import relaciones" not in fuente


def test_compartido_es_capa_inferior_y_mlflow_vive_en_persistencia():
    raiz = Path(__file__).resolve().parents[1] / "proyeccion"
    compartido = raiz / "compartido"
    prohibidos = ("..candidate", "..infraestructura", "..temporal", "..tracking")

    for ruta in compartido.glob("*.py"):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.ImportFrom):
                continue
            modulo = "." * nodo.level + (nodo.module or "")
            assert not modulo.startswith(prohibidos), (
                f"{ruta.name} invierte la dependencia: {modulo}"
            )

    arbol_mlflow = ast.parse(
        (raiz / "persistencia" / "mlflow.py").read_text(encoding="utf-8"),
        filename="persistencia/mlflow.py",
    )
    imports_mlflow = [
        "." * nodo.level + (nodo.module or "")
        for nodo in ast.walk(arbol_mlflow)
        if isinstance(nodo, ast.ImportFrom)
    ]
    assert "..tracking" not in imports_mlflow
    assert (raiz / "tracking.py").read_text(encoding="utf-8").count("persistencia.mlflow") == 1


def test_las_capas_nuevas_no_reintroducen_fachadas_legacy_internas():
    raiz = Path(__file__).resolve().parents[1] / "proyeccion"

    archivos_sin_serializacion_infraestructura = (
        raiz / "persistencia" / "conexiones_snapshots.py",
        raiz / "persistencia" / "artefactos.py",
        raiz / "persistencia" / "escenarios_decisiones.py",
        raiz / "persistencia" / "metricas_claims.py",
        raiz / "persistencia" / "runs_predicciones.py",
    )
    for ruta in archivos_sin_serializacion_infraestructura:
        fuente = ruta.read_text(encoding="utf-8")
        assert "infraestructura.serializacion" not in fuente

    for ruta in (
        raiz / "relaciones_partes" / "panel.py",
        raiz / "relaciones_partes" / "packing.py",
    ):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        imports = [
            nodo
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom) and nodo.module == "asof"
        ]
        assert not imports, f"{ruta.name} depende de la fachada asof para fechas"

    panel_fenologico = ast.parse(
        (raiz / "fenologico" / "panel.py").read_text(encoding="utf-8"),
        filename="fenologico/panel.py",
    )
    for nodo in ast.walk(panel_fenologico):
        if not isinstance(nodo, ast.ImportFrom) or nodo.module != "asof":
            continue
        nombres = {alias.name for alias in nodo.names}
        assert not {"lunes_semana", "ultimo_disponible"} & nombres

    replay = (raiz / "hibrido" / "replay.py").read_text(encoding="utf-8")
    assert "fenologico_v1" not in replay


def test_codigo_productivo_importa_implementaciones_canónicas_y_no_fachadas():
    fachadas = {
        "candidate_param_delta",
        "candidate_preflight",
        "candidate_turno_temporal",
        "fenologico_v1",
        "gobernanza",
        "hibrido_legacy",
        "hibrido_parametros_asof",
        "macro_legacy",
        "operativo_excel",
        "pronostico_horizonte",
        "temporal",
        "tracking",
        "validacion_operativa",
    }
    raiz_repo = Path(__file__).resolve().parents[3]
    rutas = []
    for carpeta in ("commands", "servicios", "scripts"):
        rutas.extend((raiz_repo / "packages" / "analitica" / carpeta).rglob("*.py"))
    for carpeta in ("legacy", "servicios"):
        rutas.extend((raiz_repo / "apps" / "dashboard" / carpeta).rglob("*.py"))
    for ruta in rutas:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        imports = [
            nodo.module.split(".")[-1]
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom)
            and nodo.module
            and nodo.module.startswith("analitica.proyeccion.")
        ]
        assert not fachadas.intersection(imports), f"{ruta} importa una fachada histórica"


def test_el_empaquetado_declara_las_fronteras_nuevas():
    raiz_paquete = Path(__file__).resolve().parents[1]
    with (raiz_paquete / "pyproject.toml").open("rb") as archivo:
        proyecto = tomllib.load(archivo)

    paquetes = set(proyecto["tool"]["setuptools"]["packages"])
    mapeos = proyecto["tool"]["setuptools"]["package-dir"]

    esperados = {
        "analitica.proyeccion.operativo": "proyeccion/operativo",
        "analitica.proyeccion.relaciones_partes": "proyeccion/relaciones_partes",
    }
    assert esperados.items() <= mapeos.items()
    assert set(esperados) <= paquetes

    for ruta_relativa in esperados.values():
        assert (raiz_paquete / ruta_relativa / "__init__.py").is_file()
