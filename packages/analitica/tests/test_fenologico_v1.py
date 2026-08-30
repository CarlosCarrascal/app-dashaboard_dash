from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from analitica.proyeccion.asof import detectar_fuga, enriquecer_asof
from analitica.proyeccion.asof import detectar_fuga as detectar_fuga_asof
from analitica.proyeccion.asof import enriquecer_asof as enriquecer_asof_asof
from analitica.proyeccion.compartido.fechas import (
    lunes_semana,
    ultimo_disponible,
)
from analitica.proyeccion.contratos import DatosProyeccion, FuenteInfo
from analitica.proyeccion.fenologico import (
    ajuste,
    especificacion,
    evidencia,
    incertidumbre,
    metricas,
    panel,
    servicio,
)
from analitica.proyeccion.fenologico.ajuste import (
    _MixedLMFinal,
    _ModeloAjustado,
)
from analitica.proyeccion.fenologico.ajuste import (
    ajustar_clasificador as _ajustar_clasificador,
)
from analitica.proyeccion.fenologico.ajuste import (
    ajustar_mixedlm as _ajustar_mixedlm,
)
from analitica.proyeccion.fenologico.ajuste import (
    ajustar_regresor as _ajustar_regresor,
)
from analitica.proyeccion.fenologico.ajuste import (
    clasificadores as _clasificadores,
)
from analitica.proyeccion.fenologico.ajuste import (
    columnas_modelo as _columnas_modelo,
)
from analitica.proyeccion.fenologico.ajuste import (
    corte_temporal as _corte_temporal,
)
from analitica.proyeccion.fenologico.ajuste import (
    pipeline as _pipeline,
)
from analitica.proyeccion.fenologico.ajuste import (
    predecir as _predecir,
)
from analitica.proyeccion.fenologico.ajuste import (
    preprocesador as _preprocesador,
)
from analitica.proyeccion.fenologico.ajuste import (
    regresores as _regresores,
)
from analitica.proyeccion.fenologico.contratos import EscenarioFenologico
from analitica.proyeccion.fenologico.especificacion import (
    FEATURES_CONTROL,
    FEATURES_PROHIBIDAS,
    HIPOTESIS_FEATURE,
    REFERENCIAS_HIPOTESIS,
)
from analitica.proyeccion.fenologico.evidencia import (
    correlacion as _correlacion,
)
from analitica.proyeccion.fenologico.evidencia import (
    evaluar_evidencia_fold,
)
from analitica.proyeccion.fenologico.evidencia import (
    hipotesis as _hipotesis,
)
from analitica.proyeccion.fenologico.incertidumbre import aplicar_escenario_fenologico
from analitica.proyeccion.fenologico.metricas import (
    calibrar_factor_volumen as _calibrar_factor_volumen,
)
from analitica.proyeccion.fenologico.metricas import (
    intervalos_validacion as _intervalos_validacion,
)
from analitica.proyeccion.fenologico.metricas import (
    intervalos_volumen_directo as _intervalos_volumen_directo,
)
from analitica.proyeccion.fenologico.metricas import (
    sensibilidades as _sensibilidades,
)
from analitica.proyeccion.fenologico.panel import (
    auditar_panel_fenologico,
    construir_panel_fenologico,
)
from analitica.proyeccion.fenologico.panel import (
    normalizar_emisiones as _normalizar_emisiones,
)
from analitica.proyeccion.fenologico.servicio import (
    _predecir_emision,
    backtest_fenologico_v1,
    proyectar_fenologico_v1,
)

lunes_semana_temporal = lunes_semana
ultimo_disponible_temporal = ultimo_disponible


def test_fachada_fenologica_conserva_identidad_del_panel():
    assert _normalizar_emisiones is panel.normalizar_emisiones
    assert construir_panel_fenologico is panel.construir_panel_fenologico
    assert auditar_panel_fenologico is panel.auditar_panel_fenologico
    assert _hipotesis is evidencia.hipotesis
    assert _correlacion is evidencia.correlacion


