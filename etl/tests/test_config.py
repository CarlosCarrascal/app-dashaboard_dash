"""La configuración debe rechazar campañas que no tengan un origen declarado."""

from __future__ import annotations

import pytest

from aquanqa_etl import config as modulo


def test_campania_access_desconocida_no_fallback_silencioso(monkeypatch):
    monkeypatch.setenv("ACCESS_CAMPAIGN", "C2027")
    modulo._cargar_env.cache_clear()
    modulo.cargar_config.cache_clear()

    try:
        with pytest.raises(ValueError, match=r"C2027.*C2025.*C2026"):
            modulo.cargar_config()
    finally:
        modulo.cargar_config.cache_clear()
        modulo._cargar_env.cache_clear()
