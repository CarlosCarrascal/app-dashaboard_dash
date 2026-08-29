"""Contratos de frontera entre las vistas oficiales y el panel histórico."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "dashboard"
sys.path[:0] = [str(APP), str(ROOT / "packages")]

import dash  # noqa: E402

import app as dashboard_app  # noqa: E402,F401
from pages.analitica import bhattacharya  # noqa: E402

RUTAS_HISTORICAS = {
    "/": "pages/pregunta.py",
    "/datos-calidad": "pages/datos_calidad.py",
    "/impacto/evidencia": "pages/impacto/evidencia.py",
    "/impacto/por-modulo": "pages/impacto/por_modulo.py",
    "/impacto/frutos-peso": "pages/impacto/frutos_peso.py",
    "/impacto/descubrimientos": "pages/impacto/descubrimientos.py",
}


def _texto(componente) -> str:
    return repr(componente.to_plotly_json())


def _paginas() -> dict[str, dict]:
    return {pagina["path"]: pagina for pagina in dash.page_registry.values()}


def test_las_rutas_oficiales_no_importan_el_panel_excel_access():
    """La puerta de entrada de `/analitica/*` no puede ser el store histórico."""
    rutas = list((APP / "pages" / "analitica").glob("*.py"))
    oficiales = [ruta for ruta in rutas if 'path="/analitica/' in ruta.read_text(encoding="utf-8")]

    assert oficiales
    for ruta in oficiales:
        codigo = ruta.read_text(encoding="utf-8")
        assert "PANEL_STORE" not in codigo, ruta
        assert "servicios.carga" not in codigo, ruta
        assert "read_excel" not in codigo.lower(), ruta
        assert "read_access" not in codigo.lower(), ruta


def test_las_vistas_oficiales_se_identifican_como_postgresql():
    paginas = _paginas()
    rutas = [pagina for pagina in paginas if pagina.startswith("/analitica/")]

    assert rutas
    for ruta in rutas:
        modulo = Path(paginas[ruta]["module"].replace(".", "/") + ".py")
        archivo = APP / modulo
        codigo = archivo.read_text(encoding="utf-8")
        if ruta == "/analitica/proyeccion":
            codigo += (APP / "pages" / "analitica" / "proyeccion_views.py").read_text(
                encoding="utf-8"
            )
        assert (
            "PostgreSQL" in codigo or "estado_fuente" in codigo or "fuente_oficial" in codigo
        ), ruta


def test_las_vistas_historicas_dejan_visible_su_fuente_y_quedan_separadas():
    paginas = _paginas()
    grupo_historico = "Histórico · Excel/Access"

    for ruta, modulo in RUTAS_HISTORICAS.items():
        pagina = paginas[ruta]
        texto = _texto(pagina["layout"]())
        assert "Fuente histórica" in texto, modulo
        assert "Excel/Access" in texto, modulo
        assert "fuente oficial PostgreSQL" in texto, modulo

    for ruta in set(RUTAS_HISTORICAS) - {"/"}:
        assert paginas[ruta]["grupo"] == grupo_historico, ruta


def test_el_pie_no_presenta_el_panel_excel_como_fuente_oficial():
    info = {"nombre": "IA.final.xlsx", "poda": False, "floracion": False, "error": None}

    pie = dashboard_app._estado_panel(object(), info, "/analitica/relaciones")

    assert pie == "Plataforma analítica\nPostgreSQL · datos publicados"
    assert "IA.final.xlsx" not in pie


def test_bhattacharya_no_fabrica_datos_si_postgresql_no_entrega_un_lote(monkeypatch):
    monkeypatch.setattr(bhattacharya, "_params", lambda *_args, **_kwargs: {})

    salida = bhattacharya._vista(None, "C2026", None, 0, 0, 1.0, 4.6)

    assert "Fuente oficial · PostgreSQL" in _texto(salida[0])
    assert "demostración" in _texto(salida[0])
    assert not salida[1].data
    assert not salida[2].data
    assert salida[3] == "—"
