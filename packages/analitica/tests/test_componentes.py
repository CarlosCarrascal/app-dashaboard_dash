"""La familia que estima frutos por planta y peso de baya, y los compone en kilos.

Lo que estas pruebas protegen, por orden de gravedad si se rompiera:

1. que no entre información posterior a la fecha de emisión;
2. que el kg publicado sea exactamente el producto de las tres piezas que muestra;
3. que las plantas salgan del maestro y no de la cosecha, que solo se conoce después.
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from analitica.proyeccion.componentes import (
    FEATURES_FRUTOS,
    FEATURES_PESO,
    FEATURES_PROHIBIDAS,
    NOMBRE_MODELO,
    challengers_componentes,
)
from analitica.proyeccion.modelos import _elegir_anidado_etiquetado

# Panel mínimo que aún deja varias emisiones entrenando: con 8 lotes y 2 horizontes son 16
# filas por semana, así que el umbral de entrenamiento se alcanza hacia la semana 7 y
# quedan emisiones suficientes para comprobar el comportamiento sin pagar el coste de
# entrenar 6 candidatos por objetivo en decenas de emisiones.
SEMANAS = 14
LOTES = 8


def _panel(
    *,
    semillas_futuras: float = 1.0,
    plantas_maestro: int = 5000,
    plantas_cosechadas: int = 2000,
    n_semanas: int = SEMANAS,
) -> pd.DataFrame:
    """Rejilla lote × emisión × objetivo con el mismo contrato que produce `preparar_r09`.

    `semillas_futuras` altera únicamente lo que ocurre después del corte; sirve para el
    test metamórfico. El corte está en la semana 10.
    """
    filas = []
    corte = pd.Timestamp("2026-01-05") + pd.to_timedelta(10, unit="W")
    for semana in range(n_semanas):
        objetivo = pd.Timestamp("2026-01-05") + pd.to_timedelta(semana, unit="W")
        for lote in range(LOTES):
            for horizonte in (1, 3):
                emision = objetivo - pd.to_timedelta(horizonte, unit="W")
                futuro = objetivo >= corte
                escala = semillas_futuras if futuro else 1.0
                frutos = (40 + 3 * (semana % 5) + lote) * escala
                peso = (3.0 + 0.05 * (semana % 7)) * escala
                real = plantas_cosechadas * frutos * peso / 1000
                filas.append(
                    {
                        "campania": "C2026",
                        "lote_id": lote,
                        "lote": f"L{lote:02d}",
                        "modulo": f"M{lote % 3}",
                        "fundo": f"F{lote % 2}",
                        "empresa": "E1",
                        "fecha_emision": emision,
                        "fecha_objetivo": objetivo,
                        "horizonte_semanas": horizonte,
                        "banda_horizonte": "operativo" if horizonte <= 2 else "planificacion",
                        "version_fuente": "S01",
                        "modelo": "R09_publicado",
                        "p50_kg": real * 1.1,
                        "p10_kg": np.nan,
                        "p90_kg": np.nan,
                        "real_kg": real,
                        "plantas": plantas_maestro,
                        "plantas_reales": plantas_cosechadas,
                        "frutos_por_planta": frutos * 0.9,
                        "peso_baya_g": peso * 0.95,
                        "peso_real_g": peso,
                        "kg_componentes": real,
                        "dias_desde_poda": 30 + 7 * semana,
                    }
                )
    tabla = pd.DataFrame(filas)
    tabla["frutos_reales_por_planta"] = (
        tabla.real_kg * 1000 / (tabla.plantas_reales * tabla.peso_real_g)
    )
    tabla["frutos_reales_por_planta_catalogo"] = (
        tabla.real_kg * 1000 / (tabla.plantas * tabla.peso_real_g)
    )
    return tabla


def test_la_identidad_reconstruye_el_kg_publicado():
    salida = challengers_componentes(_panel(), minimo_entrenamiento=100)
    assert not salida.empty
    producto = salida.plantas * salida.frutos_por_planta * salida.peso_baya_g / 1000
    assert float((producto - salida.p50_kg).abs().max()) < 1e-9


def test_cambiar_el_futuro_no_altera_las_predicciones_ya_emitidas():
    """El test que de verdad protege contra la fuga temporal.

    Se construyen dos paneles idénticos hasta el corte y radicalmente distintos después. Si
    alguna predicción anterior al corte cambia, es que el entrenamiento vio el futuro.
    """
    corte = pd.Timestamp("2026-01-05") + pd.to_timedelta(10, unit="W")
    claves = ["lote_id", "fecha_emision", "fecha_objetivo"]

    def emitidas(panel):
        salida = challengers_componentes(panel, minimo_entrenamiento=100)
        previas = salida[salida.fecha_objetivo < corte]
        return previas.sort_values(claves).reset_index(drop=True)[
            [*claves, "p50_kg", "frutos_por_planta", "peso_baya_g"]
        ]

    original = emitidas(_panel(semillas_futuras=1.0))
    alterado = emitidas(_panel(semillas_futuras=25.0))
    assert not original.empty
    assert_frame_equal(original, alterado)


def test_sin_historia_resuelta_no_emite_ninguna_fila():
    """Es preferible no emitir a emitir un número que no se sostiene."""
    assert challengers_componentes(_panel(n_semanas=3), minimo_entrenamiento=300).empty


def test_las_plantas_salen_del_maestro_y_no_de_la_cosecha():
    salida = challengers_componentes(
        _panel(plantas_maestro=5000, plantas_cosechadas=2000), minimo_entrenamiento=100
    )
    assert set(salida.plantas.unique()) == {5000}
    assert set(salida.base_plantas.unique()) == {"catalogo"}


def test_las_features_no_incluyen_el_resultado_que_se_predice():
    assert not FEATURES_PROHIBIDAS & set(FEATURES_FRUTOS)
    assert not FEATURES_PROHIBIDAS & set(FEATURES_PESO)
    assert "p50_kg" not in FEATURES_FRUTOS, "con el kg base dentro sería otra corrección residual"


def test_la_seleccion_interna_es_temporal_y_no_aleatoria():
    codigo = inspect.getsource(_elegir_anidado_etiquetado)
    assert "KFold" not in codigo
    assert "train_test_split" not in codigo
    assert "shuffle" not in codigo
    assert "fecha_objetivo" in codigo


def test_los_intervalos_quedan_ordenados():
    salida = challengers_componentes(_panel(), minimo_entrenamiento=100)
    assert (salida.p10_kg <= salida.p50_kg).all()
    assert (salida.p50_kg <= salida.p90_kg).all()


def test_hereda_el_calendario_y_no_inventa_kilos_donde_r09_no_espera_cosecha():
    panel = _panel()
    sin_cosecha = panel.fecha_objetivo == panel.fecha_objetivo.max()
    panel.loc[sin_cosecha, "p50_kg"] = 0.0
    salida = challengers_componentes(panel, minimo_entrenamiento=100)
    afectadas = salida[salida.fecha_objetivo == panel.fecha_objetivo.max()]
    if not afectadas.empty:
        assert (afectadas.p50_kg == 0).all()
        assert (afectadas.filas_con_gate_cero > 0).all()


def test_declara_de_donde_salen_sus_supuestos():
    salida = challengers_componentes(_panel(), minimo_entrenamiento=100)
    supuesto = salida.supuesto_modelo.iloc[0]
    assert "maestro del lote" in supuesto, "debe decir sobre qué base están los frutos"
    assert "calendario" in supuesto, "debe declarar que hereda el calendario de cosecha"
    assert salida.modelo.unique().tolist() == [NOMBRE_MODELO]
