"""Fachada compatible del repositorio PostgreSQL de analytics.

La implementación se organiza en mixins por responsabilidad para conservar una única
superficie pública histórica y una única conexión/transacción por operación.
"""

from .artefactos import ArtefactosMixin
from .conexiones_snapshots import ConexionSnapshotsMixin
from .escenarios_decisiones import EscenariosDecisionesMixin
from .metricas_claims import ClaimHistoryConflictError, MetricasClaimsMixin
from .runs_predicciones import RunsPrediccionesMixin


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
