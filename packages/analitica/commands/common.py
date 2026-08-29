"""Utilidades compartidas por los comandos de la CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _repositorio(no_persist: bool):
    if no_persist:
        return None
    from ..proyeccion.gobernanza import RepositorioAnalytics

    return RepositorioAnalytics()


def _registrar_inicio(repo, datos, tipo: str, config: dict, mlflow_id: str | None):
    if repo is None:
        return None, None
    snapshot_id = repo.snapshot(datos)
    return snapshot_id, repo.crear_run(snapshot_id, tipo, config, mlflow_id)


def _salida(**valores):
    print(json.dumps(valores, ensure_ascii=False, indent=2, default=str))


def _raiz_operativa(args) -> Path:
    """Resuelve la carpeta de libros sin depender de una ruta del desarrollador."""

    valor = args.root or os.environ.get("AQUANQA_OPERATIVO_ROOT")
    if not valor:
        raise ValueError(
            "Falta la carpeta de libros operativos. Usa --root o define "
            "AQUANQA_OPERATIVO_ROOT en .env."
        )
    return Path(valor).expanduser().resolve()


def _parsear_horizontes(valor: str | None) -> tuple[int, ...] | None:
    if not valor:
        return None
    try:
        return tuple(sorted({int(parte.strip()) for parte in valor.split(",") if parte.strip()}))
    except ValueError as exc:
        raise ValueError("--horizontes debe ser una lista de enteros separada por comas") from exc
