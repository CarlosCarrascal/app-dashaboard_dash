from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _ejecutar_importacion(codigo: str) -> str:
    raiz = Path(__file__).resolve().parents[2]
    entorno = os.environ.copy()
    entorno["PYTHONPATH"] = str(raiz)
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        check=True,
        capture_output=True,
        text=True,
        env=entorno,
    )
    return resultado.stdout.strip()


def test_fachadas_ligeras_no_arrastran_modelos_al_importar():
    salida = _ejecutar_importacion(
        "import sys; import analitica.dominio.nucleo; "
        "import analitica.cli; import analitica.interfaces.visualizaciones.graficos; "
        "print('xgboost' not in sys.modules and 'sklearn' not in sys.modules "
        "and 'plotly' not in sys.modules)"
    )
    assert salida == "True"
