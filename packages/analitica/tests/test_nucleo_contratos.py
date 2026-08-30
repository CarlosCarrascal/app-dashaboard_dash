import os
import subprocess
import sys
from dataclasses import fields
from pathlib import Path

from analitica.dominio.nucleo import Hallazgo as HallazgoDesdeLaFachada
from analitica.dominio.nucleo import Panel as PanelDesdeLaFachada
from analitica.dominio.nucleo.contratos import Hallazgo
from analitica.dominio.nucleo.contratos import Panel as PanelDesdeContratos
from analitica.dominio.nucleo.datos import Hallazgo as HallazgoDesdeDatos
from analitica.dominio.nucleo.datos import Panel
from analitica.dominio.nucleo.floracion import _hallazgo as hallazgo_de_floracion
from analitica.dominio.nucleo.poda import _hallazgo as hallazgo_de_poda


def test_hallazgo_conserva_el_contrato_publico_del_nucleo():
    hallazgo = Hallazgo("clave", "Título", "media", "detalle", "efecto")

    assert HallazgoDesdeDatos is Hallazgo
    assert HallazgoDesdeLaFachada is Hallazgo
    assert Panel is PanelDesdeContratos
    assert PanelDesdeLaFachada is Panel
    assert [campo.name for campo in fields(Hallazgo)] == [
        "clave",
        "titulo",
        "gravedad",
        "detalle",
        "efecto",
    ]
    assert Panel.__module__ == "analitica.dominio.nucleo.datos"
    assert hallazgo.clave == "clave"
    assert hallazgo.gravedad == "media"


def test_contratos_no_importa_transformaciones_del_nucleo():
    import sys

    modulo = sys.modules["analitica.dominio.nucleo.contratos"]

    assert "analitica.dominio.nucleo.datos" not in modulo.__dict__
    assert "analitica.dominio.nucleo.floracion" not in modulo.__dict__
    assert "analitica.dominio.nucleo.poda" not in modulo.__dict__


def test_datos_no_carga_floracion_ni_poda_al_importarse():
    raiz_paquetes = Path(__file__).resolve().parents[2]
    entorno = os.environ.copy()
    entorno["PYTHONPATH"] = str(raiz_paquetes)
    entorno["PYTHONDONTWRITEBYTECODE"] = "1"
    codigo = (
        "import sys; import analitica.dominio.nucleo.datos; "
        "print('analitica.dominio.nucleo.floracion' in sys.modules, "
        "'analitica.dominio.nucleo.poda' in sys.modules)"
    )
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        check=True,
        capture_output=True,
        text=True,
        env=entorno,
    )

    assert resultado.stdout.strip() == "False False"


def test_las_integraciones_de_floracion_y_poda_producen_el_mismo_contrato():
    argumentos = ("clave", "Título", "baja", "detalle", "efecto")

    assert hallazgo_de_floracion(*argumentos) == Hallazgo(*argumentos)
    assert hallazgo_de_poda(*argumentos) == Hallazgo(*argumentos)
