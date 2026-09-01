"""Composición explícita de puertos, adaptadores y servicios."""

from typing import Annotated

from fastapi import Depends

from ..core.settings import Settings, get_settings
from ..infrastructure.postgres.catalogos_repository import PostgresCatalogRepository
from ..infrastructure.postgres.connection import (
    PostgresConnectionFactory,
    PostgresHealthRepository,
)
from ..infrastructure.postgres.evaluaciones_repository import PostgresEvaluationRepository
from ..infrastructure.postgres.identidad_repository import PostgresIdentityRepository
from ..modules.catalogos.repository import CatalogRepository
from ..modules.catalogos.service import CatalogService
from ..modules.evaluaciones.repository import EvaluationRepository
from ..modules.evaluaciones.service import EvaluationService
from ..modules.health.repository import HealthRepository
from ..modules.health.service import HealthService
from ..modules.identidad.repository import IdentityRepository
from ..modules.identidad.service import IdentityService


def get_connection_factory(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PostgresConnectionFactory:
    return PostgresConnectionFactory(settings.database_url)


def get_catalog_repository(
    connections: Annotated[PostgresConnectionFactory, Depends(get_connection_factory)],
) -> CatalogRepository:
    return PostgresCatalogRepository(connections)


def get_identity_repository(
    connections: Annotated[PostgresConnectionFactory, Depends(get_connection_factory)],
) -> IdentityRepository:
    return PostgresIdentityRepository(connections)


def get_evaluation_repository(
    connections: Annotated[PostgresConnectionFactory, Depends(get_connection_factory)],
) -> EvaluationRepository:
    return PostgresEvaluationRepository(connections)


def get_health_repository(
    connections: Annotated[PostgresConnectionFactory, Depends(get_connection_factory)],
) -> HealthRepository:
    return PostgresHealthRepository(connections)


def get_catalog_service(
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
) -> CatalogService:
    return CatalogService(repository)


def get_identity_service(
    repository: Annotated[IdentityRepository, Depends(get_identity_repository)],
) -> IdentityService:
    return IdentityService(repository)


def get_evaluation_service(
    repository: Annotated[EvaluationRepository, Depends(get_evaluation_repository)],
) -> EvaluationService:
    return EvaluationService(repository)


def get_health_service(
    repository: Annotated[HealthRepository, Depends(get_health_repository)],
) -> HealthService:
    return HealthService(repository)


__all__ = [
    "get_catalog_service",
    "get_evaluation_service",
    "get_health_service",
    "get_identity_service",
]
