"""Rutas de autenticación de la interfaz Angular."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ...api.dependencies import get_auth_service, get_current_user
from ...core.errors import error_response
from ...core.security import TokenError
from .repository import AuthRepositoryError
from .schemas import AuthUser, LoginRequest, RefreshRequest, TokenPair
from .service import AuthService, InvalidCredentialsError

router = APIRouter(prefix="/auth", tags=["Autenticación"])
UNAUTHORIZED = error_response(
    "Credenciales inválidas o sesión vencida.", "Email o contraseña incorrectos"
)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Inicia sesión administrativa",
    operation_id="iniciarSesionAdmin",
    responses={
        401: UNAUTHORIZED,
        503: error_response("Base no disponible.", "No se pudo consultar usuarios"),
    },
)
def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPair:
    try:
        return service.login(payload)
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except AuthRepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Renueva una sesión administrativa",
    operation_id="renovarSesionAdmin",
    responses={
        401: UNAUTHORIZED,
        503: error_response("Base no disponible.", "No se pudo consultar usuarios"),
    },
)
def refresh(
    payload: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPair:
    try:
        return service.refresh(payload.refresh_token)
    except (TokenError, InvalidCredentialsError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except AuthRepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error


@router.get(
    "/me",
    response_model=AuthUser,
    summary="Devuelve la identidad activa",
    operation_id="obtenerSesionAdmin",
    responses={
        401: UNAUTHORIZED,
        503: error_response("Base no disponible.", "No se pudo consultar usuarios"),
    },
)
def me(user: Annotated[AuthUser, Depends(get_current_user)]) -> AuthUser:
    return user


__all__ = ["router"]
