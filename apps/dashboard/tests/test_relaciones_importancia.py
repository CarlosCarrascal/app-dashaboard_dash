"""La página de relaciones: la evidencia, y cómo se presenta sin engañar.

El criterio que estas pruebas protegen, en una línea: **nada se presenta como hallazgo sin
decir sobre cuánto se apoya y cuánto se descartó para llegar a él.** De ahí salen las tres
familias de comprobaciones: que una importancia cuyo margen cruza el cero no se declare
útil, que un coeficiente venga siempre acompañado de su magnitud en unidades reales, y que
el recuento del filtrado sea visible.

Lo que se puede *afirmar* con esta evidencia vive en Descubrimientos, no acá.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps" / "dashboard"), str(ROOT / "packages")]

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import app as dashboard_app  # noqa: E402,F401
from pages.analitica import _comun  # noqa: E402
from pages.analitica import relaciones as pagina  # noqa: E402
from pages.analitica._relaciones import analisis, formato, graficos, paneles, textos  # noqa: E402


def _texto(nodo, acc=None) -> list[str]:
    acc = [] if acc is None else acc
    if isinstance(nodo, str):
        acc.append(nodo)
    elif isinstance(nodo, (list, tuple)):
        for hijo in nodo:
            _texto(hijo, acc)
    else:
        hijos = getattr(nodo, "children", None)
        if hijos is not None:
            _texto(hijos, acc)
    return acc


def _plano(nodo) -> str:
    """El texto del árbol como una sola frase, con los espacios colapsados.

    Los veredictos se construyen por fragmentos —para poder resaltar la cifra sin Markdown—
    y unirlos deja dobles espacios que no existen en pantalla.
    """
    return re.sub(r"\s+", " ", " ".join(_texto(nodo))).strip()


def _enlaces(nodo, acc=None) -> list[str]:
    """Los `href` del árbol: `_texto` solo recoge cadenas y se saltaría un enlace."""
    acc = [] if acc is None else acc
    if isinstance(nodo, (list, tuple)):
        for hijo in nodo:
            _enlaces(hijo, acc)
    elif not isinstance(nodo, str):
        destino = getattr(nodo, "href", None)
        if destino:
            acc.append(destino)
        hijos = getattr(nodo, "children", None)
        if hijos is not None:
            _enlaces(hijos, acc)
    return acc


def _permutacion(ic_inferior_estructura: float = 54.3) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "familia": "estructura_productiva",
                "columnas": "plantas, frutos_por_planta, peso_baya_g",
                "aumento_mae": 60.9,
                "ic_inferior": ic_inferior_estructura,
                "ic_superior": 65.1,
            },
            {
                "familia": "calendario",
                "columnas": "semana_objetivo_sin, semana_objetivo_cos",
                "aumento_mae": -0.58,
                "ic_inferior": -2.34,
                "ic_superior": 0.98,
            },
            {
                "familia": "horizonte",
                "columnas": "horizonte_semanas",
                "aumento_mae": -2.07,
                "ic_inferior": -3.62,
                "ic_superior": 0.16,
            },
        ]
    )


def _estado(**extra) -> dict:
    base = {
        "error": None,
        "runs": pd.DataFrame(),
        "decisiones": pd.DataFrame(),
        "metricas": pd.DataFrame(),
        "claims": pd.DataFrame(),
        "proyeccion": pd.DataFrame(),
        "lotes": pd.DataFrame(),
        "calidad": pd.DataFrame(),
        "artefactos": pd.DataFrame(),
        "catalogo": pd.DataFrame(),
        "relaciones": pd.DataFrame(),
        "inferencia": pd.DataFrame(),
        "ablaciones": pd.DataFrame(),
        "permutacion": pd.DataFrame(),
        "shap": pd.DataFrame(),
        "fuentes": pd.DataFrame(),
        "matriz": pd.DataFrame(),
        "packing": pd.DataFrame(),
    }
    base.update(extra)
    return base


def _matriz() -> pd.DataFrame:
    filas = []
    for pred, resp, comp, tipo, efecto, mediana in [
        ("humedad", "peso_real_g", "peso", "externa", -0.31, 3.39),
        ("lamina_mm", "frutos_por_planta_muestra", "frutos", "externa", 42.0, 855.0),
        ("prop_e5", "kg_ha", "kilos", "cultivo", 310.0, 984.0),
    ]:
        for rezago in range(3):
            filas.append(
                {
                    "predictor": pred,
                    "respuesta": resp,
                    "componente": comp,
                    "tipo_predictor": tipo,
                    "rezago_semanas": rezago,
                    "n": 400,
                    "n_efectivo": 40,
                    "modulos": 18,
                    "pearson": 0.3,
                    "p_pearson": 0.001,
                    "correlacion_parcial": 0.35 - 0.05 * rezago,
                    "placebo_futuro": 0.05,
                    "desfases_probados": 3,
                    "p_seleccion_desfase": 0.003,
                    "p_ajustado_bh": 0.01,
                    "placebo_supera_estimacion": False,
                    "sobrevive": True,
                    "efecto_rango_iqr": efecto,
                    "iqr_predictor": 2.0,
                    "mediana_respuesta": mediana,
                }
            )
    # Una que el placebo descarta y otra que no pasa la corrección.
    filas.append(
        {**filas[0], "predictor": "lluvia", "placebo_supera_estimacion": True, "sobrevive": False}
    )
    filas.append({**filas[0], "predictor": "radiacion", "p_ajustado_bh": 0.9, "sobrevive": False})
    return pd.DataFrame(filas)


def _packing() -> pd.DataFrame:
    filas = []
    for pred, resp, r in [
        ("calibre_medio_mm", "peso_real_g", 0.657),
        ("lluvia", "proporcion_descarte", 0.408),
        ("calibre_medio_mm", "kg_ha_modulo", 0.310),
    ]:
        for rezago in range(3):
            filas.append(
                {
                    "predictor": pred,
                    "respuesta": resp,
                    "unidad": "modulo_semana",
                    "rezago_semanas": rezago,
                    "n": 600,
                    "n_efectivo": 98,
                    "modulos": 15,
                    "pearson": r + 0.1,
                    "p_pearson": 0.0001,
                    "correlacion_parcial": r - 0.05 * rezago,
                    "placebo_futuro": 0.02,
                    "desfases_probados": 3,
                    "p_seleccion_desfase": 0.0002,
                    "p_ajustado_bh": 0.001,
                    "placebo_supera_estimacion": False,
                    "sobrevive": True,
                    "efecto_rango_iqr": 0.72 if resp == "peso_real_g" else 300.0,
                    "iqr_predictor": 1.4,
                    "mediana_respuesta": 3.27,
                }
            )
    return pd.DataFrame(filas)


# ── Consolidación de los barridos ────────────────────────────────────────────


def test_se_consolida_un_hallazgo_por_par_y_no_por_desfase():
    """Tres desfases del mismo par son un hallazgo, no tres."""
    encontrados = analisis.hallazgos(_estado(matriz=_matriz()))
    assert len(encontrados) == 3, "9 pruebas de 3 pares son 3 hallazgos"
    assert set(encontrados.desfases_que_sobreviven) == {3}


def test_se_conserva_el_desfase_de_mayor_efecto_de_cada_par():
    """De los tres desfases del par se resume el más fuerte, no el primero ni el último."""
    encontrados = analisis.hallazgos(_estado(matriz=_matriz()))
    assert set(encontrados.rezago_semanas) == {0}, "el rezago 0 es el de mayor correlación"


def test_los_dos_barridos_suman_sin_pisarse():
    """Los hallazgos de la matriz y los del packing son independientes."""
    encontrados = analisis.hallazgos(_estado(packing=_packing(), matriz=_matriz()))
    assert len(encontrados) == 6, "3 pares de la matriz + 3 del packing"


def test_sin_barrido_no_se_inventa_nada():
    assert analisis.hallazgos(_estado()).empty
    assert analisis.matriz_completa(_estado()).empty
    assert not analisis.resumen_barrido(_estado()).hay_datos


def test_un_hallazgo_solido_exige_semanas_y_desfases_contiguos():
    """Una relación que aparece en un solo desfase y con muestra corta es una pista."""
    corta = _matriz().assign(n_efectivo=20)
    assert set(analisis.hallazgos(_estado(matriz=corta)).nivel) == {"hipotesis"}
    assert set(analisis.hallazgos(_estado(matriz=_matriz())).nivel) == {"solido"}


# ── Unidad de análisis ───────────────────────────────────────────────────────


def test_la_unidad_la_fija_el_predictor_y_no_el_panel_del_que_sale():
    """Un cruce climático dentro del panel de lotes sigue teniendo una sola estación detrás.

    Declararlo como «lote × semana» sugeriría miles de observaciones independientes cuando
    todos los lotes de una misma semana comparten exactamente el mismo dato de clima.
    """
    assert "semana" in analisis.unidad_del_par("humedad", "lote × semana")
    assert "lote" not in analisis.unidad_del_par("humedad", "lote × semana")
    # El riego se aplica por módulo, aunque la cosecha se registre por lote.
    assert analisis.unidad_del_par("lamina_mm", "lote × semana") == "módulo × semana"
    # Un censo sí varía lote a lote: conserva la unidad del panel.
    assert analisis.unidad_del_par("prop_e5", "lote × semana") == "lote × semana"


def test_los_hallazgos_climaticos_declaran_la_unidad_semanal():
    encontrados = analisis.hallazgos(_estado(matriz=_matriz()))
    unidades = dict(zip(encontrados.predictor, encontrados.unidad_analisis, strict=True))
    assert "clima común" in unidades["humedad"]
    assert unidades["prop_e5"] == "lote × semana"


def test_el_packing_conserva_su_grano_salvo_cuando_manda_el_clima():
    """Un hallazgo de packing no puede leerse como si fuera por lote.

    Salvo cuando el predictor es climático: entonces manda la estación, no la línea de
    proceso, y las observaciones independientes vuelven a ser semanas.
    """
    encontrados = analisis.hallazgos(_estado(packing=_packing()))
    unidades = dict(zip(encontrados.predictor, encontrados.unidad_analisis, strict=True))
    assert unidades["calibre_medio_mm"] == "módulo × semana"
    assert "clima común" in unidades["lluvia"]


# ── Traducción a magnitudes ──────────────────────────────────────────────────


def test_las_siglas_sobreviven_al_pasar_a_minuscula():
    """`.lower()` convertía «estado E5» en «estado e5», y DPV en dpv."""
    assert formato.en_minuscula("Proporción en estado E5") == "proporción en estado E5"
    assert formato.en_minuscula("Sequedad del aire (DPV)") == "sequedad del aire (DPV)"
    assert formato.en_minuscula("") == ""


def test_el_efecto_se_expresa_en_la_unidad_en_que_se_habla_de_la_variable():
    """«0,024 de proporción de descarte» no lo entiende nadie; «2,4 puntos» sí."""
    cifra, unidad = formato.efecto_legible("proporcion_descarte", 0.0244)
    assert cifra == "2,4" and unidad == "puntos de descarte"
    cifra, unidad = formato.efecto_legible("kg_ha", 548.52)
    assert cifra == "549" and unidad == "kg/ha"


def test_la_cifra_del_efecto_no_arrastra_el_signo():
    """El signo lo dice la palabra «más» o «menos»; repetirlo daría «-0,31 g menos»."""
    cifra, _ = formato.efecto_legible("peso_real_g", -0.31)
    assert not cifra.startswith("-")


def test_una_correlacion_real_con_recorrido_nulo_no_se_muestra_como_cero():
    """Lluvia y descarte correlacionan 0,41 y el efecto práctico es nulo: en la costa el
    cuarto seco y el lluvioso son casi el mismo milímetro. Escribir «0,0» leería como
    error de cálculo en vez de como el resultado que es."""
    cifra, _ = formato.efecto_legible("proporcion_descarte", 0.00002)
    assert cifra == "menos de 0,1"


def test_la_frase_no_repite_la_unidad_cuando_ya_nombra_la_variable():
    """«63,6 flores más de flores por planta» era el resultado de concatenar sin mirar."""
    frase = formato.frase_efecto(
        {
            "predictor": "temp_max",
            "respuesta": "flores_por_planta_muestra",
            "efecto_rango_iqr": 63.6,
            "mediana_respuesta": 57.3,
        }
    )
    assert "flores por planta más" in frase
    assert "de flores por planta" not in frase


def test_un_efecto_enorme_se_dice_en_veces_y_no_en_porcentaje():
    """«719 % sobre lo habitual» no se procesa mentalmente; «multiplica por 9» sí."""
    frase = formato.frase_efecto(
        {
            "predictor": "temp_media",
            "respuesta": "proporcion_descarte",
            "efecto_rango_iqr": 0.0244,
            "mediana_respuesta": 0.003,
        }
    )
    # 2,4 puntos sobre una mediana de 0,3 deja el descarte en 2,7: nueve veces lo habitual.
    assert "multiplica por 9" in frase
    assert "%" not in frase


def test_sin_efecto_calculado_no_se_inventa_una_frase():
    """Una corrida vieja no trae las columnas de efecto: el silencio es la respuesta."""
    assert formato.frase_efecto({"predictor": "humedad", "respuesta": "kg_ha"}) == ""


# ── La matriz y el perfil de desfases ────────────────────────────────────────


def test_el_mapa_solo_pinta_lo_que_sobrevivio():
    """Las celdas en blanco son cruces probados y descartados, no datos que falten."""
    figura = graficos.mapa_matriz(_matriz())
    trazo = figura.data[0]
    # 3 predictores supervivientes, no los 5 que se probaron.
    assert len(trazo.y) == 3
    assert "lluvia" not in trazo.y, "la descartada por el placebo no debe pintarse"


def test_el_mapa_usa_una_escala_que_distingue_el_signo():
    """Con una escala secuencial, «sube junto» y «baja junto» se verían igual de intensos."""
    figura = graficos.mapa_matriz(_matriz())
    assert figura.data[0].zmid == 0, "la escala debe estar centrada en cero"
    assert figura.data[0].zmin < 0 < figura.data[0].zmax


def test_sin_supervivientes_el_mapa_queda_vacio_en_vez_de_reventar():
    assert not graficos.mapa_matriz(_matriz().assign(sobrevive=False)).data
    assert not graficos.mapa_matriz(pd.DataFrame()).data


def test_el_perfil_recorre_todos_los_desfases_probados_no_solo_el_ganador():
    """El valor del gráfico está en ver la forma de la curva, incluidos los desfases que no
    sobrevivieron: una relación que salta de signo entre semanas contiguas es ruido."""
    figura = graficos.perfil_desfases(_matriz())
    assert figura.data, "debe haber al menos una línea"
    for traza in figura.data:
        assert len(traza.x) == 3, "los tres desfases probados, no solo el superviviente"


def test_el_perfil_marca_cuales_desfases_pasaron_los_filtros():
    """Sin esa marca no se distingue la parte comprobada de la exploratoria de la curva."""
    matriz = _matriz()
    matriz.loc[matriz.rezago_semanas == 2, "sobrevive"] = False
    figura = graficos.perfil_desfases(matriz)
    tamanos = {t for traza in figura.data for t in traza.marker.size}
    assert len(tamanos) == 2, "los supervivientes deben verse distintos de los demás"


# ── Efectos en unidades reales ───────────────────────────────────────────────


def test_los_efectos_se_separan_por_unidad_y_no_se_mezclan_en_un_eje():
    """Kilos, gramos y puntos de descarte en un mismo eje obligarían a normalizar, y
    normalizar por la mediana haría estallar al descarte hasta ocupar la escala entera."""
    encontrados = analisis.hallazgos(_estado(matriz=_matriz()))
    titulos = [t for t, _, _ in graficos.efectos_por_unidad(encontrados)]
    assert "Lo que mueve los kilos" in titulos
    assert "Lo que mueve el peso del fruto" in titulos
    unidades = {u for _, u, _, _, _, _ in textos.BLOQUES_GRAFICO}
    assert unidades == {"kg/ha", "gramos por fruto", "puntos de descarte"}


def test_el_descarte_se_grafica_en_puntos_y_no_en_proporcion():
    """Una barra de 0,024 junto a otra de 549 no se vería."""
    escalas = {r[0][0]: r[2] for r in textos.BLOQUES_GRAFICO}
    assert escalas["proporcion_descarte"] == 100.0
    assert escalas["kg_ha"] == 1.0


def test_las_hipotesis_declaran_por_que_no_bastan():
    """Listarlas sin decir qué les falta las volvería indistinguibles de las sólidas."""
    corta = _matriz().assign(n_efectivo=20)
    texto = " ".join(_texto(paneles.tabla_hipotesis(analisis.hallazgos(_estado(matriz=corta)))))
    assert "solo 20 semanas medidas" in texto
    assert "para decidir qué medir mejor" in texto


def test_sin_patrones_solidos_no_se_dibuja_un_grafico_enganoso():
    corta = _matriz().assign(n_efectivo=20)
    texto = " ".join(_texto(paneles.panel_efectos(analisis.hallazgos(_estado(matriz=corta)))))
    assert "Ningún patrón alcanza el nivel de sólido" in texto


# ── El embudo de filtrado ────────────────────────────────────────────────────


def test_el_barrido_declara_cuantas_combinaciones_se_probaron():
    """Sin decir cuánto se probó, el número de hallazgos no significa nada."""
    barrido = analisis.resumen_barrido(_estado(matriz=_matriz()))
    assert barrido.pruebas == 11, "9 cruces vivos + 2 descartados"
    texto = _plano(paneles.panel_filtrado(barrido))
    assert "De 11 cruces probados quedan 9" in texto
    assert "por puro azar se esperaba" in texto.lower()


def test_el_placebo_descarta_una_relacion_aunque_su_p_sea_bajo():
    """Un p bajo no basta: si una serie inventada explica lo mismo, era el calendario."""
    barrido = analisis.resumen_barrido(_estado(matriz=_matriz()))
    assert barrido.placebo == 1
    texto = _plano(paneles.panel_filtrado(barrido))
    assert "1 cayó en el placebo" in texto, "la concordancia de plural también se lee"
    assert "explica igual de bien" in texto


def test_el_veredicto_modula_su_afirmacion_segun_la_distancia_al_azar():
    """Sobrevivir a los filtros no significa nada por sí solo: informa cuánto supera el
    recuento a lo que saldría de una base sin ninguna relación real.

    Con la inferencia anterior —que contaba filas en vez de semanas— la distancia era de
    284 contra 74 y parecía holgada; medida bien es de 109 contra 74.
    """
    barrido = analisis.resumen_barrido(_estado(matriz=_matriz(), packing=_packing()))
    holgado = dataclasses.replace(barrido, supervivientes=barrido.esperados_por_azar * 5)
    justo = dataclasses.replace(barrido, supervivientes=barrido.esperados_por_azar * 2)
    corto = dataclasses.replace(barrido, supervivientes=barrido.esperados_por_azar)

    assert "no se explica por azar" in _plano(paneles.panel_filtrado(holgado))
    assert "el margen es estrecho" in _plano(paneles.panel_filtrado(justo))
    texto_corto = _plano(paneles.panel_filtrado(corto))
    assert "demasiado corta para distinguirla del azar" in texto_corto
    assert "exploratorio" in texto_corto


def test_el_rotulo_de_solidos_cede_ante_el_recuento():
    """Llamar «sólidos» a unos pares mientras el embudo dice que el conjunto no se separa
    del azar es contradecirse dentro de la misma pantalla."""
    hallazgos = analisis.hallazgos(_estado(matriz=_matriz(), packing=_packing()))
    barrido = analisis.resumen_barrido(_estado(matriz=_matriz(), packing=_packing()))
    corto = dataclasses.replace(barrido, supervivientes=barrido.esperados_por_azar)
    texto = _plano(paneles.kpis(hallazgos, corto))
    assert "Patrones sólidos" not in texto
    assert "no se separa del azar" in texto

    holgado = dataclasses.replace(barrido, supervivientes=barrido.esperados_por_azar * 5)
    assert "Patrones sólidos" in _plano(paneles.kpis(hallazgos, holgado))


def test_el_embudo_solo_puede_decrecer():
    """Un embudo donde una etapa posterior tiene más elementos sería un error de conteo."""
    barrido = analisis.resumen_barrido(_estado(matriz=_matriz(), packing=_packing()))
    etapas = [barrido.pruebas, barrido.sin_corregir, barrido.tras_placebo, barrido.supervivientes]
    assert etapas == sorted(etapas, reverse=True)


def test_el_embudo_marca_la_linea_de_azar():
    """Sin esa referencia, el número de supervivientes no se puede juzgar."""
    barrido = analisis.resumen_barrido(_estado(matriz=_matriz()))
    figura = graficos.embudo_filtrado(barrido)
    lineas = [f for f in figura.layout.shapes if f.type == "line"]
    assert lineas, "debe dibujarse la referencia de azar"
    assert barrido.esperados_por_azar == round(0.05 * barrido.pruebas)


def test_el_barrido_advierte_que_vale_menos_que_una_hipotesis_previa():
    """Un hallazgo de un barrido de cientos de cruces no es evidencia, es una pista."""
    texto = " ".join(
        _texto(paneles.panel_filtrado(analisis.resumen_barrido(_estado(matriz=_matriz()))))
    )
    assert "no es lo mismo" in texto.lower()
    assert "volver a comprobarlos" in texto


def test_si_nada_sobrevive_se_dice_sin_disimular():
    matriz = _matriz().assign(sobrevive=False)
    texto = " ".join(
        _texto(paneles.panel_filtrado(analisis.resumen_barrido(_estado(matriz=matriz))))
    )
    assert "ninguna sobrevive" in texto
    assert "no encontrar nada es un resultado legítimo" in texto


# ── Apertura y reparto con Descubrimientos ───────────────────────────────────


def test_la_apertura_cuenta_lo_probado_junto_a_lo_hallado():
    """Enseñar los hallazgos sin el denominador es la forma más fácil de exagerar."""
    estado = _estado(packing=_packing(), matriz=_matriz(), permutacion=_permutacion())
    barrido = analisis.resumen_barrido(estado)
    texto = " ".join(_texto(paneles.kpis(analisis.hallazgos(estado), barrido)))
    assert "Cruces probados" in texto
    assert "Esperados por azar" in texto
    assert "Patrones sólidos" in texto


def test_el_resumen_no_inventa_cifras_cuando_no_hay_datos():
    texto = " ".join(_texto(paneles.kpis(pd.DataFrame(), analisis.resumen_barrido(_estado()))))
    assert "—" in texto, "sin datos se muestra un guion, no un cero engañoso"


def test_la_sintesis_remite_a_descubrimientos_en_vez_de_duplicarlo():
    """Las decisiones y su alcance se publican en Descubrimientos. Repetirlas acá haría que
    las dos páginas se contradijeran al primer cambio de umbral."""
    nodo = paneles.sintesis(analisis.hallazgos(_estado(matriz=_matriz())))
    assert "/analitica/descubrimientos" in _enlaces(nodo), "debe enlazar a Descubrimientos"
    assert "la evidencia" in " ".join(_texto(nodo))


def test_la_sintesis_nombra_la_relacion_mas_fuerte_con_su_muestra():
    texto = " ".join(_texto(paneles.sintesis(analisis.hallazgos(_estado(packing=_packing())))))
    assert "calibre" in texto.lower()
    assert "98 semanas" in texto


def test_sin_hallazgos_la_sintesis_lo_dice_en_vez_de_quedar_en_blanco():
    assert "Todavía no hay resultados" in " ".join(_texto(paneles.sintesis(pd.DataFrame())))


def test_las_lecciones_ensenan_a_no_leer_mal_los_numeros():
    """Sin ellas, una correlación alta con efecto nulo se lee como un hallazgo importante."""
    texto = _plano(paneles.panel_lecciones())
    assert "correlación 0,41, efecto cero" in texto, "el caso que justifica todo el enfoque"
    assert "no se asigna al azar" in texto
    for titulo, porque, hacer in textos.LECCIONES:
        assert porque and hacer, f"«{titulo}» no dice por qué engaña ni qué hacer"
        # Tres renglones cortos, no un párrafo: el lector llega tras cinco gráficos.
        assert len(porque) < 130 and len(hacer) < 130, f"«{titulo}» volvió a ser un párrafo"


# ── Importancia de variables ─────────────────────────────────────────────────


def test_solo_se_declara_util_lo_que_no_cruza_el_cero():
    texto = _plano(paneles.panel_importancia(_estado(permutacion=_permutacion())))
    assert "sostiene el pronóstico es estructura productiva" in texto
    assert "no muestran un aporte distinguible de cero" in texto
    assert "61 kg" in texto


def test_si_ninguna_familia_supera_el_ruido_no_se_afirma_ninguna():
    """Con todos los intervalos cruzando el cero, la conclusión honesta es que no se sabe."""
    floja = _permutacion(ic_inferior_estructura=-5.0)
    texto = " ".join(_texto(paneles.panel_importancia(_estado(permutacion=floja))))
    assert "Ningún grupo de variables aporta de forma distinguible" in texto
    assert "Lo que sostiene el pronóstico es" not in texto


def test_la_tabla_de_familias_explica_que_incluye_cada_grupo():
    """Nombrar el grupo sin decir de qué se compone deja al lector adivinando."""
    texto = " ".join(_texto(paneles.panel_importancia(_estado(permutacion=_permutacion()))))
    assert "las plantas del lote, los frutos por planta y el peso de la baya" in texto.lower()
    assert "No distinguible de cero" in texto
    assert "estructura_productiva" not in texto, "el identificador no debe llegar a pantalla"


def test_los_grupos_sin_aporte_se_nombran_en_la_tabla_y_no_en_prosa():
    """Enumerarlos en una frase producía dobles negaciones («ni X ni Y no muestran»).

    Ahora la lista vive en la tabla, donde cada grupo lleva su propio veredicto.
    """
    texto = " ".join(_texto(paneles.panel_importancia(_estado(permutacion=_permutacion()))))
    assert texto.count("No distinguible de cero") == 2, "calendario y anticipación"
    assert " ni " not in texto


def test_se_distingue_la_importancia_para_el_modelo_de_la_relacion_en_el_campo():
    """Son preguntas distintas: una variable puede correlacionar fuerte y no aportar nada."""
    texto = " ".join(_texto(paneles.panel_importancia(_estado(permutacion=_permutacion()))))
    assert "no es lo mismo que las relaciones" in texto.lower()


def test_sin_analisis_de_importancia_se_avisa_en_vez_de_dejar_el_hueco():
    texto = " ".join(_texto(paneles.panel_importancia(_estado())))
    assert "Todavía no se ha ejecutado el análisis de importancia" in texto


# ── Inventario de variables ──────────────────────────────────────────────────


def test_el_inventario_distingue_lo_usado_de_lo_medido_sin_usar():
    """Sin esta distinción, una variable ausente del ranking se lee como «no importa»
    cuando puede significar «nunca se probó»."""
    texto = " ".join(_texto(paneles.panel_inventario()))
    # La categoría se nombra siempre, incluso vacía: hace visible el próximo dato que se
    # levante en campo y nadie aproveche.
    assert "registra en campo sin usarse" in texto or "todavía no se usan" in texto
    assert "no existen en ninguna tabla" in texto
    assert "puede ser que no importe, o puede ser que nunca se haya probado" in texto


def test_el_inventario_cubre_el_ciclo_completo_del_cultivo():
    """La cadena que debe recorrer es poda → rama → brote → yema → flor → cuajado →
    estados → fruto: si falta un eslabón, el análisis empieza por la mitad."""
    texto = " ".join(_texto(paneles.panel_inventario()))
    for variable in (
        "Poda",
        "Ramas",
        "Brotes",
        "Yemas abiertas",
        "Flores",
        "Cuajado",
        "Estados E1 a E5",
    ):
        assert variable in texto, f"falta {variable} en el inventario"
    estados = {e for _, _, e, _ in textos.INVENTARIO_VARIABLES}
    assert estados <= {"modelo", "relacion", "sin_usar", "sin_dato"}
    assert "sin_usar" in textos.ESTADOS_VARIABLE


def test_el_inventario_declara_las_ausencias_de_origen():
    """Nutrición, polinización y suelo no se pueden analizar: no existen."""
    texto = " ".join(_texto(paneles.panel_inventario()))
    for ausente in ("Nutrición", "Polinización", "Suelo", "Pronóstico del tiempo"):
        assert ausente in texto
    sin_dato = [n for _, n, e, _ in textos.INVENTARIO_VARIABLES if e == "sin_dato"]
    assert len(sin_dato) >= 4
    # Una columna que existe en el origen pero llega vacía es una ausencia, no un dato.
    assert any("desarrollo del brote" in n for n in sin_dato)


def test_cada_variable_del_inventario_explica_que_es():
    for grupo, nombre, estado, detalle in textos.INVENTARIO_VARIABLES:
        assert grupo and nombre and detalle, f"{nombre} sin descripción"
        assert len(detalle) > 25, f"{nombre}: la descripción no explica nada"
        assert estado in textos.ESTADOS_VARIABLE


# ── Cómo se mide cada cosa ───────────────────────────────────────────────────
#
# La sección que declaraba los tres bloques por separado se eliminó: repetía en prosa la
# columna «unidad de análisis» de la tabla y llegaba después del embudo, sin relación con
# él. Lo que no podía perderse —por qué unas filas de la matriz valen más que otras— pasó
# a la instrucción de lectura de la propia matriz, que es donde se necesita.


def test_la_matriz_declara_por_que_unas_filas_valen_mas_que_otras():
    """Un 0,66 de packing y un 0,25 de clima no se leen igual, y la razón es la medición."""
    texto = _plano(paneles.panel_matriz(_matriz()))
    assert "una sola estación para los cinco fundos" in texto
    assert "las semanas y no los lotes" in texto
    assert "0,66" in texto and "0,26" in texto, "el contraste packing / censo de bayas"
    assert "15 de los 26 módulos" in texto
    assert "ponderado por kilos" in texto or "pondera por kilos" in texto


def test_la_matriz_remite_a_la_unidad_declarada_por_par():
    """La unidad no se explica bloque a bloque: se declara en cada fila de la tabla."""
    assert "unidad de análisis" in _plano(paneles.panel_matriz(_matriz())).lower()
    encontrados = analisis.hallazgos(_estado(matriz=_matriz(), packing=_packing()))
    assert "Unidad de análisis" in _fila_visible(encontrados)


def _fila_visible(encontrados) -> str:
    return _plano(paneles.tabla_solidos(encontrados))


def test_no_se_rompe_el_formato_de_los_decimales():
    """`replace('.', ',')` sobre la frase entera convertía los puntos finales."""
    for t in _texto(paneles.panel_matriz(_matriz())):
        assert " análisis," not in t, "un punto final se convirtió en coma"
        assert " total," not in t or "en total, " in t


def test_las_lecciones_van_junto_a_lo_que_explican():
    """Hablan de correlaciones y magnitudes, así que van tras los efectos y no tras el
    embudo, donde quedaban colgadas de un gráfico que no tiene nada que ver."""
    codigo = Path(pagina.__file__).read_text(encoding="utf-8")
    pos_lecciones = codigo.index("panel_lecciones")
    pos_embudo = codigo.index("panel_filtrado")
    assert pos_lecciones < pos_embudo, "las lecciones deben preceder al embudo"


# ── Recomendaciones de medición ──────────────────────────────────────────────


def test_el_cierre_dice_que_habria_que_medir_y_que_desbloquea_cada_cosa():
    """Una lista de carencias sin decir qué resuelve cada una no es una recomendación."""
    texto = _plano(paneles.panel_medicion())
    assert "Estaciones meteorológicas por fundo" in texto
    assert "Censo de bayas semanal" in texto
    assert "Ensayos con tratamientos asignados" in texto
    # Va en tabla: cada fila declara qué falta, cómo está hoy y qué desbloquea.
    assert "Qué desbloquea" in texto and "Cómo está hoy" in texto
    for titulo, hoy, beneficio in textos.MEDICION:
        assert hoy and beneficio, f"«{titulo}» sin estado actual o sin beneficio"


def test_el_cierre_reconoce_que_solo_un_ensayo_da_causalidad():
    """El manejo responde al estado del cultivo: sin asignación no hay causa."""
    texto = _plano(paneles.panel_medicion())
    assert "Único camino a afirmaciones causales" in texto
    assert "El manejo responde al estado del cultivo" in texto


# ── Peso visual ──────────────────────────────────────────────────────────────
#
# La página llegó a tener cuatro estilos de tarjeta distintos —bordes de color, fondos
# teñidos, grids de dos columnas, círculos numerados— y a partir de la mitad costaba
# seguirla. Estas pruebas fijan el límite para que no vuelva a crecer.


def _cajas(nodo, acc=None) -> list[str]:
    """Las `className` del árbol, para poder contar cuánto marco visual hay."""
    acc = [] if acc is None else acc
    if isinstance(nodo, (list, tuple)):
        for hijo in nodo:
            _cajas(hijo, acc)
    elif not isinstance(nodo, str):
        clase = getattr(nodo, "className", None)
        if clase:
            acc.append(str(clase))
        hijos = getattr(nodo, "children", None)
        if hijos is not None:
            _cajas(hijos, acc)
    return acc


def test_el_origen_de_los_datos_no_ocupa_una_alerta_entera():
    """Que todo esté en orden es el caso normal, y el caso normal es contexto, no aviso.

    Antes salía como una caja verde de cuatro líneas en las siete páginas del grupo,
    compitiendo con los datos que venían debajo.
    """
    import pandas as pd

    runs = pd.DataFrame(
        [
            {
                "run_id": 28,
                "tipo": "relations",
                "estado": "succeeded",
                "corte_datos": pd.Timestamp("2026-09-10"),
                "firma_snapshot": "be5fa0b02190abc",
                "cobertura": {},
                "advertencias": [],
            }
        ]
    )
    nodo = _comun.estado_fuente(_estado(runs=runs))
    texto = " ".join(_texto(nodo))
    assert "be5fa0b02190" in texto, "la huella sigue estando"
    assert "n.º 28" in texto
    # Lo que sobraba: la explicación de qué es una huella pasa a ser un tooltip.
    assert "partieron exactamente de los mismos datos" not in texto
    assert len(texto) < 120, f"la barra de origen se alargó otra vez: {texto!r}"
    assert not any("rounded-2xl" in c or "border p-4" in c for c in _cajas(nodo))


def test_un_fallo_de_origen_si_interrumpe():
    """Compactar el caso normal no puede volver silencioso el caso roto."""
    texto = " ".join(_texto(_comun.estado_fuente(_estado(error="sin conexión"))))
    assert "No se pudo leer el histórico" in texto


def test_las_listas_largas_no_se_dibujan_como_tarjetas_apiladas():
    """Lecciones y prioridades comparten un mismo estilo de lista, sin caja por entrada."""
    clases = _cajas(paneles.panel_lecciones())
    assert any("divide-y" in c for c in clases), "deben separarse por línea, no por caja"
    assert not any("rounded-xl border" in c for c in clases)
    assert not any("border-l-4" in c for c in clases), "el borde de color no aporta"


def test_las_opciones_que_compiten_por_presupuesto_van_en_tabla():
    """Cinco fichas apiladas no se comparan; una tabla sí, y para eso se abre esa sección."""
    texto = _plano(paneles.panel_medicion())
    for titulo, _, _ in textos.MEDICION:
        assert titulo in texto
    assert not any("divide-y" in c for c in _cajas(paneles.panel_medicion()))


def test_la_sintesis_de_apertura_no_es_una_alerta():
    """Es la entrada a la página; una franja verde compite con los KPI de arriba."""
    nodo = paneles.sintesis(analisis.hallazgos(_estado(matriz=_matriz())))
    assert not any("rounded-2xl" in c for c in _cajas(nodo))


# ── Estructura del módulo ────────────────────────────────────────────────────


def test_la_pagina_solo_compone_y_no_calcula():
    """La página tenía 1.146 líneas mezclando textos, cálculo y figuras.

    Se parte en `_relaciones/` para que una corrección de redacción no obligue a leer
    lógica. Lo que queda acá es el orden de las secciones.
    """
    codigo = Path(pagina.__file__).read_text(encoding="utf-8")
    assert len(codigo.splitlines()) < 250
    assert "go.Figure" not in codigo, "las figuras viven en _relaciones/graficos.py"
    assert "groupby" not in codigo, "el cálculo vive en _relaciones/analisis.py"


def test_las_piezas_no_se_importan_circularmente():
    """`paneles` usa `graficos` y `analisis`; ninguno de esos dos puede usar `paneles`."""
    for modulo in (analisis, formato, graficos):
        codigo = Path(modulo.__file__).read_text(encoding="utf-8")
        assert "import paneles" not in codigo
        assert "from .paneles" not in codigo


def test_el_parrafo_que_explicaba_la_estructura_ya_no_esta():
    """Quien abre la página quiere saber qué hay dentro, no cómo está organizada."""
    codigo = Path(pagina.__file__).read_text(encoding="utf-8")
    assert "Esta página tiene dos partes" not in codigo


def test_la_pagina_renderiza_sin_datos():
    """Debe abrir durante un bootstrap o una migración, no reventar."""
    assert pagina.layout() is not None


# ── Fuentes de datos ─────────────────────────────────────────────────────────


def _fuentes(fallback: bool = False, advertencias=None) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fuente": "excel" if fallback else "postgres",
                "corte_datos": pd.Timestamp("2026-09-10"),
                "firma": "37e2721f8b078abcdef",
                "source_snapshot_id": 101,
                "tablas": {"clima": 155588, "riego": 82742, "forecast": 48345, "lotes": 860},
                "cobertura": {"fallback": fallback},
                "advertencias": advertencias or [],
                "run_id": 23,
                "tipo": "backtest",
                "fin": pd.Timestamp("2026-08-19"),
            }
        ]
    )


def test_las_fuentes_se_exponen_con_su_conteo_y_su_significado():
    texto = " ".join(_texto(_comun.panel_fuentes(_estado(fuentes=_fuentes()))))
    assert "287.535 registros" in texto, "debe sumar todas las fuentes"
    assert "4 fuentes distintas" in texto
    assert "Estación meteorológica" in texto, "cada tabla con su nombre de negocio"
    assert "155.588" in texto
    assert "clima" not in texto.replace("climáticas", ""), "el nombre técnico no debe salir"
    assert "10/09/2026" in texto, "debe declarar el corte"
    assert "37e2721f8b07" in texto, "y la huella para poder reproducirlo"


def test_el_respaldo_excel_se_declara_y_no_se_disimula():
    texto = " ".join(_texto(_comun.panel_fuentes(_estado(fuentes=_fuentes(fallback=True)))))
    assert "Excel de respaldo" in texto
    assert "no pueden sostener una publicación oficial" in texto


def test_un_snapshot_de_archivos_no_rompe_el_panel_de_fuentes():
    fuentes = _fuentes(fallback=True)
    fuentes.at[0, "tablas"] = {"artifact": r"C:\respaldo\resultado.json"}

    texto = " ".join(_texto(_comun.panel_fuentes(_estado(fuentes=fuentes))))

    assert "no reportó el conteo" in texto


def test_las_advertencias_del_origen_se_muestran():
    fuentes = _fuentes(advertencias=["Faltan 3 semanas de clima en Aqu Anqa 2"])
    texto = " ".join(_texto(_comun.panel_fuentes(_estado(fuentes=fuentes))))
    assert "Faltan 3 semanas de clima" in texto


def test_el_panel_declara_snapshot_access_completo():
    control = pd.DataFrame(
        [
            {
                "alcance": "completo",
                "source_snapshot_id": 101,
                "snapshot_completo": True,
                "tablas_catalogo": 17,
                "tablas_extraidas": 17,
                "tablas_omitidas": 0,
            }
        ]
    )
    texto = " ".join(
        _texto(_comun.panel_fuentes(_estado(fuentes=_fuentes(), fuente_access_control=control)))
    )

    assert "Snapshot Access completo" in texto
    assert "17 de 17 tablas" in texto


def test_el_panel_alerta_snapshot_access_parcial():
    control = pd.DataFrame(
        [
            {
                "alcance": "parcial",
                "source_snapshot_id": 101,
                "snapshot_completo": False,
                "tablas_catalogo": 17,
                "tablas_extraidas": 1,
                "tablas_omitidas": 16,
            }
        ]
    )
    texto = " ".join(
        _texto(_comun.panel_fuentes(_estado(fuentes=_fuentes(), fuente_access_control=control)))
    )

    assert "Snapshot Access parcial" in texto
    assert "16 omitidas" in texto


def test_el_panel_no_inventa_estado_access_si_no_hay_control_vinculado():
    texto = " ".join(_texto(_comun.panel_fuentes(_estado(fuentes=_fuentes())))
    )

    assert "Estado del snapshot Access: no verificable" in texto


def test_el_panel_rechaza_control_access_de_otro_snapshot():
    control = pd.DataFrame(
        [{"source_snapshot_id": 999, "alcance": "completo", "snapshot_completo": True}]
    )
    texto = " ".join(
        _texto(_comun.panel_fuentes(_estado(fuentes=_fuentes(), fuente_access_control=control)))
    )

    assert "Estado del snapshot Access: no verificable" in texto


def test_sin_corrida_registrada_se_avisa():
    texto = " ".join(_texto(_comun.panel_fuentes(_estado())))
    assert "Todavía no hay una corrida registrada" in texto


@pytest.mark.parametrize(
    "clave",
    [
        "relaciones",
        "inferencia",
        "ablaciones",
        "permutacion",
        "shap",
        "fuentes",
        "matriz",
        "packing",
    ],
)
def test_el_estado_analitico_declara_las_claves_nuevas(clave):
    """Las páginas acceden por clave: si falta, el layout revienta con KeyError."""
    from servicios.analytics import estado_analitico

    assert clave in estado_analitico()


# ── Vocabulario ──────────────────────────────────────────────────────────────


def test_los_nombres_de_variable_se_traducen_cuando_son_valores():
    """En el barrido, `predictor` contiene `frutos_por_planta_muestra` como dato.

    `valor_legible` solo miraba `VALORES_ANALITICOS`, así que el nombre técnico llegaba a
    la pantalla dentro de la celda.
    """
    assert _comun.valor_legible("predictor", "frutos_por_planta_muestra") == "frutos por planta"
    assert _comun.valor_legible("respuesta", "peso_real_g") == "peso de la baya cosechada"
    assert _comun.valor_legible("variable", "frutos_por_planta") == "Frutos por planta"
    # Una columna que no contiene nombres de variable no se toca.
    assert _comun.valor_legible("lote", "frutos_por_planta") == "frutos_por_planta"


def test_las_variables_de_la_matriz_tienen_nombre_legible():
    """`agua_m3` y los censos nuevos llegaban sin traducir a la tabla."""
    from analitica.config import etiqueta

    for variable in (
        "agua_m3",
        "temp_min",
        "ramas_por_planta",
        "brotes_por_planta",
        "yemas_por_planta",
        "eto",
        "reposicion_pct",
        "calibre_medio_mm",
        "proporcion_descarte",
        "kg_ha_modulo",
    ):
        assert etiqueta(variable) != variable, f"{variable} sin etiqueta"


def test_todo_objetivo_del_mapa_tiene_nombre_y_grupo():
    """Una respuesta sin entrada en OBJETIVOS saldría con su nombre de columna en el eje."""
    for clave, (nombre, _, grupo) in textos.OBJETIVOS.items():
        assert nombre and "_" not in nombre, f"{clave} llegaría al eje sin traducir"
        assert grupo in textos.GRUPOS_OBJETIVO, f"{clave} apunta a un grupo inexistente"


def test_el_nombre_del_reporte_heredado_no_llega_a_la_pantalla():
    """R08 y R09 son nombres de consultas del Access original, no de modelos.

    Un agrónomo no tiene por qué saber que R09 era el reporte de forecast semanal.
    """
    from analitica.config import VALORES_ANALITICOS

    modelos = VALORES_ANALITICOS["modelo"]
    assert modelos["R09_publicado"] == "Proyección del equipo"
    assert not any(
        nombre.startswith("R09") or nombre.startswith("R08") for nombre in modelos.values()
    ), "ningún nombre visible debe empezar por el código del reporte"
