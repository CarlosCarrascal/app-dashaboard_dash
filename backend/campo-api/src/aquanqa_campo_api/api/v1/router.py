"""Router agregado de la versión 1."""

from fastapi import APIRouter

from ...modules.catalogos.router import router as catalogos_router
from ...modules.evaluaciones.router import router as evaluaciones_router
from ...modules.health.router import router as health_router
from ...modules.identidad.router import router as identidad_router

router = APIRouter()
router.include_router(health_router)
router.include_router(identidad_router)
router.include_router(catalogos_router)
router.include_router(evaluaciones_router)

__all__ = ["router"]