def test_fachada_fenologica_conserva_identidad_del_ajuste():
    assert _ModeloAjustado is ajuste._ModeloAjustado
    assert _MixedLMFinal is ajuste._MixedLMFinal
    assert _columnas_modelo is ajuste.columnas_modelo
    assert _preprocesador is ajuste.preprocesador
    assert _regresores is ajuste.regresores
    assert _clasificadores is ajuste.clasificadores
    assert _corte_temporal is ajuste.corte_temporal
    assert _pipeline is ajuste.pipeline
    assert _ajustar_mixedlm is ajuste.ajustar_mixedlm
    assert _ajustar_regresor is ajuste.ajustar_regresor
    assert _ajustar_clasificador is ajuste.ajustar_clasificador
    assert _predecir is ajuste.predecir


def test_fachada_fenologica_conserva_identidad_de_metricas():
    assert _sensibilidades is metricas.sensibilidades
    assert _intervalos_validacion is metricas.intervalos_validacion
    assert _intervalos_volumen_directo is metricas.intervalos_volumen_directo
    assert _calibrar_factor_volumen is metricas.calibrar_factor_volumen


def test_fachada_reexporta_la_implementacion_fisica_del_servicio_fenologico():
    assert _predecir_emision is servicio._predecir_emision
    assert backtest_fenologico_v1 is servicio.backtest_fenologico_v1
    assert proyectar_fenologico_v1 is servicio.proyectar_fenologico_v1
    assert aplicar_escenario_fenologico is incertidumbre.aplicar_escenario_fenologico

    assert _predecir_emision.__module__ == servicio.__name__
    assert backtest_fenologico_v1.__module__ == servicio.__name__
    assert proyectar_fenologico_v1.__module__ == servicio.__name__
    assert aplicar_escenario_fenologico.__module__ == incertidumbre.__name__


def test_fachada_fenologica_conserva_constantes_historicas():
    assert FEATURES_CONTROL is especificacion.FEATURES_CONTROL
    assert FEATURES_PROHIBIDAS is especificacion.FEATURES_PROHIBIDAS
    assert HIPOTESIS_FEATURE is especificacion.HIPOTESIS_FEATURE
    assert REFERENCIAS_HIPOTESIS is especificacion.REFERENCIAS_HIPOTESIS


def test_fachada_fenologica_conserva_helpers_asof_historicos():
    assert detectar_fuga is detectar_fuga_asof
    assert enriquecer_asof is enriquecer_asof_asof
    assert lunes_semana is lunes_semana_temporal
    assert ultimo_disponible is ultimo_disponible_temporal


def test_regresores_real_kg_conserva_exclusion_historica_de_xgboost():
    assert "XGBoost" not in {nombre for nombre, _ in ajuste.regresores("real_kg")}


def test_intervalos_y_calibracion_respetan_indices_y_horizontes():
    indice = pd.RangeIndex(24)
    entrenamiento = pd.DataFrame(
        {
            "peso_real_g": 2.0,
            "plantas": 100.0,
            "real_kg": [0.4] * 12 + [0.8] * 12,
            "horizonte_semanas": [1] * 12 + [2] * 12,
        },
        index=indice,
    )
    ocurrencia = ajuste._ModeloAjustado(object(), "ocurre", [], [], indice, np.ones(24), 0.0)
    frutos = ajuste._ModeloAjustado(object(), "frutos", [], [], indice, np.ones(24), 0.0)
    peso = ajuste._ModeloAjustado(object(), "peso", [], [], indice, np.full(24, 2.0), 0.0)

    inferior, superior, n = metricas.intervalos_validacion(
        entrenamiento,
        ocurrencia,
        frutos,
        peso,
        factor_validacion=pd.Series(2.0, index=indice),
    )
    np.testing.assert_allclose([inferior, superior], [-0.4, 0.4])
    assert n == 24

    inferior_directo, superior_directo, n_directo = metricas.intervalos_volumen_directo(
        entrenamiento,
        ajuste._ModeloAjustado(object(), "directo", [], [], indice, np.full(24, 0.2), 0.0),
    )
    np.testing.assert_allclose([inferior_directo, superior_directo], [-0.6, 0.6])
    assert n_directo == 24

    prueba = pd.DataFrame({"horizonte_semanas": [1, 2]}, index=pd.Index([100, 101], dtype=int))
    factores_validacion, factores_prueba, metadatos = metricas.calibrar_factor_volumen(
        entrenamiento,
        prueba,
        ocurrencia,
        frutos,
        peso,
    )
    assert metadatos["factores_por_horizonte"] == {1: 2.0, 2: 4.0}
    np.testing.assert_allclose(factores_validacion.iloc[[0, 12]], [2.0, 4.0])
    np.testing.assert_allclose(factores_prueba, [2.0, 4.0])


