"""Aceptación de la mesa operativa de Proyección."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from dash import dcc

import app as dashboard_app  # noqa: F401,E402
from pages.analitica import proyeccion as pagina
from pages.analitica import proyeccion_callbacks as callbacks_proyeccion
from pages.analitica.proyeccion_charts import (
    curva_operativa_actual,
    curvas_por_fundo,
    figura_nowcast_cierre,
    historico_y_desviacion,
)
from pages.analitica.proyeccion_domain import (
    FUNDOS_OPERATIVOS,
    HORIZONTE_CAMPANIA,
    HORIZONTE_SEMANAS,
    MODELO_OPERATIVO_ACTUAL,
    SERIES_HISTORICAS,
    agrupar_replay_historico,
    alinear_replay_con_real_comun,
    aplicar_horizonte,
    enriquecer,
    etiqueta_semana,
    filas_grid,
    filtrar_ubicacion,
    inicio_ventana_operativa,
    limitar_ventana_semanal,
    metricas_replay_historico,
    normalizar_fundo,
    plan_semanal,
    preparar_real,
    resumen_fundos,
    vista_descarga,
    vista_trazabilidad,
)
from pages.analitica.proyeccion_views import panel_nowcast_cierre


def _proyeccion() -> pd.DataFrame:
    filas = []
    mapeo = [
        ("Aqu Anqa 1", "M01", "L001"),
        ("Aqu Anqa 4", "M04", "L004"),
        ("Aqu Anqa 3", "M03", "L003"),
        ("Aqu Anqa 5", "M05", "L005"),
        ("Aqu Anqa 2", "M02", "L002"),
    ]
    for semana, fecha in enumerate(pd.date_range("2026-08-24", periods=8, freq="7D"), 1):
        for indice, (fundo, modulo, lote) in enumerate(mapeo, 1):
            filas.append(
                {
                    "run_id": 17,
                    "modelo": "ModeloOperativoActual_v1",
                    "version_fuente": "ProySemanal_34",
                    "campania": "C2026",
                    "empresa": "Aqu Anqa",
                    "fundo": fundo,
                    "modulo": modulo,
                    "lote": lote,
                    "lote_id": indice,
                    "fecha_emision": pd.Timestamp("2026-08-17"),
                    "fecha_objetivo": fecha,
                    "horizonte_semanas": semana,
                    "p50_kg": float(indice * semana * 100),
                    "plantas": 1000.0,
                    "frutos_por_planta": 20.0,
                    "peso_baya_g": 3.0,
                    "componentes": json.dumps(
                        {
                            "pasada": semana,
                            "fecha_inicio": str(fecha - pd.Timedelta(days=7)),
                            "fuente_libro": f"ProySemanal_34_{fundo}.xlsm",
                            "fuente_hash": f"hash-{fundo}",
                        }
                    ),
                    "generado_en": pd.Timestamp("2026-08-18 08:00"),
                }
            )
    return pd.DataFrame(filas)


@pytest.fixture
def tabla() -> pd.DataFrame:
    return enriquecer(_proyeccion())


def _componentes(nodo):
    yield nodo
    hijos = getattr(nodo, "children", None)
    if hijos is None:
        return
    if not isinstance(hijos, (list, tuple)):
        hijos = [hijos]
    for hijo in hijos:
        if hasattr(hijo, "children") or hasattr(hijo, "id"):
            yield from _componentes(hijo)


def _texto(nodo) -> list[str]:
    if isinstance(nodo, str):
        return [nodo]
    hijos = getattr(nodo, "children", None)
    if hijos is None:
        return []
    if not isinstance(hijos, (list, tuple)):
        hijos = [hijos]
    salida = []
    for hijo in hijos:
        salida.extend(_texto(hijo) if not isinstance(hijo, str) else [hijo])
    return salida


def test_los_cinco_codigos_se_normalizan_en_cuatro_fundos():
    assert normalizar_fundo("Aqu Anqa 1") == "Arena"
    assert normalizar_fundo("Aqu Anqa 2") == "Quri"
    assert normalizar_fundo("Aqu Anqa 3") == "Kawsay"
    assert normalizar_fundo("Aqu Anqa 4") == "Ayllu"
    assert normalizar_fundo("Aqu Anqa 5") == "Kawsay"


def test_los_cuatro_fundos_aparecen_una_sola_vez(tabla):
    resumen = resumen_fundos(tabla)
    assert tuple(resumen.fundo) == FUNDOS_OPERATIVOS
    assert resumen.fundo.is_unique


def test_la_vista_operativa_usa_la_macro_y_no_expone_r09_como_modelo():
    assert MODELO_OPERATIVO_ACTUAL == "ModeloOperativoActual_v1"
    assert SERIES_HISTORICAS["R09_publicado"] == "R09 publicado · referencia"


def test_kawsay_concilia_aqu_anqa_3_y_5(tabla):
    primera = tabla.semana_inicio.min()
    esperado = tabla[
        tabla.fundo_fuente.isin(["Aqu Anqa 3", "Aqu Anqa 5"]) & tabla.semana_inicio.eq(primera)
    ].p50_kg.sum()
    plan = plan_semanal(tabla)
    assert plan.loc[plan.semana_inicio.eq(primera), "Kawsay"].iat[0] == esperado


def test_un_fundo_ausente_es_sin_datos_y_no_cero(tabla):
    resumen = resumen_fundos(tabla[~tabla.fundo.eq("Quri")])
    quri = resumen[resumen.fundo.eq("Quri")].iloc[0]
    assert quri.estado == "Sin datos"
    assert pd.isna(quri.total_periodo_kg)


def test_seis_semanas_y_campania_completa_no_truncan_igual(tabla):
    inicio = tabla.semana_inicio.min()
    seis = aplicar_horizonte(tabla, HORIZONTE_SEMANAS, inicio=inicio)
    completa = aplicar_horizonte(tabla, HORIZONTE_CAMPANIA, inicio=inicio)
    assert seis.semana_inicio.nunique() == 6
    assert completa.semana_inicio.nunique() == 8


def test_el_total_concilia_lotes_fundos_y_semana(tabla):
    plan = plan_semanal(tabla)
    suma_fundos = plan[list(FUNDOS_OPERATIVOS)].sum(axis=1)
    assert suma_fundos.tolist() == pytest.approx(plan.total_kg.tolist())
    por_semana = tabla.groupby("semana_inicio").p50_kg.sum().sort_index()
    assert por_semana.tolist() == pytest.approx(plan.set_index("semana_inicio").total_kg.tolist())


def test_la_semana_33_se_etiqueta_y_se_ubica_en_su_domingo():
    assert etiqueta_semana(pd.Timestamp("2026-08-10")) == "10/08–16/08/2026"
    modelo = enriquecer(
        pd.DataFrame(
            {
                "fundo": ["Arena"],
                "fecha_objetivo": [pd.Timestamp("2026-08-10")],
                "p50_kg": [681_011.0],
            }
        )
    )
    figura = curva_operativa_actual(modelo, pd.DataFrame(), pd.DataFrame())
    traza = next(item for item in figura.data if item.name == "Modelo Python")
    assert pd.Timestamp(traza.x[0]) == pd.Timestamp("2026-08-16")


def test_la_semana_parcial_es_ambar_y_no_se_conecta():
    real = preparar_real(
        pd.DataFrame(
            {
                "fundo": ["Arena", "Arena"],
                "fecha_objetivo": [pd.Timestamp("2026-08-10"), pd.Timestamp("2026-08-17")],
                "real_kg": [681_011.0, 314_844.0],
            }
        )
    )
    figura = curva_operativa_actual(
        pd.DataFrame(), pd.DataFrame(), real, fecha_hoy=pd.Timestamp("2026-08-21")
    )
    cerrada = next(item for item in figura.data if item.name == "Real cosechado")
    parcial = next(item for item in figura.data if item.name == "Real parcial")
    assert len(cerrada.x) == 1
    assert parcial.mode == "markers"
    assert parcial.marker.color == "#d97706"


def test_r09_esta_oculto_por_defecto_y_es_referencia_opcional(tabla):
    r09 = tabla.copy()
    figura = curva_operativa_actual(tabla, r09, pd.DataFrame())
    assert "R09 publicado" not in {item.name for item in figura.data}
    figura_visible = curva_operativa_actual(tabla, r09, pd.DataFrame(), mostrar_r09=True)
    assert "R09 publicado" in {item.name for item in figura_visible.data}


def test_nowcast_es_comparacion_opcional_y_no_altera_el_plan(tabla):
    nowcast = enriquecer(
        pd.DataFrame(
            {
                "fundo": ["Empresa"],
                "fecha_objetivo": [pd.Timestamp("2026-08-17")],
                "p50_kg": [924_676.0],
            }
        )
    )
    sin_comparacion = curva_operativa_actual(tabla, pd.DataFrame(), pd.DataFrame())
    con_comparacion = curva_operativa_actual(
        tabla,
        pd.DataFrame(),
        pd.DataFrame(),
        nowcast=nowcast,
        mostrar_nowcast=True,
    )
    assert "NowcastCierreSemanal_v1 · cierre miércoles" not in {
        item.name for item in sin_comparacion.data
    }
    assert "NowcastCierreSemanal_v1 · cierre miércoles" in {
        item.name for item in con_comparacion.data
    }


def test_hibrido_v2_normal_se_muestra_como_comparacion_de_seis_semanas():
    fechas = pd.date_range("2026-08-24", periods=6, freq="7D")
    hibrido = enriquecer(
        pd.DataFrame(
            {
                "run_id": [80] * 6,
                "modelo": ["HibridoOcurrenciaOnline_v2"] * 6,
                "version_modelo": ["macro_hurdle_online_full_coverage_v2"] * 6,
                "version_fuente": ["Hibrido v2"] * 6,
                "fundo": ["Empresa"] * 6,
                "fecha_emision": [pd.Timestamp("2026-08-17")] * 6,
                "fecha_objetivo": fechas,
                "horizonte_semanas": list(range(1, 7)),
                "p50_kg": [400_754, 356_815, 411_222, 381_675, 342_255, 367_259],
            }
        )
    )
    figura = curva_operativa_actual(
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        hibrido_v2=hibrido,
        mostrar_hibrido_v2=True,
    )
    traza = next(item for item in figura.data if item.name == "Híbrido ocurrencia v2")
    assert len(traza.x) == 6
    assert list(pd.to_datetime(traza.x)) == list(fechas + pd.Timedelta(days=6))
    assert "H2" not in traza.name
    assert "corrida normal de seis semanas" in traza.customdata[0][2]


def test_r09_muestra_la_version_oficial_de_cada_semana_en_el_tooltip():
    r09 = enriquecer(
        pd.DataFrame(
            {
                "fundo": ["Arena", "Arena"],
                "fecha_objetivo": [pd.Timestamp("2026-08-17"), pd.Timestamp("2026-08-24")],
                "p50_kg": [873_062.10, 919_327.71],
                "version_fuente": ["S34", "S35"],
            }
        )
    )
    figura = curva_operativa_actual(pd.DataFrame(), r09, pd.DataFrame(), mostrar_r09=True)
    traza = next(item for item in figura.data if item.name == "R09 publicado")
    assert list(traza.customdata[:, 3]) == ["S34", "S35"]
    assert "Emisión" in traza.hovertemplate


def test_inicio_operativo_es_despues_de_la_ultima_semana_real(tabla):
    real = preparar_real(
        pd.DataFrame(
            {
                "fundo": ["Arena"],
                "fecha_objetivo": [pd.Timestamp("2026-08-17")],
                "real_kg": [10.0],
            }
        )
    )
    assert inicio_ventana_operativa(tabla, real, fecha_hoy="2026-08-21") == pd.Timestamp(
        "2026-08-24"
    )


def test_detalle_conserva_pania_y_archivo_sin_intervalos(tabla):
    filas = filas_grid(tabla.head(1))
    assert filas[0]["pasada"] == 1
    assert "fuente_libro" not in filas[0]
    descarga = vista_descarga(tabla.head(1))
    assert "Archivo de trazabilidad" not in descarga.columns
    auditoria = vista_trazabilidad(tabla.head(1))
    assert "Archivo fuente (auditoría)" in auditoria.columns
    assert "P10" not in " ".join(descarga.columns)
    assert "P90" not in " ".join(descarga.columns)


def test_grafico_compara_semana_en_curso_sin_conectarla_al_real():
    modelo = enriquecer(
        pd.DataFrame(
            {
                "fundo": ["Arena", "Arena"],
                "fecha_objetivo": [pd.Timestamp("2026-08-17"), pd.Timestamp("2026-08-24")],
                "p50_kg": [700_000.0, 720_000.0],
            }
        )
    )
    real = preparar_real(
        pd.DataFrame(
            {
                "fundo": ["Arena"],
                "fecha_objetivo": [pd.Timestamp("2026-08-17")],
                "real_kg": [314_844.0],
            }
        )
    )
    figura = curva_operativa_actual(
        modelo, pd.DataFrame(), real, fecha_hoy=pd.Timestamp("2026-08-21")
    )
    modelo_traza = next(item for item in figura.data if item.name == "Modelo Python")
    parcial = next(item for item in figura.data if item.name == "Real parcial")
    assert pd.Timestamp(modelo_traza.x[0]) == pd.Timestamp("2026-08-23")
    assert pd.Timestamp(parcial.x[0]) == pd.Timestamp("2026-08-23")
    assert not any(item.name is None and item.mode == "lines" for item in figura.data)


def test_filtros_admiten_seleccion_multiple(tabla):
    filtrada = filtrar_ubicacion(tabla, fundo=["Arena", "Quri"], modulo=[], lote=None)
    assert set(filtrada.fundo) == {"Arena", "Quri"}
    assert filtrar_ubicacion(tabla, fundo=[]).shape == tabla.shape


def test_perfiles_por_fundo_usan_curvas_comparables(tabla):
    figura = curvas_por_fundo(tabla, pd.DataFrame())
    assert len(figura.data) == len(FUNDOS_OPERATIVOS)
    assert {traza.type for traza in figura.data} == {"scatter"}
    assert [traza.name for traza in figura.data] == list(FUNDOS_OPERATIVOS)
    assert all(traza.fill == "tozeroy" for traza in figura.data)


def test_nowcast_se_muestra_como_cierre_semanal_y_no_como_plan_futuro():
    semanas = pd.date_range("2026-08-10", periods=2, freq="7D")
    nowcast = pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "semana_inicio": semanas,
            "semana_cierre": semanas + pd.Timedelta(days=6),
            "fundo": ["Empresa", "Empresa"],
            "p50_kg": [687_821.0, 924_676.0],
            "real_kg": [681_011.0, 849_671.0],
            "macro_kg": [675_000.0, 674_688.0],
            "r09_presemana_kg": [695_153.0, 704_969.0],
            "r09_misma_semana_kg": [695_153.0, 873_062.0],
        }
    )
    panel = panel_nowcast_cierre({"nowcast_cierre": nowcast})
    texto = " ".join(_texto(panel))
    assert "no reemplaza el plan emitido antes" in texto
    assert "924.676 kg" in texto
    assert "Mejora frente a Macro" in texto
    figura = figura_nowcast_cierre(nowcast)
    assert [trace.name for trace in figura.data[:3]] == [
        "Cierre real",
        "Nowcast miércoles",
        "R09 ajustado en la semana",
    ]
    assert figura.data[-1].type == "bar"


def test_historico_muestra_real_proyeccion_y_desviacion_firmada():
    replay = pd.DataFrame(
        {
            "modelo": ["R09_publicado", "R09_publicado"],
            "campania": ["C2025", "C2025"],
            "fundo": ["Arena", "Arena"],
            "lote_id": [1, 1],
            "fecha_objetivo": [pd.Timestamp("2025-07-07"), pd.Timestamp("2025-07-14")],
            "p50_kg": [120.0, 80.0],
            "real_kg": [100.0, 100.0],
        }
    )
    agrupada = agrupar_replay_historico(replay, "semana")
    assert agrupada.desviacion_kg.tolist() == [20.0, -20.0]
    metricas = metricas_replay_historico(agrupada)
    assert metricas["wape"] == pytest.approx(0.2)
    figura = historico_y_desviacion(
        agrupada,
        nombre_serie="R09 publicado · referencia",
        granularidad="semana",
    )
    assert [traza.type for traza in figura.data] == ["scatter", "scatter", "bar"]
    assert list(figura.data[-1].y) == [20.0, -20.0]
    assert figura.layout.xaxis2.tickangle == 0
    assert figura.layout.xaxis2.dtick == 14 * 24 * 60 * 60 * 1000


def test_r09_y_python_conservan_el_mismo_real_aunque_un_modelo_omita_lotes():
    predicciones = pd.DataFrame(
        {
            "modelo": ["MacroLegacy_v1", "MacroLegacy_v1", "R09_publicado"],
            "campania": ["C2026"] * 3,
            "lote_id": [1, 2, 1],
            "fundo": ["Arena"] * 3,
            "modulo": ["M01"] * 3,
            "lote": ["L001", "L002", "L001"],
            "fecha_objetivo": [pd.Timestamp("2026-08-10")] * 3,
            "p50_kg": [90.0, 90.0, 120.0],
            "real_kg": [100.0, 100.0, 100.0],
        }
    )
    reales = pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "lote_id": [1, 2],
            "fundo": ["Arena", "Arena"],
            "modulo": ["M01", "M01"],
            "lote": ["L001", "L002"],
            "fecha_objetivo": [pd.Timestamp("2026-08-10")] * 2,
            "real_kg": [100.0, 100.0],
        }
    )

    python = alinear_replay_con_real_comun(predicciones, reales, "MacroLegacy_v1")
    r09 = alinear_replay_con_real_comun(predicciones, reales, "R09_publicado")
    assert python.real_kg.sum() == r09.real_kg.sum() == 200.0
    assert r09.p50_kg.sum() == 120.0
    assert len(r09) == 2
    metricas = metricas_replay_historico(agrupar_replay_historico(r09, "semana"), r09)
    assert metricas["wape"] == pytest.approx(0.4)


def test_un_periodo_real_sin_emision_no_se_elimina_del_universo():
    predicciones = pd.DataFrame(
        {
            "modelo": ["R09_publicado"],
            "campania": ["C2025"],
            "lote_id": [1],
            "fecha_objetivo": [pd.Timestamp("2025-07-07")],
            "p50_kg": [100.0],
        }
    )
    reales = pd.DataFrame(
        {
            "campania": ["C2025", "C2025"],
            "lote_id": [1, 1],
            "fecha_objetivo": [pd.Timestamp("2025-07-07"), pd.Timestamp("2025-07-14")],
            "real_kg": [100.0, 100.0],
        }
    )
    alineado = alinear_replay_con_real_comun(predicciones, reales, "R09_publicado")
    assert len(alineado) == 2
    faltante = alineado.loc[alineado.fecha_objetivo.eq(pd.Timestamp("2025-07-14")), "p50_kg"].iat[0]
    assert faltante == 0


def test_selector_operativo_no_expone_experimentos_internos():
    assert set(SERIES_HISTORICAS) == {
        "R09_publicado",
        "MacroLegacy_v1",
        "HibridoOcurrenciaOnline_v2",
        "HibridoParametrosAsOf_v1",
    }


def test_layout_historico_no_contiene_campanias_ficticias(monkeypatch):
    monkeypatch.setattr(pagina, "datos", lambda: {})
    componentes = list(_componentes(pagina.layout()))
    por_id = {getattr(item, "id", None): item for item in componentes}
    selector = por_id["proy-hist-campania"]
    assert selector.options == []
    assert selector.value is None
    texto = " ".join(_texto(pagina.layout()))
    assert "Campaña más reciente" not in texto
    assert "Todas las campañas" not in texto


def test_campanias_evaluables_usan_la_fecha_cerrada_mas_reciente():
    replay = pd.DataFrame(
        {
            "campania": ["C2025", "C2026", "C2024"],
            "fecha_objetivo": pd.to_datetime(["2026-02-22", "2026-08-16", "2025-04-20"]),
            "emitio_prediccion": [True, True, False],
        }
    )
    opciones = callbacks_proyeccion._campanias_evaluables(replay)
    assert opciones == ["C2026", "C2025"]
    assert callbacks_proyeccion._seleccionar_campania_concreta(None, opciones) == "C2026"


def test_campania_concreta_se_preserva_al_cambiar_granularidad():
    disponibles = ["C2026", "C2025", "C2024"]
    for granularidad in ("semana", "mes", "campania"):
        assert granularidad
        assert callbacks_proyeccion._seleccionar_campania_concreta("C2025", disponibles) == "C2025"


def test_semana_parcial_no_entra_en_las_campanias_evaluables():
    replay = pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "fecha_objetivo": pd.to_datetime(["2026-08-10", "2026-08-17"]),
            "p50_kg": [681_011.0, 704_969.0],
            "real_kg": [681_011.0, 0.0],
            "emitio_prediccion": [True, True],
        }
    )
    cerrados = callbacks_proyeccion._periodos_cerrados(
        pd.DataFrame(
            {
                "campania": ["C2026"],
                "fecha_objetivo": [pd.Timestamp("2026-08-10")],
            }
        )
    )
    filtrado = callbacks_proyeccion._restringir_a_periodos_cerrados(replay, cerrados)
    assert filtrado.fecha_objetivo.tolist() == [pd.Timestamp("2026-08-10")]


def test_modelos_rejected_o_experimentales_no_se_ofrecen():
    replay = pd.DataFrame(
        {
            "modelo": [
                "R09_publicado",
                "MacroLegacy_v1",
                "HibridoOcurrenciaOnline_v2",
                "HibridoParametrosAsOf_v1",
            ],
            "estado_modelo": ["published", "approved", "candidate", "rejected"],
            "publicacion": ["referencia", "operativo", "approved", "experimental"],
        }
    )
    visibles = callbacks_proyeccion._filtrar_modelos_visibles(replay)
    assert set(visibles.modelo) == {
        "R09_publicado",
        "MacroLegacy_v1",
        "HibridoOcurrenciaOnline_v2",
    }
    opciones = [codigo for codigo in SERIES_HISTORICAS if codigo in set(visibles.modelo)]
    assert "HibridoParametrosAsOf_v1" not in opciones
    assert (
        callbacks_proyeccion._seleccionar_serie_visible("HibridoParametrosAsOf_v1", opciones)
        == "HibridoOcurrenciaOnline_v2"
    )


def test_callback_historico_preserva_campania_concreta_y_filtra_series(monkeypatch):
    modelos = [
        "R09_publicado",
        "MacroLegacy_v1",
        "HibridoOcurrenciaOnline_v2",
        "HibridoParametrosAsOf_v1",
    ]
    replay = pd.DataFrame(
        [
            {
                "modelo": modelo,
                "campania": campania,
                "lote_id": 1,
                "fecha_objetivo": fecha,
                "p50_kg": 90.0,
                "real_kg": 100.0,
                "emitio_prediccion": True,
                "estado_modelo": (
                    "rejected" if modelo == "HibridoParametrosAsOf_v1" else "approved"
                ),
            }
            for modelo in modelos
            for campania, fecha in (
                ("C2025", pd.Timestamp("2026-02-22")),
                ("C2026", pd.Timestamp("2026-08-16")),
            )
        ]
    )
    reales = replay.loc[
        replay.modelo.eq("MacroLegacy_v1"),
        ["campania", "lote_id", "fecha_objetivo", "real_kg"],
    ].copy()
    monkeypatch.setattr(
        callbacks_proyeccion,
        "estado_replay_proyeccion",
        lambda: {"replay_detalle": replay, "real_detalle": reales},
    )

    salida = callbacks_proyeccion._actualizar_historico(
        "precision",
        "C2025",
        "HibridoOcurrenciaOnline_v2",
        "campania",
        "12",
        [],
        [],
        [],
    )
    opciones_campania, seleccion = salida[3], salida[4]
    opciones_modelo, serie = salida[5], salida[6]
    assert opciones_campania == [
        {"label": "C2026", "value": "C2026"},
        {"label": "C2025", "value": "C2025"},
    ]
    assert seleccion == "C2025"
    assert serie == "HibridoOcurrenciaOnline_v2"
    assert "HibridoParametrosAsOf_v1" not in {opcion["value"] for opcion in opciones_modelo}


def test_callback_historico_no_ofrece_serie_sin_release_en_la_campania(monkeypatch):
    replay = pd.DataFrame(
        [
            {
                "modelo": modelo,
                "campania": campania,
                "lote_id": 1,
                "fecha_objetivo": fecha,
                "p50_kg": 90.0,
                "real_kg": 100.0,
                "emitio_prediccion": True,
            }
            for modelo, campania, fecha in (
                ("R09_publicado", "C2026", pd.Timestamp("2026-08-16")),
                ("MacroLegacy_v1", "C2026", pd.Timestamp("2026-08-16")),
                ("HibridoOcurrenciaOnline_v2", "C2026", pd.Timestamp("2026-08-16")),
                ("MacroLegacy_v1", "C2025", pd.Timestamp("2026-02-22")),
                ("HibridoOcurrenciaOnline_v2", "C2025", pd.Timestamp("2026-02-22")),
            )
        ]
    )
    reales = replay.loc[
        replay.modelo.eq("MacroLegacy_v1"),
        ["campania", "lote_id", "fecha_objetivo", "real_kg"],
    ].copy()
    monkeypatch.setattr(
        callbacks_proyeccion,
        "estado_replay_proyeccion",
        lambda: {"replay_detalle": replay, "real_detalle": reales},
    )

    salida = callbacks_proyeccion._actualizar_historico(
        "precision",
        "C2025",
        "R09_publicado",
        "campania",
        "12",
        [],
        [],
        [],
    )

    opciones_modelo = {opcion["value"] for opcion in salida[5]}
    assert opciones_modelo == {
        "MacroLegacy_v1",
        "HibridoOcurrenciaOnline_v2",
    }
    assert salida[6] == "HibridoOcurrenciaOnline_v2"


def test_wape_declara_nivel_visible_y_conserva_error_lote_semana():
    replay = pd.DataFrame(
        {
            "modelo": ["MacroLegacy_v1", "MacroLegacy_v1"],
            "campania": ["C2026", "C2026"],
            "fundo": ["Arena", "Arena"],
            "lote_id": [1, 1],
            "fecha_objetivo": [pd.Timestamp("2026-07-06"), pd.Timestamp("2026-07-13")],
            "p50_kg": [150.0, 50.0],
            "real_kg": [100.0, 100.0],
        }
    )
    mensual = agrupar_replay_historico(replay, "mes")
    metricas = metricas_replay_historico(mensual, replay)

    assert len(mensual) == 1
    assert metricas["wape"] == pytest.approx(0.0)
    assert metricas["wape_lote_semana"] == pytest.approx(0.5)
    assert metricas["semanas"] == 2
    assert metricas["meses"] == 1


def test_kpis_separan_precision_operativa_de_cobertura_y_baseline():
    replay = pd.DataFrame(
        {
            "modelo": ["R09_publicado"] * 3,
            "campania": ["C2026"] * 3,
            "fundo": ["Arena"] * 3,
            "lote_id": [1, 1, 1],
            "fecha_objetivo": pd.to_datetime(["2026-07-06", "2026-07-13", "2026-07-20"]),
            "p50_kg": [120.0, 0.0, 140.0],
            "real_kg": [100.0, 100.0, 120.0],
            "emitio_prediccion": [True, False, True],
        }
    )
    agrupada = agrupar_replay_historico(replay, "semana")
    metricas = metricas_replay_historico(agrupada, replay)

    # Operativo: la semana sin emisión se penaliza como cero.
    assert metricas["wape_operacional"] == pytest.approx(140 / 320)
    assert metricas["wape"] == pytest.approx(metricas["wape_operacional"])
    # Condicionado: solo evalúa las dos semanas que sí fueron emitidas.
    assert metricas["wape_condicionado"] == pytest.approx(40 / 220)
    assert metricas["cobertura_volumen"] == pytest.approx(220 / 320)
    assert metricas["cobertura_lote_semana"] == pytest.approx(2 / 3)
    assert metricas["mae_kg"] == pytest.approx((20 + 100 + 20) / 3)
    assert metricas["rmse_kg"] == pytest.approx(((20**2 + 100**2 + 20**2) / 3) ** 0.5)
    assert metricas["bias_kg"] == pytest.approx(-60.0)
    assert metricas["sesgo"] == pytest.approx(-60 / 320)
    assert "mase" in metricas and "rmsse" in metricas


def test_ventana_semanal_limita_solo_las_ultimas_semanas():
    tabla = pd.DataFrame(
        {
            "fecha_objetivo": pd.date_range("2026-01-04", periods=20, freq="7D"),
            "modelo": ["MacroLegacy_v1"] * 20,
        }
    )
    limitada = limitar_ventana_semanal(tabla, "12")
    assert len(limitada) == 12
    assert limitada.fecha_objetivo.min() == tabla.fecha_objetivo.iloc[-12]
    assert len(limitar_ventana_semanal(tabla, "todo")) == 20


def test_mes_conserva_separadas_las_campanias_aunque_compartan_mes_calendario():
    replay = pd.DataFrame(
        {
            "modelo": ["MacroLegacy_v1", "MacroLegacy_v1"],
            "campania": ["C2025", "C2026"],
            "lote_id": [1, 1],
            "fecha_objetivo": [pd.Timestamp("2025-07-07"), pd.Timestamp("2026-07-06")],
            "p50_kg": [90.0, 120.0],
            "real_kg": [100.0, 100.0],
        }
    )
    mensual = agrupar_replay_historico(replay, "mes")
    assert len(mensual) == 2
    assert set(mensual.campania) == {"C2025", "C2026"}


def test_historico_de_campania_no_dibuja_barras_gigantes():
    agrupada = pd.DataFrame(
        {
            "etiqueta": ["C2026"],
            "real_kg": [314_844.0],
            "proyectado_kg": [119_467.0],
            "desviacion_kg": [-195_377.0],
        }
    )
    figura = historico_y_desviacion(
        agrupada,
        nombre_serie="Modelo Python · replay histórico",
        granularidad="campania",
    )
    assert [traza.type for traza in figura.data] == ["scatter", "scatter", "scatter"]
    assert figura.layout.xaxis.title.text == "Kg de campaña"


def test_un_solo_mes_tampoco_dibuja_barras_gigantes():
    agrupada = pd.DataFrame(
        {
            "etiqueta": ["ago 2026"],
            "real_kg": [314_844.0],
            "proyectado_kg": [119_467.0],
            "desviacion_kg": [-195_377.0],
        }
    )
    figura = historico_y_desviacion(
        agrupada,
        nombre_serie="Modelo Python · replay histórico",
        granularidad="mes",
    )
    assert [traza.type for traza in figura.data] == ["scatter", "scatter", "scatter"]
    assert figura.layout.xaxis.title.text == "Kg del período"


def test_layout_es_operativo_y_no_expone_controles_inertes(monkeypatch):
    estado = {
        "proyeccion_experimental": _proyeccion(),
        "proyeccion": pd.DataFrame(),
        "cosecha_real": pd.DataFrame(),
        "lotes": pd.DataFrame(),
        "replay": pd.DataFrame(),
        "metricas_comparacion": pd.DataFrame(),
        "curva_historica": pd.DataFrame(),
    }
    monkeypatch.setattr(pagina, "datos", lambda: estado)
    layout = pagina.layout()
    componentes = list(_componentes(layout))
    ids = [getattr(item, "id", None) for item in componentes if getattr(item, "id", None)]
    assert ids.count("proy-curva") == 1
    assert len(ids) == len(set(ids))
    for eliminado in (
        "proy-fuente-modelo",
        "proy-ajuste-riego",
        "proy-clima-escenario",
        "proy-ajuste-poda",
        "proy-semanas",
    ):
        assert eliminado not in ids
    texto = " ".join(_texto(layout)).casefold()
    assert "plan semanal de cosecha" in texto
    assert "r09 · plan vigente" not in texto
    por_id = {getattr(item, "id", None): item for item in componentes}
    assert por_id["proy-fundo"].multi is True
    assert por_id["proy-modulo"].multi is True
    assert por_id["proy-lote"].multi is True


def test_pagina_abre_sin_corrida(monkeypatch):
    monkeypatch.setattr(pagina, "datos", lambda: {})
    assert pagina.layout() is not None


def test_hay_un_solo_grafico_operativo_principal(monkeypatch):
    monkeypatch.setattr(
        pagina,
        "datos",
        lambda: {
            "proyeccion_experimental": _proyeccion(),
            "replay": pd.DataFrame(),
            "metricas_comparacion": pd.DataFrame(),
            "curva_historica": pd.DataFrame(),
        },
    )
    graficos = [item for item in _componentes(pagina.layout()) if isinstance(item, dcc.Graph)]
    assert sum(grafico.id == "proy-curva" for grafico in graficos) == 1
