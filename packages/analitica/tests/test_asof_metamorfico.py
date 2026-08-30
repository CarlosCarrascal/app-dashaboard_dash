from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
from pandas.testing import assert_frame_equal

from analitica.proyeccion.asof import detectar_fuga, enriquecer_asof
from analitica.proyeccion.asof import lunes_semana as lunes_compat
from analitica.proyeccion.asof import ultimo_disponible as ultimo_compat
from analitica.proyeccion.compartido import lunes_semana, ultimo_disponible


def _datos(flores_futuras: int, temperatura_futura: float):
    fechas = pd.date_range("2026-01-01", "2026-01-20", freq="D")
    clima = pd.DataFrame(
        {
            "fecha_hora": fechas,
            "temp": [
                20.0 if f <= pd.Timestamp("2026-01-08") else temperatura_futura for f in fechas
            ],
            "temp_alta": 25.0,
            "temp_baja": 15.0,
            "humedad": 70.0,
            "rad_sol": 10.0,
            "et_mm": 3.0,
            "lluvia": 0.0,
        }
    )
    return SimpleNamespace(
        flores=pd.DataFrame(
            {
                "lote_id": [1, 1],
                "fecha": pd.to_datetime(["2026-01-02", "2026-01-15"]),
                "n_flores": [12, flores_futuras],
                "cuajo": [3, 99],
                "planta": [1, 1],
            }
        ),
        estados=pd.DataFrame(),
        bayas=pd.DataFrame(),
        poda=pd.DataFrame(),
        clima=clima,
    )


def test_cambiar_el_futuro_no_altera_variables_asof_de_una_emision():
    objetivos = pd.DataFrame(
        {
            "lote_id": [1],
            "campania": ["C2026"],
            "fecha_emision": pd.to_datetime(["2026-01-08"]),
            "fecha_objetivo": pd.to_datetime(["2026-01-19"]),
        }
    )
    original = enriquecer_asof(objetivos, _datos(100, 30.0))
    mutado = enriquecer_asof(objetivos, _datos(999_999, -10.0))
    assert_frame_equal(original, mutado)
    assert original.loc[0, "flores"] == 12
    assert detectar_fuga(original).empty


def test_un_censo_sin_todas_sus_columnas_no_tumba_el_panel():
    """Una evaluación puede no registrar yemas, o un lote no tener censo de ramas.

    El panel debe seguir armándose con lo que sí hay: la variable ausente simplemente no
    existe para esas filas, en vez de romper toda la corrida.
    """
    objetivos = pd.DataFrame(
        {
            "lote_id": [1],
            "campania": ["C2026"],
            "fecha_emision": pd.to_datetime(["2026-01-08"]),
            "fecha_objetivo": pd.to_datetime(["2026-01-19"]),
        }
    )
    # El fixture no trae yemas, ni brotes, ni ramas.
    panel = enriquecer_asof(objetivos, _datos(100, 30.0))
    assert len(panel) == 1
    assert panel.loc[0, "flores"] == 12
    assert "yemas_por_planta" not in panel
    assert "brotes_por_planta" not in panel


def test_censos_con_campania_no_se_mezclan_entre_ciclos():
    objetivos = pd.DataFrame(
        {
            "lote_id": [1],
            "campania": ["C2026"],
            "fecha_emision": pd.to_datetime(["2026-01-08"]),
        }
    )
    datos = _datos(100, 30.0)
    datos.flores = pd.DataFrame(
        {
            "campania": ["C2025", "C2026"],
            "lote_id": [1, 1],
            "fecha": pd.to_datetime(["2026-01-02", "2026-01-03"]),
            "n_flores": [999, 12],
            "cuajo": [99, 3],
            "planta": [1, 1],
        }
    )

    panel = enriquecer_asof(objetivos, datos)

    assert panel.loc[0, "flores"] == 12
    assert panel.loc[0, "cuajo"] == 3


def test_los_censos_del_arranque_del_ciclo_llegan_al_panel():
    """Ramas, brotes y yemas se levantan en campo y hasta ahora no entraban a ningún cálculo."""
    from analitica.proyeccion.asof import agregar_fenologia

    datos = _datos(100, 30.0)
    datos.flores["yemas_abiertas"] = [4, 20]
    datos.flores["yemas_por_abrir"] = [8, 30]
    datos.brotes = pd.DataFrame(
        {
            "lote_id": [1, 1],
            "fecha": pd.to_datetime(["2026-01-02", "2026-01-15"]),
            "planta": [1, 1],
            "brotes": [40, 999],
        }
    )
    datos.ramas = pd.DataFrame(
        {
            "lote_id": [1],
            "fecha": pd.to_datetime(["2026-01-02"]),
            "planta": [1],
            "ramas_menor5": [6],
            "ramas_mayor5": [4],
            "nro_rama": [10],
            "diametro": [7.5],
        }
    )
    agregados = agregar_fenologia(datos)
    assert agregados["brotes"].brotes_por_planta.iloc[0] == 40
    assert agregados["ramas"].proporcion_ramas_gruesas.iloc[0] == 0.4
    flores = agregados["flores"]
    assert flores.yemas_por_planta.iloc[0] == 12
    assert abs(flores.proporcion_yemas_abiertas.iloc[0] - 4 / 12) < 1e-9

    objetivos = pd.DataFrame(
        {
            "lote_id": [1],
            "campania": ["C2026"],
            "fecha_emision": pd.to_datetime(["2026-01-08"]),
            "fecha_objetivo": pd.to_datetime(["2026-01-19"]),
        }
    )
    panel = enriquecer_asof(objetivos, datos)
    # El brote de 999 es del 15, posterior a la emisión: no puede haber entrado.
    assert panel.loc[0, "brotes_por_planta"] == 40
    assert panel.loc[0, "ramas_por_planta"] == 10
    assert detectar_fuga(panel).empty


def test_asof_conserva_aliases_temporales_en_la_fachada():
    assert lunes_compat is lunes_semana
    assert ultimo_compat is ultimo_disponible
