"""Entrenamiento XGBoost compartido con la caché analítica persistente."""

from __future__ import annotations

from analitica import nucleo
from servicios.cache_analisis import obtener


def entrenar(panel, objetivo: str = "KgHa") -> nucleo.Ajuste:
    """Entrena una vez por panel/objetivo o recupera el ajuste ya precalculado."""
    return obtener(
        panel,
        f"modelo:ajuste:{objetivo}",
        lambda: nucleo.entrenar(panel.tabla, objetivo=objetivo),
    )
