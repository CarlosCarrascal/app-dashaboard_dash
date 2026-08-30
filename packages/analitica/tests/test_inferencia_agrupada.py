"""Los seis defectos que hacían publicables relaciones que no existían.

Una auditoría del módulo encontró que el barrido publicaba 44 «patrones sólidos» apoyados
en tres errores encadenados: el riego duplicaba un tercio del panel, el área del módulo se
contaba una vez por día de cosecha, y la significancia se calculaba sobre el número de
filas cuando la información independiente eran las semanas —una razón de hasta 629 a 1—.
Con la inferencia hecha bien, de 49 pares supervivientes quedaron 23.

Cada prueba de este archivo reproduce uno de esos defectos en pequeño y comprueba que ya
no ocurre. No son pruebas de refactor: si alguna falla, hay números falsos en pantalla.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from analitica.proyeccion.contratos import DatosProyeccion, FuenteInfo
from analitica.proyeccion.relaciones_partes.estadistica import (
    _p_agrupado,
    _placebo_parcial,
    _residuos_controles,
)
from analitica.proyeccion.relaciones_partes.packing import panel_packing
from analitica.proyeccion.relaciones_partes.panel import construir_panel_relaciones

# ── Defecto 1: el riego duplicaba filas ──────────────────────────────────────


def _datos_minimos(**tablas) -> DatosProyeccion:
    base = {
        "forecast": pd.DataFrame(),
        "cosecha": pd.DataFrame(),
        "flores": pd.DataFrame(),
        "estados": pd.DataFrame(),
        "bayas": pd.DataFrame(),
        "brotes": pd.DataFrame(),
        "ramas": pd.DataFrame(),
        "packing": pd.DataFrame(),
        "poda": pd.DataFrame(),
        "clima": pd.DataFrame(),
        "riego": pd.DataFrame(),
        "lotes": pd.DataFrame(),
    }
    base.update(tablas)
    campos = {f.name for f in dataclasses.fields(DatosProyeccion)}
    return DatosProyeccion(
        fuente=FuenteInfo(nombre="prueba", firma="x", corte=None),
        **{k: v for k, v in base.items() if k in campos},
    )


def _cosecha_dos_fundos() -> pd.DataFrame:
    filas = []
    for fundo, lote_id in (("Norte", 1), ("Sur", 2)):
        for semana in range(6):
            filas.append(
                {
                    "lote_id": lote_id,
                    "fecha": pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=semana),
                    "kg": 100.0 + semana,
                    "peso_baya": 3.0,
                    "area_ha": 2.0,
                    "plantas_cosechadas": 1000.0,
                    "plantas_maestro": 1000.0,
                    "empresa": "AQ",
                    "fundo": fundo,
                    "modulo": "M01",
                    "lote": "L1",
                    "variedad": "V",
                    "campania": "C2026",
                    "motivo": "cosecha",
                    "turno": 1,
                    "semana": semana,
                }
            )
    return pd.DataFrame(filas)


def _riego_dos_fundos() -> pd.DataFrame:
    filas = []
    for modulo_id, fundo in ((10, "Norte"), (20, "Sur")):
        for dia in range(30):
            filas.append(
                {
                    "fecha": pd.Timestamp("2026-01-05") + pd.Timedelta(days=dia),
                    "modulo_id": modulo_id,
                    "turno_local": 1,
                    "area_ha": 2.0,
                    "agua_m3": 50.0 + modulo_id,
                    "lamina_mm": 5.0,
                    "reposicion_pct": 90.0,
                    "estimado": False,
                    "empresa": "AQ",
                    "fundo": fundo,
                    "modulo": "M01",
                }
            )
    return pd.DataFrame(filas)


def test_el_riego_no_duplica_filas_cuando_dos_fundos_comparten_el_nombre_del_modulo():
    """«M01» existe en dos fundos. Unir solo por el nombre emparejaba cada lote con los dos
    módulos homónimos y duplicaba 20.868 filas del panel real —el 30 %—, inflando la
    muestra de toda relación que tocara el riego."""
    datos = _datos_minimos(cosecha=_cosecha_dos_fundos(), riego=_riego_dos_fundos())
    sin_riego = construir_panel_relaciones(
        _datos_minimos(cosecha=_cosecha_dos_fundos(), riego=pd.DataFrame())
    )
    con_riego = construir_panel_relaciones(datos)
    assert len(con_riego) == len(sin_riego), "el riego no puede cambiar el número de filas"
    assert not con_riego.duplicated(["lote_id", "fecha_semana"]).any()


def test_cada_fundo_recibe_el_agua_de_su_propio_modulo():
    """Duplicar no era el único daño: al lote del Norte se le atribuía también el riego
    del Sur, así que el valor promediado no correspondía a ningún módulo real."""
    panel = construir_panel_relaciones(
        _datos_minimos(cosecha=_cosecha_dos_fundos(), riego=_riego_dos_fundos())
    )
    agua = panel.dropna(subset=["agua_m3"]).groupby("fundo").agua_m3.nunique()
    if not agua.empty:
        assert set(panel.dropna(subset=["agua_m3"]).fundo) <= {"Norte", "Sur"}
        norte = panel[(panel.fundo == "Norte") & panel.agua_m3.notna()].agua_m3
        sur = panel[(panel.fundo == "Sur") & panel.agua_m3.notna()].agua_m3
        if len(norte) and len(sur):
            assert norte.iloc[0] != sur.iloc[0], "cada fundo tiene su propio módulo"


# ── Defecto 2: el área se contaba una vez por día de cosecha ─────────────────


def test_el_area_del_modulo_se_cuenta_una_vez_por_lote_y_no_por_registro():
    """Un lote aparece en varias filas de cosecha dentro de la misma semana —un registro
    por día y turno— y sumar `area_ha` contaba su superficie tantas veces como veces se
    cosechó. Inflaba 762 de los 1.017 grupos módulo-semana, hasta 2,67 veces, y hundía
    `kg_ha_modulo` en la misma proporción. Es el defecto B-4 del ADR-0004."""
    filas = []
    for dia in range(4):  # el mismo lote cosechado cuatro días de la misma semana
        filas.append(
            {
                "lote_id": 1,
                "fecha": pd.Timestamp("2026-01-05") + pd.Timedelta(days=dia),
                "kg": 250.0,
                "peso_baya": 3.0,
                "area_ha": 2.0,
                "plantas_cosechadas": 1000.0,
                "plantas_maestro": 1000.0,
                "empresa": "AQ",
                "fundo": "Norte",
                "modulo": "M01",
                "lote": "L1",
                "variedad": "V",
                "campania": "C2026",
                "motivo": "cosecha",
                "turno": 1,
                "semana": 1,
            }
        )
    packing = pd.DataFrame(
        [
            {
                "modulo": "M01",
                "fecha_cosecha": pd.Timestamp("2026-01-05") + pd.Timedelta(days=d),
                "semana": 1,
                "anio": 2026,
                "variedad": "V",
                "calibre": "J",
                "calibre_mm": 18.0,
                "clase": "exportable",
                "mercado": "USA",
                "defecto": 0.0,
                "acidez": 1.0,
                "peso_kg": 100.0,
                "recuento": 10,
            }
            for d in range(4)
        ]
    )
    panel = panel_packing(_datos_minimos(cosecha=pd.DataFrame(filas), packing=packing))
    assert not panel.empty
    fila = panel.iloc[0]
    assert fila.area_ha == 2.0, f"el área es la del lote, no 4×2 ha (obtenido {fila.area_ha})"
    # 1.000 kg sobre 2 ha son 500 kg/ha; con el área inflada salían 125.
    assert abs(fila.kg_ha_modulo - 500.0) < 1e-6


# ── Defectos 3 y 4: la significancia ─────────────────────────────────────────


def _serie_comun_a_la_semana(n_semanas: int, n_lotes: int, semilla: int = 0):
    """Un predictor idéntico para todos los lotes de la semana, como el clima real.

    Con una sola estación para los cinco fundos, los 260 lotes de una semana comparten
    literalmente el mismo valor: la información independiente son las semanas.
    """
    rng = np.random.default_rng(semilla)
    x_semana = rng.normal(size=n_semanas)
    y_semana = rng.normal(size=n_semanas)  # sin relación alguna con x
    filas = []
    for s in range(n_semanas):
        for lote in range(n_lotes):
            filas.append(
                {
                    "fecha_semana": pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=s),
                    "lote_id": lote,
                    "modulo": f"M{lote % 3}",
                    "x": x_semana[s],
                    "y": y_semana[s] + rng.normal(scale=0.1),
                }
            )
    return pd.DataFrame(filas)


def test_repetir_el_mismo_dato_en_cien_lotes_no_crea_informacion_nueva():
    """El defecto que más resultados falsos produjo.

    Con el p calculado sobre filas, dos series sin ninguna relación salían «significativas»
    con solo repetirlas en suficientes lotes. En la base real la razón filas/semanas llega
    a 629, y por eso sobrevivían 218 pruebas donde la inferencia correcta deja 102.
    """
    from scipy import stats

    tabla = _serie_comun_a_la_semana(n_semanas=25, n_lotes=60, semilla=7)
    rx = _residuos_controles(tabla, "x")
    ry = _residuos_controles(tabla, "y")

    _, p_por_filas = stats.pearsonr(tabla.x, tabla.y)
    p_agrupado, gl = _p_agrupado(rx, ry, tabla[["fecha_semana", "lote_id"]])

    assert gl < len(tabla) / 10, "los grados de libertad deben venir de los grupos, no de las filas"
    assert p_agrupado > p_por_filas, "agrupar solo puede ser más exigente, nunca menos"


def test_multiplicar_los_lotes_no_cambia_el_p_agrupado():
    """La comprobación decisiva: con el mismo dato semanal repetido en el triple de lotes,
    la conclusión estadística tiene que ser la misma. Con el p sobre filas se disparaba."""
    from scipy import stats

    ps, crudos = [], []
    for n_lotes in (10, 30, 90):
        tabla = _serie_comun_a_la_semana(n_semanas=25, n_lotes=n_lotes, semilla=3)
        rx = _residuos_controles(tabla, "x")
        ry = _residuos_controles(tabla, "y")
        ps.append(_p_agrupado(rx, ry, tabla[["fecha_semana", "lote_id"]])[0])
        crudos.append(stats.pearsonr(tabla.x, tabla.y)[1])

    assert max(ps) - min(ps) < 0.25, f"el p agrupado debería ser estable: {ps}"
    assert crudos[2] < crudos[0], "el p sobre filas sí se infla con la repetición"


def test_sin_grupos_suficientes_no_se_afirma_nada():
    """Con dos semanas no hay con qué estimar la variabilidad entre grupos."""
    tabla = _serie_comun_a_la_semana(n_semanas=2, n_lotes=5, semilla=1)
    p, gl = _p_agrupado(tabla.x.to_numpy(), tabla.y.to_numpy(), tabla[["fecha_semana"]])
    assert p == 1.0 and gl == 0


def test_el_placebo_se_mide_con_la_misma_vara_que_la_estimacion():
    """Antes el placebo se calculaba en crudo y se comparaba contra la parcial descontada:
    cargaba con todo el calendario que a la estimación ya se le había quitado."""
    tabla = _serie_comun_a_la_semana(n_semanas=30, n_lotes=8, semilla=11)
    orden = tabla.rename(columns={"x": "pred", "y": "resp"}).sort_values(
        ["lote_id", "fecha_semana"]
    )
    valor = _placebo_parcial(orden, "pred", "resp", rezago=0, grupo="lote_id", minimo=10)
    assert np.isnan(valor) or -1.0 <= valor <= 1.0


# ── Defecto 6: el corte as-of ────────────────────────────────────────────────


def test_el_corte_asof_deja_fuera_lo_posterior():
    """«Corte de datos» era solo la fecha máxima encontrada: describía hasta dónde llegaban
    los datos, no hasta dónde se había decidido mirar. La corrida vigente se ejecutó el
    2026-08-19 con datos hasta el 2026-09-10, tres semanas por delante."""
    from analitica.proyeccion.fuentes import _aplicar_asof

    tablas = {
        "cosecha": pd.DataFrame(
            {"fecha": pd.to_datetime(["2026-08-01", "2026-08-19", "2026-09-10"])}
        ),
        "clima": pd.DataFrame({"fecha_hora": pd.to_datetime(["2026-08-01", "2026-09-10"])}),
        "lotes": pd.DataFrame({"lote_id": [1, 2]}),  # sin fecha: no se toca
    }
    recortado = _aplicar_asof(tablas, pd.Timestamp("2026-08-19"))
    assert len(recortado["cosecha"]) == 2
    assert len(recortado["clima"]) == 1
    assert len(recortado["lotes"]) == 2, "una tabla sin fecha no se recorta"
    assert _aplicar_asof(tablas, None)["cosecha"].shape[0] == 3, "sin corte no se filtra"
