"""Matriz exploratoria: cruzar todo con todo sin que el azar se cuele como hallazgo.

Con cientos de combinaciones, el 5 % saldría «significativo» aunque no existiera ninguna
relación. Estas pruebas fijan las dos correcciones que lo evitan y el criterio de que un
par no es un hallazgo por cada desfase en que aparece.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.dominio.evaluacion.relaciones_partes.estadistica import (
    ORDEN_CICLO,
    PREDICTORES_EXTERNOS,
    RESPUESTAS_MATRIZ,
    _pares_matriz,
    evaluar_matriz_relaciones,
)
from analitica.dominio.evaluacion.relaciones_partes.evidencia import (
    hallazgos_matriz,
    resumen_matriz,
)


def _panel(semillas: int = 0, n_lotes: int = 12, n_semanas: int = 30) -> pd.DataFrame:
    """Panel lote-semana con una relación real sembrada y el resto puro ruido."""
    rng = np.random.default_rng(semillas)
    filas = []
    for lote in range(n_lotes):
        for semana in range(n_semanas):
            fecha = pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=semana)
            temp = 18 + 6 * np.sin(2 * np.pi * semana / 52) + rng.normal(0, 1)
            filas.append(
                {
                    "lote_id": lote,
                    "modulo": f"M{lote % 4}",
                    "fecha_semana": fecha,
                    "temp_max": temp,
                    "temp_min": temp - 8 + rng.normal(0, 0.5),
                    "humedad": rng.normal(70, 5),
                    "dpv_kpa": rng.normal(1.2, 0.2),
                    "eto": rng.normal(4, 0.5),
                    "radiacion": rng.normal(20, 3),
                    "lluvia": rng.normal(0, 0.1),
                    "gdd_4_4": max(0.0, 7 * (temp - 4.4)),
                    "lamina_mm": rng.normal(12, 3),
                    "agua_m3": rng.normal(300, 40),
                    "reposicion_pct": rng.normal(90, 8),
                    "ramas_por_planta": rng.normal(10, 2),
                    "proporcion_ramas_gruesas": rng.uniform(0.3, 0.6),
                    "diametro_rama_mm": rng.normal(7, 1),
                    "brotes_por_planta": rng.normal(60, 12),
                    "yemas_por_planta": rng.normal(30, 6),
                    "proporcion_yemas_abiertas": rng.uniform(0.2, 0.8),
                    "flores_por_planta_muestra": rng.normal(50, 10),
                    "tasa_cuajo_observada": rng.uniform(0.2, 0.8),
                    "frutos_por_planta_muestra": rng.normal(55, 10),
                    "indice_estado": rng.uniform(1, 5),
                    "prop_e1": rng.uniform(0, 0.4),
                    "prop_e5": rng.uniform(0, 0.4),
                    "diametro_baya_mm": rng.normal(12, 1.5),
                    "peso_real_g": rng.normal(3.4, 0.4),
                    "kg_ha": rng.normal(1200, 200),
                }
            )
    return pd.DataFrame(filas)


def test_solo_se_cruza_hacia_adelante_en_el_ciclo():
    """Preguntar si el peso de la baya explica las ramas es preguntar si el futuro causa
    el pasado. Las externas sí se cruzan contra todo: el clima actúa en cualquier momento."""
    pares = _pares_matriz()
    for predictor, respuesta, tipo in pares:
        if tipo != "cultivo":
            continue
        assert ORDEN_CICLO[predictor] < ORDEN_CICLO[respuesta], (
            f"{predictor} → {respuesta} invierte el orden del ciclo"
        )
    externas = {p for p, _, t in pares if t == "externa"}
    assert externas == set(PREDICTORES_EXTERNOS)
    assert {r for _, r, _ in pares} <= set(RESPUESTAS_MATRIZ)


def test_una_variable_no_se_cruza_consigo_misma():
    assert all(p != r for p, r, _ in _pares_matriz())


def test_la_correccion_penaliza_haber_elegido_el_mejor_desfase():
    """Con nueve desfases probados, el p del mejor ya no significa lo que dice."""
    matriz = evaluar_matriz_relaciones(_panel(), minimo_n=25)
    assert not matriz.empty
    assert (matriz.p_seleccion_desfase >= matriz.p_pearson - 1e-12).all()
    varios = matriz[matriz.desfases_probados > 1]
    assert not varios.empty
    assert (varios.p_seleccion_desfase > varios.p_pearson).any()


def test_el_ajuste_global_es_mas_exigente_que_el_valor_p_crudo():
    matriz = evaluar_matriz_relaciones(_panel(), minimo_n=25)
    assert (matriz.p_ajustado_bh >= matriz.p_seleccion_desfase - 1e-12).all()
    assert (matriz.p_ajustado_bh <= 1.0).all()


def test_con_datos_de_puro_ruido_casi_nada_sobrevive():
    """La prueba que de verdad importa: sin señal real, la matriz no debe inventar hallazgos.

    Se admite algún superviviente porque el panel tiene estacionalidad compartida, pero
    debe quedar muy por debajo de lo que pasaría sin corregir.
    """
    matriz = evaluar_matriz_relaciones(_panel(semillas=7), minimo_n=25)
    resumen = resumen_matriz(matriz)
    assert resumen["sin_corregir"] > resumen["pruebas_que_sobreviven"], (
        "la corrección tiene que descartar algo"
    )
    hallazgos = hallazgos_matriz(matriz)
    assert len(hallazgos) < 0.15 * resumen["pares"], (
        f"sobreviven {len(hallazgos)} de {resumen['pares']} pares con datos de ruido"
    )


def test_el_resumen_declara_cuantos_se_esperarian_por_azar():
    """Sin esa cifra no hay forma de juzgar si el número de hallazgos dice algo."""
    matriz = evaluar_matriz_relaciones(_panel(), minimo_n=25)
    resumen = resumen_matriz(matriz)
    assert resumen["esperados_por_azar"] == round(0.05 * resumen["pruebas"], 1)
    assert resumen["pares_que_sobreviven"] <= resumen["pruebas_que_sobreviven"]


def test_un_par_es_un_hallazgo_aunque_aparezca_en_varios_desfases():
    """`gdd → kg/ha` a 1, 3 y 4 semanas es el mismo hallazgo visto tres veces."""
    matriz = evaluar_matriz_relaciones(_panel(), minimo_n=25)
    hallazgos = hallazgos_matriz(matriz)
    if hallazgos.empty:
        return
    assert not hallazgos.duplicated(["predictor", "respuesta"]).any()
    assert (hallazgos.desfases_que_sobreviven >= 1).all()
    assert (hallazgos.desfase_min <= hallazgos.desfase_max).all()


def test_el_placebo_descarta_lo_que_explica_el_calendario():
    matriz = evaluar_matriz_relaciones(_panel(), minimo_n=25)
    descartados = matriz[matriz.placebo_supera_estimacion]
    assert not descartados.sobrevive.any(), (
        "una relación que una serie futura explica igual de bien no puede sobrevivir"
    )


def test_se_exige_un_minimo_de_semanas_distintas():
    """Muchas filas de pocas semanas no son muchas observaciones independientes."""
    matriz = evaluar_matriz_relaciones(_panel(n_semanas=40), minimo_n=25, minimo_semanas=30)
    if not matriz.empty:
        assert (matriz.n_efectivo >= 30).all()


def test_un_panel_vacio_no_rompe_la_matriz():
    assert evaluar_matriz_relaciones(pd.DataFrame()).empty
    assert hallazgos_matriz(pd.DataFrame()).empty
    assert resumen_matriz(pd.DataFrame()) == {}
