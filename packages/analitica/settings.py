"""Rutas de entrada configurables para las aplicaciones analíticas.

Las rutas pueden ser absolutas o relativas a ``AQUANQA_REPO_ROOT``. En local se detecta
automáticamente la raíz del checkout; en un contenedor se declara explícitamente para que
el paquete instalado no dependa de la ubicación de ``site-packages``.
"""

from __future__ import annotations

import os
from pathlib import Path

def _raiz_repositorio() -> Path:
    declarada = os.environ.get("AQUANQA_REPO_ROOT")
    if declarada:
        return Path(declarada).expanduser().resolve()

    archivo = Path(__file__).resolve()
    for padre in (archivo.parent, *archivo.parents):
        if (padre / "package.json").is_file() and (padre / "db" / "sql").is_dir():
            return padre
    return Path.cwd()


_RAIZ_REPOSITORIO = _raiz_repositorio()


def _ruta(clave: str, defecto: Path) -> Path:
    valor = Path(os.environ.get(clave, str(defecto)))
    return valor if valor.is_absolute() else (_RAIZ_REPOSITORIO / valor)

# Copias versionadas de la campaña. Las variables de entorno permiten cambiar el origen
# sin tocar el código ni crear una dependencia de Streamlit o Dash.
XLSX_REPO = _ruta("AQUANQA_XLSX", _RAIZ_REPOSITORIO / "docs" / "data" / "IA.final.xlsx")
PODA_REPO = _ruta("AQUANQA_PODA_XLSX", _RAIZ_REPOSITORIO / "docs" / "data" / "M_Poda.xlsx")

# «DAtos mes.xlsx» trae la hoja EvFlores: conteo real de flores por fundo físico, módulo,
# turno y semana — la primera fase fenológica medida del tablero.
FLORACION_REPO = _ruta(
    "AQUANQA_FLORACION_XLSX",
    _RAIZ_REPOSITORIO / "docs" / "data" / "DAtos mes.xlsx",
)
