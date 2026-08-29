from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps" / "dashboard"), str(ROOT / "packages")]

import dash  # noqa: E402

import app as dashboard_app  # noqa: E402,F401
from pages.modelo._legacy import legacy_habilitado  # noqa: E402


def _texto(componente) -> str:
    return repr(componente.to_plotly_json())


def test_existen_las_ocho_paginas_analiticas_y_renderizan():
    esperadas = {
        "/analitica/relaciones",
        "/analitica/descubrimientos",
        "/analitica/modelo",
        "/analitica/explicacion",
        "/analitica/proyeccion",
        "/analitica/backtesting",
        "/analitica/trazabilidad",
        "/analitica/fundamento",
    }
    paginas = {p["path"]: p for p in dash.page_registry.values()}
    assert esperadas <= set(paginas)
    for ruta in esperadas:
        assert paginas[ruta]["layout"]() is not None


def test_vistas_distinguen_explicacion_de_causalidad_y_r2_de_promocion():
    """La garantía es de contenido, no de redacción: la página de explicación tiene que
    negar la lectura causal y la del modelo tiene que dejar el R² fuera de la decisión.
    Se comprueban las ideas y no una frase literal, que se rompe al reescribir el texto."""
    paginas = {p["path"]: p for p in dash.page_registry.values()}
    explicacion = _texto(paginas["/analitica/explicacion"]["layout"]()).lower()
    modelo = _texto(paginas["/analitica/modelo"]["layout"]()).lower()

    assert "causa" in explicacion
    assert "ensayo" in explicacion, "debe decir qué haría falta para afirmar una causa"
    assert "identifica causas" in explicacion or "no implica" in explicacion

    assert "r²" in modelo
    assert "diagnóstico" in modelo
    assert "no participa" in modelo or "no decide" in modelo


def test_modulo_historico_es_opt_in_y_no_se_registra_por_defecto(monkeypatch):
    monkeypatch.delenv("AQUANQA_ENABLE_LEGACY_MODEL", raising=False)
    assert legacy_habilitado() is False
    rutas_legacy = {
        p["path"] for p in dash.page_registry.values() if p["path"].startswith("/modelo/")
    }
    assert not rutas_legacy

    monkeypatch.setenv("AQUANQA_ENABLE_LEGACY_MODEL", "true")
    assert legacy_habilitado() is True
