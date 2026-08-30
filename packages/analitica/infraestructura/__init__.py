"""Componentes técnicos para persistir y auditar corridas de proyección."""

from __future__ import annotations

import subprocess
import sys
import types

from analitica import settings
from analitica.dominio.compartido import limpiar_valor, serializar_json, serializar_jsonb


def commit_actual() -> str | None:
    """Devuelve el commit ejecutado para auditoría y reproducibilidad."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=settings._RAIZ_REPOSITORIO,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


# Compatibilidad de import para consumidores que aún usan ``infraestructura.git``.
_git_compat = types.ModuleType(f"{__name__}.git", __doc__)
_git_compat.__package__ = __name__
_git_compat.__file__ = __file__
_git_compat.commit_actual = commit_actual
_git_compat.__all__ = ["commit_actual"]
sys.modules[_git_compat.__name__] = _git_compat
git = _git_compat

__all__ = ["commit_actual", "limpiar_valor", "serializar_json", "serializar_jsonb"]
