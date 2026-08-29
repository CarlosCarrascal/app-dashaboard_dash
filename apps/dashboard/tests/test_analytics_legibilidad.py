"""La sección analítica no debe mostrar jerga de base de datos a quien la usa.

Estas pruebas fijan lo que se corrigió: nombres de columna crudos en las cabeceras, enums
en inglés como valores, números sin formato y estados vacíos disfrazados de dato.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps" / "dashboard"), str(ROOT / "packages")]

import dash  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import app as dashboard_app  # noqa: E402,F401
from analitica.config import (  # noqa: E402
    ETIQUETAS,
    ETIQUETAS_ANALITICAS,
    FORMATO_ANALITICO,
    GLOSARIO,
    GLOSARIO_ANALITICO,
    etiqueta,
    glosa,
)
from pages.analitica import _comun  # noqa: E402

RUTAS = [
    "/analitica/relaciones",
    "/analitica/descubrimientos",
    "/analitica/modelo",
    "/analitica/explicacion",
    "/analitica/proyeccion",
    "/analitica/backtesting",
    "/analitica/trazabilidad",
    "/analitica/fundamento",
]

# Nombres de columna que antes llegaban tal cual a la cabecera de una tabla.
COLUMNAS_CRUDAS = [
    "wape",
    "mase",
    "rmsse",
    "mae_kg",
    "sesgo_pct",
    "cobertura_80",
    "interval_score_80",
    "ancho_intervalo_kg",
    "pinball_p10",
    "pinball_p50",
    "pinball_p90",
    "n_efectivo",
    "clase_evidencia",
    "banda_horizonte",
    "firma_snapshot",
    "codigo_commit",
    "mlflow_run_id",
    "corte_datos",
    "p50_kg",
    "p10_kg",
    "p90_kg",
    "peso_baya_g",
    "frutos_por_planta",
    "mae_frutos_por_planta",
    "decision_mejora_wape",
    "decision_deterioro_fundo_max",
    "evidence_claim",
]


def _paginas() -> dict[str, object]:
    return {p["path"]: p for p in dash.page_registry.values()}


def _texto_visible(nodo, acumulado=None) -> list[str]:
    """Solo las cadenas que el navegador acaba pintando, sin clases ni identificadores."""
    acumulado = [] if acumulado is None else acumulado
    if isinstance(nodo, str):
        acumulado.append(nodo)
    elif isinstance(nodo, (list, tuple)):
        for hijo in nodo:
            _texto_visible(hijo, acumulado)
    else:
        hijos = getattr(nodo, "children", None)
        if hijos is not None:
            _texto_visible(hijos, acumulado)
    return acumulado


@pytest.mark.parametrize("ruta", RUTAS)
def test_ninguna_pagina_muestra_nombres_crudos_de_columna(ruta):
    texto = " ".join(_texto_visible(_paginas()[ruta]["layout"]()))
    encontrados = sorted({c for c in COLUMNAS_CRUDAS if c in texto})
    assert not encontrados, f"{ruta} muestra nombres de columna sin traducir: {encontrados}"


@pytest.mark.parametrize("ruta", RUTAS)
def test_ninguna_pagina_muestra_enums_en_ingles(ruta):
    """`succeeded`, `published` y compañía vienen de PostgreSQL y no significan nada acá.

    Se ignoran las rutas de archivo de los paquetes de auditoría: el nombre del ZIP es un
    dato real del sistema de archivos, no una etiqueta traducible.
    """
    textos = [t for t in _texto_visible(_paginas()[ruta]["layout"]()) if ".zip" not in t]
    texto = " ".join(textos).lower()
    for enum in ("succeeded", "published", "failed", "running", "created"):
        assert enum not in texto, f"{ruta} muestra el enum «{enum}» sin traducir"


def test_el_glosario_del_panel_no_se_contamina_con_metricas():
    """`ui.glosario()` sin argumentos recorre GLOSARIO entero, y lo usan Pregunta y Datos y
    calidad. Si el vocabulario analítico entrara ahí, esas dos páginas se llenarían de
    métricas de backtesting que no vienen al caso."""
    assert not set(GLOSARIO) & set(GLOSARIO_ANALITICO)
    assert not set(ETIQUETAS) & set(ETIQUETAS_ANALITICAS)
    for termino in ("wape", "mase", "run_id", "cobertura_80", "clase_evidencia"):
        assert termino not in GLOSARIO


def test_los_terminos_con_formato_declarado_tienen_etiqueta():
    faltan = [c for c in FORMATO_ANALITICO if c not in ETIQUETAS_ANALITICAS]
    assert not faltan, f"columnas con formato pero sin nombre legible: {faltan}"


def test_etiqueta_y_glosa_resuelven_los_dos_vocabularios():
    assert etiqueta("DPV") == ETIQUETAS["DPV"]
    assert etiqueta("wape") == ETIQUETAS_ANALITICAS["wape"]
    assert etiqueta("columna_inventada") == "columna_inventada"
    assert glosa("DPV") and glosa("mase")
    assert glosa("columna_inventada") is None


def test_los_porcentajes_no_se_multiplican_dos_veces():
    """`wape` llega como fracción y `sesgo_pct` ya viene en puntos porcentuales.

    Tratarlos igual daba un sesgo de −8.873 % en pantalla.
    """
    assert _comun._formatear("wape", 0.4363) == "43,6 %"
    assert _comun._formatear("sesgo_pct", -88.734) == "-88,7 %"
    assert _comun._formatear("cobertura_80", 0.8147) == "81,5 %"


def test_los_numeros_usan_punto_de_millar():
    assert _comun.numero(3911651.5, 0) == "3.911.652"
    assert _comun._formatear("p50_kg", 3911651.5) == "3.911.652"
    assert _comun._formatear("mase", 1.8811) == "1,88"


def test_los_campos_json_se_leen_como_pares_y_no_como_json_crudo():
    salida = _comun._formatear("detalle", {"observados": 13750, "sin_fuga": True})
    assert "{" not in salida and '"' not in salida
    assert "13.750" in salida and "sí" in salida


def test_la_ruta_de_un_artefacto_se_acorta_al_nombre_del_archivo():
    largo = r"C:\repo\data\salida\analytics\backtest-20260818T190223Z-37e2721f.zip"
    assert _comun._formatear("uri", largo) == "backtest-20260818T190223Z-37e2721f.zip"


def test_una_tabla_vacia_avisa_en_vez_de_fingir_un_dato():
    """Antes devolvía una tabla con una columna «Estado» y el valor «Sin resultados
    persistidos», visualmente idéntica a una fila real de datos."""
    salida = _comun.tabla(pd.DataFrame(), ["wape"], vacio="No hay nada guardado.")
    texto = " ".join(_texto_visible(salida))
    assert "No hay nada guardado." in texto
    assert "Estado" not in texto


def test_una_tabla_recortada_declara_cuantas_filas_oculta():
    df = pd.DataFrame({"wape": [0.1] * 50, "modelo": ["R09"] * 50})
    texto = " ".join(_texto_visible(_comun.tabla(df, ["modelo", "wape"], limite=10)))
    assert "10 de 50" in texto


def test_las_cabeceras_de_una_tabla_vienen_traducidas():
    df = pd.DataFrame({"wape": [0.43], "banda_horizonte": ["operativo"], "n": [120]})
    texto = " ".join(_texto_visible(_comun.tabla(df, ["banda_horizonte", "wape", "n"])))
    assert ETIQUETAS_ANALITICAS["wape"] in texto
    assert "Compromiso" in texto, "el valor del enum también debe traducirse"
    assert "wape" not in texto and "operativo" not in texto


@pytest.mark.parametrize("ruta", RUTAS)
def test_cada_pagina_abre_aunque_la_base_no_responda(ruta, monkeypatch):
    """La vista tiene que poder abrirse durante un bootstrap o una migración."""
    vacio = {
        "error": "Analytics no disponible: OperationalError: conexión rechazada",
        "runs": pd.DataFrame(),
        "decisiones": pd.DataFrame(),
        "metricas": pd.DataFrame(),
        "claims": pd.DataFrame(),
        "proyeccion": pd.DataFrame(),
        "calidad": pd.DataFrame(),
        "artefactos": pd.DataFrame(),
        "catalogo": pd.DataFrame(),
    }
    monkeypatch.setattr(_comun, "datos", lambda: vacio)
    assert _paginas()[ruta]["layout"]() is not None


# ── Indicador de precisión ───────────────────────────────────────────────────


def _estado_con_metricas() -> dict:
    return {
        "error": None,
        "runs": pd.DataFrame(),
        "decisiones": pd.DataFrame(
            [
                {
                    "banda_horizonte": "operativo",
                    "campeon": "R09_publicado",
                    "challenger": "Random_Forest",
                    "resultado": "retener",
                }
            ]
        ),
        "metricas": pd.DataFrame(
            [
                {
                    "modelo": "R09_publicado",
                    "banda_horizonte": "operativo",
                    "n": 7990,
                    "wape": 0.549,
                    "sesgo_pct": 28.3,
                    "cobertura_80": 0.75,
                    "mase": 0.87,
                }
            ]
        ),
        "claims": pd.DataFrame(),
        "proyeccion": pd.DataFrame(),
        "calidad": pd.DataFrame(),
        "artefactos": pd.DataFrame(),
        "catalogo": pd.DataFrame(),
    }


def test_el_indicador_traduce_el_error_en_acierto():
    """45,1 % de acierto es más legible que «WAPE 0,549» y dice exactamente lo mismo."""
    texto = " ".join(_texto_visible(_comun.indicador_precision(_estado_con_metricas())))
    assert "45,1 %" in texto
    assert "7.990" in texto, "debe decir sobre cuántos casos está medido"
    # «R09» era el nombre de la consulta del Access original, no de un modelo.
    assert "Proyección del equipo" in texto, "el modelo se nombra traducido"


def test_el_indicador_dice_hacia_que_lado_se_equivoca():
    """Un sesgo positivo significa prometer de más, y eso en packing cuesta distinto."""
    texto = " ".join(_texto_visible(_comun.indicador_precision(_estado_con_metricas())))
    assert "de más" in texto
    assert "28,3 %" in texto


def test_el_indicador_avisa_cuando_no_hay_nada_medido():
    vacio = dict(_estado_con_metricas(), decisiones=pd.DataFrame(), metricas=pd.DataFrame())
    texto = " ".join(_texto_visible(_comun.indicador_precision(vacio)))
    assert "Todavía no hay una medición" in texto


def test_el_indicador_usa_el_plazo_de_compromiso_por_defecto():
    """Mezclar plazos daría una cifra optimista: los largos siempre salen peor."""
    import inspect

    assert inspect.signature(_comun.indicador_precision).parameters["banda"].default == "operativo"


def test_la_proyeccion_no_recorta_filas_por_rendimiento():
    """El SELECT sin LIMIT: un recorte haría desaparecer un fundo sin avisar."""
    from pathlib import Path

    servicio = Path(_comun.__file__).parents[2] / "servicios" / "analytics.py"
    codigo = servicio.read_text(encoding="utf-8")
    bloque = codigo.split("reporting.proyeccion_vigente")[1].split('"""')[0]
    assert "LIMIT" not in bloque.upper()
