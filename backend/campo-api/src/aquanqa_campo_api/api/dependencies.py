"""Composición explícita de puertos, adaptadores y servicios."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.security import TokenError
from ..infrastructure.postgres.admin_repository import PostgresAdminRepository
from ..infrastructure.postgres.auth_repository import PostgresAuthRepository
from ..infrastructure.postgres.catalogos_repository import PostgresCatalogRepository
from ..infrastructure.postgres.connection import (
    PostgresConnectionFactory,
    PostgresHealthRepository,
)
from ..infrastructure.postgres.evaluaciones_repository import PostgresEvaluationRepository
from ..infrastructure.postgres.identidad_repository import PostgresIdentityRepository
from ..modules.admin.repository import AdminRepository
from ..modules.admin.service import AdminService
from ..modules.catalogos.repository import CatalogRepository
from ..modules.catalogos.service import CatalogService
from ..modules.evaluaciones.repository import EvaluationRepository
from ..modules.evaluaciones.service import EvaluationService
from ..modules.health.repository import HealthRepository
from ..modules.health.service import HealthService
from ..modules.identidad.repository import IdentityRepository
from ..modules.identidad.service import IdentityService
from ..modules.seguridad.repository import AuthRepository, AuthRepositoryError
from ..modules.seguridad.schemas import AuthUser
from ..modules.seguridad.service import AuthService, InvalidCredentialsError

bearer_scheme = HTTPBearer(auto_error=False)


def get_connection_factory(request: Request) -> PostgresConnectionFactory:
    return request.app.state.postgres_connections


def get_catalog_repository(
    connections: Annotated[PostgresConnectionFactory, Depends(get_connection_factory)],
) -> CatalogRepository:
    return PostgresCatalogRepository(connections)


def get_identity_repository(
    connections: Annotated[PostgresConnectionFactory, Depends(get_connection_factory)],
) -> IdentityRepository:
    return PostgresIdentityRepository(connections)


def get_auth_repository(
    connections: Annotated[PostgresConnectionFactory, Depends(get_connection_factory)],
) -> AuthRepository:
    return PostgresAuthRepository(connections)


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


def get_auth_service(
    repository: Annotated[AuthRepository, Depends(get_auth_repository)],
    request: Request,
) -> AuthService:
    return AuthService(repository, request.app.state.settings)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un token Bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return service.current_user(credentials.credentials)
    except (TokenError, InvalidCredentialsError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except AuthRepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


def get_admin_repository(
    connections: Annotated[PostgresConnectionFactory, Depends(get_connection_factory)],
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> AdminRepository:
    return PostgresAdminRepository(
        connections,
        usuario_id=user.usuario_id,
        unrestricted=user.rol == "admin",
    )


def get_admin_service(
    repository: Annotated[AdminRepository, Depends(get_admin_repository)],
) -> AdminService:
    return AdminService(repository)


def get_admin_user(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> AuthUser:
    if not user.puede("admin:panel:leer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no tiene permiso para abrir el panel administrativo",
        )
    return user


def require_permission(permission: str):
    """Crea una dependencia que valida un permiso administrativo concreto."""

    def permission_dependency(
        user: Annotated[AuthUser, Depends(get_admin_user)],
    ) -> AuthUser:
        if not user.puede(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"El usuario no tiene el permiso {permission}",
            )
        return user

    return permission_dependency


def require_user_permission(permission: str):
    """Valida un permiso de API sin exigir que el usuario sea administrador."""

    def permission_dependency(
        user: Annotated[AuthUser, Depends(get_current_user)],
    ) -> AuthUser:
        if not user.puede(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"El usuario no tiene el permiso {permission}",
            )
        return user

    return permission_dependency


def get_evaluation_service(
    repository: Annotated[EvaluationRepository, Depends(get_evaluation_repository)],
) -> EvaluationService:
    return EvaluationService(repository)


def get_health_service(
    repository: Annotated[HealthRepository, Depends(get_health_repository)],
) -> HealthService:
    return HealthService(repository)


__all__ = [
    "get_admin_service",
    "get_admin_user",
    "get_auth_repository",
    "get_auth_service",
    "get_catalog_service",
    "get_evaluation_service",
    "get_health_service",
    "get_identity_service",
    "get_current_user",
    "require_permission",
    "require_user_permission",
]
