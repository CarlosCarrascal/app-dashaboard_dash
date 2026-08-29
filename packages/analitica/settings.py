"""Rutas de entrada configurables para las aplicaciones analíticas.

Las rutas pueden ser absolutas o relativas a ``AQUANQA_REPO_ROOT``. En local se detecta
automáticamente la raíz del checkout; en un contenedor se declara explícitamente para que
el paquete instalado no dependa de la ubicación de ``site-packages``.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


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
load_dotenv(_RAIZ_REPOSITORIO / ".env")
load_dotenv(_RAIZ_REPOSITORIO / ".env.local", override=True)


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

# La proyección usa PostgreSQL como contrato principal. `auto` solo existe para desarrollo:
# nunca debe ocultar un fallback, por eso la fuente efectiva viaja en DatasetSnapshot.
ANALYTICS_SOURCE = os.environ.get("AQUANQA_ANALYTICS_SOURCE", "auto").lower()
ANALYTICS_DATABASE_URL = os.environ.get("ANALYTICS_DATABASE_URL")
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI")
MLFLOW_ARTIFACT_ROOT = _ruta(
    "MLFLOW_ARTIFACT_ROOT", _RAIZ_REPOSITORIO / "data" / "salida" / "mlflow"
)
ANALYTICS_EXPORT_DIR = _ruta(
    "AQUANQA_ANALYTICS_EXPORT_DIR", _RAIZ_REPOSITORIO / "data" / "salida" / "analytics"
)


def postgres_dsn() -> str | None:
    """DSN del motor analítico sin imprimir ni registrar secretos."""
    if ANALYTICS_DATABASE_URL:
        return ANALYTICS_DATABASE_URL
    if os.environ.get("PGPASSWORD"):
        usuario = os.environ.get("PGUSER", "postgres")
        host = os.environ.get("PGHOST", "localhost")
        puerto = os.environ.get("PGPORT", "5432")
        base = os.environ.get("PGDATABASE", "aquanqa")
        clave = os.environ["PGPASSWORD"]
        return (
            f"postgresql://{quote_plus(usuario)}:{quote_plus(clave)}@"
            f"{host}:{puerto}/{quote_plus(base)}"
        )
    return None
