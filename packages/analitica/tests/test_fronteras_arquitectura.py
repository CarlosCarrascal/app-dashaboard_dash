from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

CAPAS_CANONICAS = (
    "analitica.dominio",
    "analitica.dominio.modelos",
    "analitica.dominio.modelos.fenologico",
    "analitica.dominio.modelos.hibrido",
    "analitica.dominio.modelos.ocurrencia",
    "analitica.dominio.evaluacion",
    "analitica.aplicacion",
    "analitica.aplicacion.procesos",
    "analitica.aplicacion.parametros",
    "analitica.aplicacion.operativo",
    "analitica.infraestructura",
    "analitica.infraestructura.persistencia",
    "analitica.interfaces",
    "analitica.proyeccion.horizonte",
)


def test_las_capas_canonicas_se_pueden_importar():
    for nombre in CAPAS_CANONICAS:
        assert importlib.import_module(nombre).__name__ == nombre


def test_proyeccion_es_un_punto_de_entrada_pequeno_y_estable():
    raiz = Path(__file__).resolve().parents[1] / "proyeccion"
    archivos_raiz = {ruta.name for ruta in raiz.glob("*.py")}
    assert archivos_raiz == {"__init__.py", "pronostico_horizonte.py"}
    assert (raiz / "horizonte").is_dir()

    modulo = importlib.import_module("analitica.proyeccion")
    for nombre in ("proyectar_hibrido_v1", "proyectar_fenologico_v1", "estimar_ocurrencia"):
        assert hasattr(modulo, nombre)


def test_las_familias_de_modelos_no_se_confunden_con_procesos():
    hibrido = importlib.import_module("analitica.dominio.modelos.hibrido")
    fenologico = importlib.import_module("analitica.dominio.modelos.fenologico")
    nowcast = importlib.import_module("analitica.aplicacion.procesos.nowcast")

    assert hibrido.NOMBRE_MODELO
    assert fenologico.NOMBRE_MODELO
    assert hasattr(nowcast, "__file__")
    assert "nowcast" in nowcast.__name__


def test_los_imports_productivos_usan_rutas_canonicas():
    raiz_repo = Path(__file__).resolve().parents[3]
    rutas = []
    for carpeta in (
        "interfaces/commands",
        "aplicacion/servicios",
        "interfaces/scripts",
    ):
        rutas.extend((raiz_repo / "packages" / "analitica" / carpeta).rglob("*.py"))
    for ruta in rutas:
        fuente = ruta.read_text(encoding="utf-8")
        assert "analitica.proyeccion.dominio" not in fuente
        assert "analitica.proyeccion.aplicacion" not in fuente
        assert "analitica.proyeccion.infraestructura" not in fuente
        assert "analitica.proyeccion.interfaces" not in fuente


def test_no_quedan_fachadas_historicas_en_la_raiz_de_proyeccion():
    raiz = Path(__file__).resolve().parents[1] / "proyeccion"
    obsoletos = {
        "candidatos.py",
        "fenologico.py",
        "hibrido.py",
        "modelos.py",
        "ocurrencia.py",
        "persistencia.py",
        "parametros.py",
        "operativo.py",
    }
    assert not obsoletos.intersection(ruta.name for ruta in raiz.glob("*.py"))


def test_el_empaquetado_declara_las_capas_reales():
    raiz_paquete = Path(__file__).resolve().parents[1]
    with (raiz_paquete / "pyproject.toml").open("rb") as archivo:
        proyecto = tomllib.load(archivo)

    paquetes = set(proyecto["tool"]["setuptools"]["packages"])
    esperados = {
        "analitica.dominio",
        "analitica.dominio.modelos",
        "analitica.dominio.evaluacion",
        "analitica.aplicacion",
        "analitica.aplicacion.procesos",
        "analitica.aplicacion.parametros",
        "analitica.aplicacion.operativo",
        "analitica.infraestructura",
        "analitica.infraestructura.persistencia",
        "analitica.interfaces",
    }
    assert esperados <= paquetes