def test_importar_submodulo_liviano_no_arrastra_dependencias_pesadas():
    entorno = os.environ.copy()
    raiz_paquete = str(Path(__file__).resolve().parents[1])
    entorno["PYTHONPATH"] = os.pathsep.join(
        parte for parte in (raiz_paquete, entorno.get("PYTHONPATH")) if parte
    )
    codigo = """
import sys
import analitica.proyeccion.fenologico
from analitica.proyeccion import DatosProyeccion
import analitica.proyeccion.fenologico.ajuste
assert DatosProyeccion.__name__ == "DatosProyeccion"
assert not any(nombre in sys.modules for nombre in ("sklearn", "statsmodels", "xgboost"))
"""
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        check=False,
        capture_output=True,
        text=True,
        env=entorno,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_api_publica_de_proyeccion_sigue_resolviendo_todos_sus_simbolos():
    entorno = os.environ.copy()
    raiz_paquete = str(Path(__file__).resolve().parents[1])
    entorno["PYTHONPATH"] = os.pathsep.join(
        parte for parte in (raiz_paquete, entorno.get("PYTHONPATH")) if parte
    )
    codigo = """
import analitica.proyeccion as modulo
[getattr(modulo, nombre) for nombre in modulo.__all__]
"""
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        check=False,
        capture_output=True,
        text=True,
        env=entorno,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_ajuste_filtra_features_sin_datos_en_el_bloque_temprano(monkeypatch):
    llamadas = []

    class _Pipeline:
        def fit(self, tabla, objetivo):
            return self

        def predict(self, tabla):
            return np.zeros(len(tabla))

    def _pipeline(estimador, numericas, categorias, *, spline=False):
        llamadas.append((numericas, categorias, spline))
        return _Pipeline()

    monkeypatch.setattr(ajuste, "pipeline", _pipeline)
    monkeypatch.setattr(ajuste, "regresores", lambda objetivo: [("Dummy", lambda: object())])
    monkeypatch.setattr(
        ajuste,
        "ajustar_mixedlm",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no debe llamarse")),
    )
    tabla = pd.DataFrame(
        {
            "fecha_objetivo": pd.date_range("2026-01-05", periods=60, freq="W-MON"),
            "lote_id": np.arange(60),
            "peso_real_g": np.linspace(1, 2, 60),
            "feature_ok": np.linspace(10, 20, 60),
            "feature_tardia": [np.nan] * 48 + list(np.linspace(1, 2, 12)),
        }
    )

    numericas, _ = ajuste.columnas_modelo(tabla, ["feature_ok", "feature_tardia"])
    assert numericas == ["feature_ok", "feature_tardia"]
    ajuste.ajustar_regresor(
        tabla,
        "peso_real_g",
        ["feature_ok", "feature_tardia"],
        usar_mixedlm=False,
    )

    assert llamadas
    assert all(numericas == ["feature_ok"] for numericas, _, _ in llamadas)


def test_mixedlm_fallback_y_prediccion_aplican_contratos_de_salida():
    class _Resultado:
        def predict(self, exog):
            return np.ones(len(exog))

        @property
        def random_effects(self):
            raise np.linalg.LinAlgError("covarianza singular")

    mixto = ajuste._MixedLMFinal(
        _Resultado(),
        ["x"],
        pd.Series({"x": 0.0}),
        pd.Series({"x": 0.0}),
        pd.Series({"x": 1.0}),
    )
    tabla = pd.DataFrame({"x": [1.0, 2.0], "modulo": ["M1", "M2"]})
    np.testing.assert_allclose(mixto.predict(tabla), [1.0, 1.0])

    class _Modelo:
        def predict(self, tabla):
            return np.array([-2.0, 3.0])

        def predict_proba(self, tabla):
            return np.array([[0.1, 1.2], [0.7, -0.2]])

    modelo = ajuste._ModeloAjustado(
        _Modelo(), "Dummy", ["x"], [], pd.Index([0, 1]), np.array([]), 0.0
    )
    np.testing.assert_allclose(ajuste.predecir(modelo, tabla), [0.0, 3.0])
    np.testing.assert_allclose(ajuste.predecir(modelo, tabla, probabilidad=True), [1.0, 0.0])


