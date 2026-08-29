"""Identidad del código ejecutado para auditoría y reproducibilidad."""

from __future__ import annotations

import subprocess

from analitica import settings


def commit_actual() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=settings._RAIZ_REPOSITORIO,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


__all__ = ["commit_actual"]
