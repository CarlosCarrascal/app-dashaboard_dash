"""Selección determinista de libros operativos por fundo y semana."""

from __future__ import annotations

import re
from pathlib import Path

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
    "FUNDOS_ARCHIVO",
    "LIBROS_OPERATIVOS",
    "VARIANTES_NO_PROMOVIDAS",
    "seleccionar_libros_operativos",
]