def test_historial_asof_excluye_cosecha_del_mismo_dia_de_emision():
    objetivos = pd.DataFrame(
        {
            "campania": ["C2026"],
            "lote_id": [1],
            "fecha_emision": [pd.Timestamp("2026-05-04 12:00")],
            "fecha_objetivo": [pd.Timestamp("2026-05-11")],
        }
    )
    reales = pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "lote_id": [1, 1],
            "fecha_objetivo": pd.to_datetime(["2026-04-27", "2026-05-04"]),
            "real_kg": [50.0, 100.0],
            "pasada_real": [1.0, 1.0],
        }
    )

    salida = panel.agregar_historial_asof(objetivos, reales)

    assert salida.loc[0, "kg_ultimas_4_semanas_asof"] == 50.0
    assert salida.loc[0, "semanas_cosecha_asof"] == 1.0


def _datos(*, futuro_kg: float = 500.0) -> DatosProyeccion:
    lotes = pd.DataFrame(
        [
            {
                "lote_id": lote_id,
                "empresa": "AQ",
                "fundo": "F1" if lote_id <= 3 else "F2",
                "modulo": f"M{1 + (lote_id - 1) // 2}",
                "lote": f"L{lote_id}",
                "variedad": "Sekoya Pop",
                "area_ha": 1.5,
                "n_plantas": 2000.0 + lote_id * 50,
                "fecha_siembra": pd.Timestamp("2024-01-01"),
            }
            for lote_id in range(1, 7)
        ]
    )
    cosecha = []
    fechas = pd.date_range("2025-11-03", periods=34, freq="W-MON")
    for lote_id in lotes.lote_id:
        for semana, fecha in enumerate(fechas):
            if (semana + lote_id) % 3:
                peso = 2.4 + 0.02 * semana + lote_id * 0.01
                kg = 240 + 8 * semana + 5 * lote_id
                if fecha == fechas[-1]:
                    kg = futuro_kg
                cosecha.append(
                    {
                        "lote_id": lote_id,
                        "campania": "C2026",
                        "fecha": fecha,
                        "kg": float(kg),
                        "peso_baya": peso,
                        "plantas_cosechadas": float(
                            lotes.loc[lotes.lote_id == lote_id, "n_plantas"].iloc[0]
                        ),
                        "pana": 1 + semana // 4,
                    }
                )
    poda = lotes[["lote_id"]].assign(
        campania="C2026",
        fecha_inicio=pd.Timestamp("2025-08-04"),
    )
    base = {campo.name: pd.DataFrame() for campo in dataclasses.fields(DatosProyeccion)}
    base.update(
        fuente=FuenteInfo(nombre="prueba", firma="x", corte=None),
        forecast=pd.DataFrame(
            {
                "campania": ["C2026"],
                "fecha_emision": [pd.Timestamp("2026-06-01")],
                "kg": [999_999.0],
            }
        ),
        cosecha=pd.DataFrame(cosecha),
        poda=poda,
        lotes=lotes,
    )
    return DatosProyeccion(**base)


def test_panel_fenologico_crea_su_rejilla_sin_componentes_r09():
    emisiones = pd.DataFrame(
        {
            "campania": ["C2026", "C2026"],
            "fecha_emision": pd.to_datetime(["2026-04-06", "2026-04-13"]),
        }
    )
    panel = construir_panel_fenologico(_datos(), emisiones, horizonte_semanas=3)
    assert len(panel) == 2 * 6 * 3
    assert not panel.duplicated(["campania", "fecha_emision", "lote_id", "fecha_objetivo"]).any()
    assert "kg_r09" not in panel
    assert "frutos_por_planta_r09" not in panel
    assert "peso_baya_r09" not in panel
    assert set(panel.calendario_fuente) == {"rejilla_lotes_independiente_de_R09"}


def test_panel_alinea_objetivos_a_la_semana_operativa_aunque_emita_otro_dia():
    emisiones = pd.DataFrame({"campania": ["C2026"], "fecha_emision": [pd.Timestamp("2026-08-20")]})
    panel = construir_panel_fenologico(_datos(), emisiones, horizonte_semanas=2)
    assert set(pd.to_datetime(panel.fecha_objetivo).dt.weekday) == {0}
    assert pd.to_datetime(panel.fecha_objetivo).min() == pd.Timestamp("2026-08-24")


