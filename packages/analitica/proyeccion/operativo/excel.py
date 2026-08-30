"""Caso operativo basado en libros ProySemanal.

Reúne contratos, lectura, normalización, selección y contenedores de salida
del flujo Excel. El modelo y la validación más grandes permanecen separados
porque tienen reglas de negocio propias.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..compartido import sha256_archivo
from ..contratos import DatosProyeccion, FuenteInfo

MODELO_OPERATIVO_ACTUAL = "ModeloOperativoActual_v1"
CLAVES_CORRIDA = ["Modulo", "Turno", "Lote", "Paña", "Fechaini", "FeCos"]
CAMPOS_NUMERICOS = ["Frtutos", "Peso", "Rend", "Kg", "Frutototal"]


@dataclass
class ResultadoValidacionOperativa:
    """Resultado serializable de la comparación entre libro, Panel y BDProy."""

    archivo: str
    sha256: str
    modelo: str = MODELO_OPERATIVO_ACTUAL
    estado: str = "no_evaluable"
    filas_fuente: int = 0
    filas_motor: int = 0
    max_diferencia: dict[str, float] = field(default_factory=dict)
    diferencias_filas: int = 0
    advertencias: list[str] = field(default_factory=list)
    metadatos: dict[str, Any] = field(default_factory=dict)

    @property
    def valido(self) -> bool:
        return self.estado == "validado"


def leer_libro_operativo(ruta: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Lee las tres hojas necesarias sin abrir Excel ni modificar el libro."""
    try:
        from python_calamine import CalamineWorkbook
    except ImportError as exc:  # pragma: no cover - depende del entorno de ejecución
        raise RuntimeError("python-calamine es necesario para validar libros xlsm") from exc

    workbook = CalamineWorkbook.from_path(str(ruta))
    parametros = workbook.get_sheet_by_name("Parametros").to_python()
    panel = workbook.get_sheet_by_name("Panel").to_python()
    bdproy = workbook.get_sheet_by_name("BDProy").to_python()

    return (
        pd.DataFrame(parametros[1:], columns=parametros[0]),
        pd.DataFrame(panel[2:], columns=panel[1]),
        pd.DataFrame(bdproy[1:], columns=bdproy[0]),
    )


def _fecha(valor: object) -> pd.Timestamp:
    fecha = pd.to_datetime(valor, errors="coerce")
    if pd.isna(fecha):
        raise ValueError(f"Fecha de emisión inválida: {valor!r}")
    return pd.Timestamp(fecha).normalize()


def _normalizar_claves(tabla: pd.DataFrame) -> pd.DataFrame:
    salida = tabla.copy()
    for columna in ("Paña", "ReiRe"):
        if columna in salida:
            salida[columna] = pd.to_numeric(salida[columna], errors="coerce").round(8)
    for columna in ("Fechaini", "FeCos"):
        if columna in salida:
            salida[columna] = pd.to_datetime(salida[columna], errors="coerce").dt.date
    return salida


def _campana_unica(tabla: pd.DataFrame) -> str | None:
    valores = tabla.get("Campaña", pd.Series(dtype=object)).dropna().astype(str).str.strip()
    valores = valores[valores.ne("")].unique().tolist()
    return valores[0] if len(valores) == 1 else None


def _firma_manifest(manifest: list[dict[str, object]]) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def datos_proyeccion_operativo(fuente: FuenteInfo) -> DatosProyeccion:
    """Crea el contenedor mínimo requerido por el repositorio y exportador."""
    return DatosProyeccion(
        fuente=fuente,
        forecast=pd.DataFrame(),
        cosecha=pd.DataFrame(),
    )


LIBROS_OPERATIVOS = (
    ("ProySemanal_33_Arena.xlsm", "Arena"),
    ("ProySemanal_33_Ayllu.xlsm", "Ayllu"),
    ("ProySemanal_33_Kawsay Allpa.xlsm", "Kawsay"),
    ("ProySemanal_33_Quri.xlsm", "Quri"),
)

FUNDOS_ARCHIVO = {
    "Arena": ("arena",),
    "Ayllu": ("ayllu",),
    "Kawsay": ("kawsay",),
    "Quri": ("quri", "qury"),
}
VARIANTES_NO_PROMOVIDAS = ("edi", "v2", "v3", "oli", "copia", "copy")


def seleccionar_libros_operativos(
    root: str | Path,
    version_fuente: str,
    promociones: dict[str, str] | None = None,
) -> tuple[tuple[str, str], ...]:
    """Elige exactamente un libro base por fundo sin sumar variantes silenciosamente."""
    raiz = Path(root).expanduser().resolve()
    numero = re.search(r"(\d+)", str(version_fuente))
    if numero is None:
        raise ValueError(f"La versión no contiene semana: {version_fuente!r}")
    patron_version = re.compile(rf"^proysemanal[ _-]*0*{int(numero.group(1))}(?:\D|$)", re.I)
    promociones = promociones or {}
    seleccion: list[tuple[str, str]] = []

    for fundo, aliases in FUNDOS_ARCHIVO.items():
        promovido = promociones.get(fundo)
        if promovido:
            ruta = raiz / promovido
            if not ruta.is_file():
                raise FileNotFoundError(f"La variante promovida no existe: {ruta}")
            seleccion.append((ruta.name, fundo))
            continue

        candidatos = []
        for ruta in raiz.glob("*.xlsm"):
            nombre = " ".join(ruta.stem.casefold().replace("_", " ").split())
            if not patron_version.match(ruta.stem):
                continue
            if not any(alias in nombre for alias in aliases):
                continue
            if any(
                re.search(rf"(?:^|[ _-]){re.escape(variante)}(?:$|[ _-])", ruta.stem, re.I)
                for variante in VARIANTES_NO_PROMOVIDAS
            ):
                continue
            candidatos.append(ruta)
        if len(candidatos) != 1:
            encontrados = ", ".join(r.name for r in candidatos) or "ninguno"
            raise ValueError(
                f"Se esperaba un libro base de {fundo} para {version_fuente}; "
                f"encontrados: {encontrados}"
            )
        seleccion.append((candidatos[0].name, fundo))
    return tuple(seleccion)


__all__ = [
    "CAMPOS_NUMERICOS",
    "CLAVES_CORRIDA",
    "FUNDOS_ARCHIVO",
    "LIBROS_OPERATIVOS",
    "MODELO_OPERATIVO_ACTUAL",
    "ResultadoValidacionOperativa",
    "_campana_unica",
    "_fecha",
    "_firma_manifest",
    "_normalizar_claves",
    "datos_proyeccion_operativo",
    "leer_libro_operativo",
    "seleccionar_libros_operativos",
    "sha256_archivo",
]
