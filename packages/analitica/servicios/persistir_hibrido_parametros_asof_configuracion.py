"""Configuración y contratos de ejecución del runner candidate-only."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODELO_MACRO = "MacroLegacy_v1"
MODELO_OCURRENCIA = "HibridoOcurrenciaOnline_v2"
MODELO_R09 = "R09_publicado"
BASELINES_REQUERIDOS = (MODELO_MACRO,)
BASELINES_PERMITIDOS = (MODELO_MACRO, MODELO_OCURRENCIA, MODELO_R09)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
HORIZONTES_BASELINE = (1, 2, 4, 6)


@dataclass(frozen=True)
class SolicitudEjecucion:
    """Entrada inmutable que delimita el candidate-only y sus referencias."""

    campania: str
    referencias: Mapping[str, int]
    hashes_esperados: Mapping[str, str] | None
    expected_keyset_hash: str | None
    horizonte: int
    max_cortes: int
    excel_root: str | None
    preflight_only: bool
    dry_run: bool
    cache_dir: str | None


def argumentos(
    argv: list[str] | None = None,
    *,
    description: str | None = None,
) -> argparse.Namespace:
    """Construye los argumentos CLI sin ejecutar efectos externos."""

    parser = argparse.ArgumentParser(description=description or __doc__)
    parser.add_argument("--campania", required=True)
    parser.add_argument("--horizonte-semanas", type=int, default=10)
    parser.add_argument("--max-cortes", type=int, default=0)
    parser.add_argument("--excel-root", default=None)
    parser.add_argument(
        "--baseline-run-id",
        action="append",
        default=[],
        metavar="MODELO=RUN_ID",
    )
    parser.add_argument(
        "--expected-baseline-hash",
        action="append",
        default=[],
        metavar="MODELO=SHA256",
    )
    parser.add_argument("--expected-keyset-hash", default=None)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--cache-dir",
        default=str(PROJECT_ROOT / ".cache" / "analitica" / "candidate-preflight"),
    )
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output-json", default=None)
    return parser.parse_args(argv)


def parsear_mapa(valores: list[str], *, enteros: bool = False) -> dict[str, Any]:
    """Convierte argumentos repetibles ``CLAVE=VALOR`` en un mapa."""

    salida: dict[str, Any] = {}
    for valor in valores:
        if "=" not in valor:
            raise ValueError(f"Referencia inválida: {valor!r}; use MODELO=VALOR.")
        clave, contenido = valor.split("=", 1)
        clave, contenido = clave.strip(), contenido.strip()
        if not clave or not contenido:
            raise ValueError(f"Referencia inválida: {valor!r}.")
        salida[clave] = int(contenido) if enteros else contenido
    return salida


def validar_referencias(referencias: Mapping[str, int]) -> None:
    """Comprueba que el contrato tenga solo baselines permitidos."""

    faltantes = sorted(set(BASELINES_REQUERIDOS) - set(referencias))
    extras = sorted(set(referencias) - set(BASELINES_PERMITIDOS))
    if faltantes or extras:
        raise ValueError(
            "MacroLegacy_v1 es obligatorio; HibridoOcurrenciaOnline_v2 y "
            "R09_publicado son opcionales solo si comparten el mismo contrato; "
            f"faltan={faltantes}, sobran={extras}."
        )


__all__ = [
    "BASELINES_PERMITIDOS",
    "BASELINES_REQUERIDOS",
    "HORIZONTES_BASELINE",
    "MODELO_MACRO",
    "MODELO_OCURRENCIA",
    "MODELO_R09",
    "PROJECT_ROOT",
    "SolicitudEjecucion",
    "argumentos",
    "parsear_mapa",
    "validar_referencias",
]