def test_backtest_descarta_emisiones_sin_objetivo_real_cerrado():
    emisiones = pd.DataFrame(
        {
            "campania": ["C2026", "C2026", "C2026"],
            "fecha_emision": pd.to_datetime(["2026-06-01", "2026-06-15", "2026-07-06"]),
        }
    )
    resultado = backtest_fenologico_v1(
        _datos(), emisiones, horizonte_semanas=2, minimo_entrenamiento=5
    )
    assert "descartaron 1 emisiones" in " ".join(resultado.advertencias)
    assert all("2026-07-06" not in aviso for aviso in resultado.advertencias)


def test_modificar_cosecha_posterior_no_cambia_una_emision_pasada():
    emisiones = pd.DataFrame({"campania": ["C2026"], "fecha_emision": [pd.Timestamp("2026-04-06")]})
    columnas = [
        "lote_id",
        "fecha_emision",
        "fecha_objetivo",
        "frutos_por_planta_ultimo_asof",
        "peso_real_g_ultimo_asof",
        "kg_ultimo_asof",
        "kg_acumulado_asof",
        "kg_ultima_cosecha_asof",
        "kg_ultimas_4_semanas_asof",
        "semanas_cosecha_asof",
        "pasada_ultima_asof",
    ]
    original = construir_panel_fenologico(_datos(futuro_kg=500), emisiones, horizonte_semanas=3)[
        columnas
    ]
    mutado = construir_panel_fenologico(_datos(futuro_kg=999_999), emisiones, horizonte_semanas=3)[
        columnas
    ]
    assert_frame_equal(original, mutado)


def test_evidencia_de_features_se_etiqueta_como_no_causal():
    n = 48
    panel = pd.DataFrame(
        {
            "lote_id": np.tile([1, 2], n // 2),
            "modulo": np.tile(["M1", "M2"], n // 2),
            "fecha_emision": pd.date_range("2025-01-06", periods=n, freq="W-MON"),
            "fecha_objetivo": pd.date_range("2025-01-13", periods=n, freq="W-MON"),
            "dias_desde_poda": np.arange(n, dtype=float),
            "ocurre_cosecha": (np.arange(n) > 20).astype(float),
        }
    )
    evidencia = evaluar_evidencia_fold(
        panel, objetivo="ocurre_cosecha", features=["dias_desde_poda"]
    )
    assert len(evidencia) == 1
    assert not bool(evidencia.etiqueta_causal.iloc[0])
    assert "asociación observacional" in evidencia.limitacion.iloc[0]


def test_modelo_compone_ocurrencia_frutos_peso_y_plantas():
    resultado = proyectar_fenologico_v1(
        _datos(),
        fecha_emision="2026-06-29",
        horizonte_semanas=2,
        minimo_entrenamiento=100,
    )
    assert resultado.advertencias == []
    pred = resultado.predicciones
    assert not pred.empty
    esperado = (
        pred.probabilidad_cosecha * pred.plantas * pred.frutos_por_planta * pred.peso_baya_g / 1000
    )
    esperado = esperado * pred.factor_asignacion_cosecha
    np.testing.assert_allclose(pred.p50_kg, esperado, rtol=1e-8, atol=1e-8)
    assert set(pred.modelo) == {"FenologicoComponentes_v1"}
    assert pred.componentes.map(lambda valor: valor["etiqueta_causal"] is False).all()
    auditoria = resultado.auditoria.set_index("regla")
    assert auditoria.loc["fenologico_conteo_rejilla", "estado"] == "ok"

    escenario, avisos = aplicar_escenario_fenologico(
        pred, EscenarioFenologico(nombre="más plantas", plantas_pct=10)
    )
    assert avisos == []
    np.testing.assert_allclose(escenario.p50_kg, pred.p50_kg * 1.1)


def test_auditoria_acepta_horizontes_mixtos_de_historial_y_emision_actual():
    panel = pd.DataFrame(
        {
            "campania": ["C2025", "C2026", "C2026"],
            "fecha_emision": pd.to_datetime(["2025-06-02", "2026-06-01", "2026-06-01"]),
            "lote_id": [1, 1, 1],
            "fecha_objetivo": pd.to_datetime(["2025-06-09", "2026-06-08", "2026-06-15"]),
        }
    )
    auditoria = auditar_panel_fenologico(
        panel,
        n_emisiones=2,
        n_lotes=1,
        horizonte_semanas=2,
        filas_esperadas=3,
    ).set_index("regla")

    assert auditoria.loc["fenologico_conteo_rejilla", "estado"] == "ok"
