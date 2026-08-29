"""Control de carga para las páginas históricas de ``/modelo``.

El código histórico se conserva para auditoría y comparación con capturas antiguas, pero
no forma parte del producto analítico oficial. Dash ignora este archivo y los módulos que
no contienen la llamada directa de registro cuando descubre páginas automáticamente; la
bandera solo se evalúa si alguien solicita explícitamente recuperar esas vistas.
"""

from __future__ import annotations

import os
from typing import Any

import dash

_CLAVE = "AQUANQA_ENABLE_LEGACY_MODEL"
_VALORES_ACTIVOS = {"1", "true", "yes", "on"}


def legacy_habilitado() -> bool:
    """Devuelve si se pidió exponer el módulo histórico de manera explícita."""
    return os.environ.get(_CLAVE, "").strip().lower() in _VALORES_ACTIVOS


def registrar_pagina_legacy(module: str, **kwargs: Any) -> None:
    """Registra una página histórica solo con ``AQUANQA_ENABLE_LEGACY_MODEL=true``."""
    if legacy_habilitado():
        dash.register_page(module, **kwargs)
