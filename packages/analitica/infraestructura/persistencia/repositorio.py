"""Fachada compatible del repositorio PostgreSQL de analytics.

La implementación se organiza en mixins por responsabilidad para conservar una única
superficie pública histórica y una única conexión/transacción por operación.
"""

from analitica.infraestructura.persistencia.artefactos import ArtefactosMixin
from analitica.infraestructura.persistencia.conexiones_snapshots import ConexionSnapshotsMixin
from analitica.infraestructura.persistencia.escenarios_decisiones import EscenariosDecisionesMixin
from analitica.infraestructura.persistencia.metricas_claims import (
    ClaimHistoryConflictError,
    MetricasClaimsMixin,
)
from analitica.infraestructura.persistencia.runs_predicciones import RunsPrediccionesMixin


class RepositorioAnalytics(
    ConexionSnapshotsMixin,
    RunsPrediccionesMixin,
    MetricasClaimsMixin,
    EscenariosDecisionesMixin,
    ArtefactosMixin,
):
    """Superficie histórica de persistencia, compuesta por responsabilidades."""

    pass


__all__ = ["ClaimHistoryConflictError", "RepositorioAnalytics"]
