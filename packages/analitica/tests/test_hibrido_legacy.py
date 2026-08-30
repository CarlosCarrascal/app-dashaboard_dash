from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_fenologico_v1 import _datos

from analitica.proyeccion.fenologico import construir_panel_fenologico
from analitica.proyeccion.hibrido import priors, proyecciones, replay, residual, servicio
from analitica.proyeccion.hibrido.priors import (
    ParametroLegacyAsOf,
    _normalizar_emisiones,
    calibrar_parametros_legacy_asof,
)
from analitica.proyeccion.hibrido.proyecciones import (
    NOMBRE_MODELO,
    proyectar_hibrido_v1,
)
from analitica.proyeccion.hibrido.replay import (
    backtest_hibrido_v1,
    backtest_macro_legacy_v1,
    construir_curva_historica,
)
from analitica.proyeccion.hibrido.replay import (
    panel_corte_replay as _panel_corte_replay,
)
from analitica.proyeccion.hibrido.replay import (
    panel_replay_cache as _panel_replay_cache,
)
from analitica.proyeccion.hibrido.residual import (
    EPSILON,
    FEATURES_PROHIBIDAS,
    FEATURES_RESIDUALES,
)
from analitica.proyeccion.hibrido.residual import (
    CorreccionResidual as _CorreccionResidual,
)
from analitica.proyeccion.hibrido.residual import (
    ajustar_residuales as _ajustar_residuales,
)
from analitica.proyeccion.hibrido.residual import (
    features_presentes as _features_presentes,
)
from analitica.proyeccion.hibrido.residual import (
    pipeline_residual as _pipeline_residual,
)


def _emisiones() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campania": ["C2026"] * 4,
            "fecha_emision": pd.to_datetime(
                ["2026-04-06", "2026-05-04", "2026-06-01", "2026-06-29"]
            ),
        }
    )


def test_normalizar_emisiones_a_isla_la_campania_solicitada():
    emisiones = pd.DataFrame(
        {
            "campania": ["C2025", "C2026", "C2026"],
            "fecha_emision": pd.to_datetime(["2025-06-02", "2026-04-06", "2026-05-04"]),
        }
    )
    salida = _normalizar_emisiones(emisiones, "C2026")
    assert set(salida.campania) == {"C2026"}
    assert len(salida) == 2


def test_normalizar_emisiones_no_inventa_campania_si_falta():
    emisiones = pd.DataFrame({"fecha_emision": pd.to_datetime(["2026-04-06"])})
    salida = _normalizar_emisiones(emisiones, "C2026")
    assert salida.campania.tolist() == ["C2026"]


def test_fachada_legacy_conserva_identidad_de_priors_asof():
    assert ParametroLegacyAsOf is priors.ParametroLegacyAsOf
    assert calibrar_parametros_legacy_asof is priors.calibrar_parametros_legacy_asof
    assert _normalizar_emisiones is priors._normalizar_emisiones


def test_fachada_legacy_conserva_identidad_del_residual():
    assert _CorreccionResidual is residual.CorreccionResidual
    assert _ajustar_residuales is residual.ajustar_residuales
    assert _features_presentes is residual.features_presentes
    assert _pipeline_residual is residual.pipeline_residual
    assert EPSILON is residual.EPSILON
    assert FEATURES_RESIDUALES is residual.FEATURES_RESIDUALES
    assert FEATURES_PROHIBIDAS is residual.FEATURES_PROHIBIDAS


def test_residual_rechaza_variables_prohibidas_en_la_api_de_bajo_nivel():
    with pytest.raises(ValueError, match="variables prohibidas"):
        residual.pipeline_residual(pd.DataFrame({"p50_kg": [1.0]}), ["p50_kg"])


def test_residual_excluye_negativos_y_respeta_umbral_de_entrenamiento():
    entrenamiento = pd.DataFrame(
        {
            "legacy_frutos_por_planta": [10.0, 11.0, 12.0],
            "frutos_reales_por_planta_catalogo": [9.0, -1.0, 11.0],
            "legacy_peso_baya_g": [2.0, 2.1, 2.2],
            "peso_real_g": [2.1, -0.5, 2.3],
            "real_kg": [100.0, 90.0, 110.0],
            "legacy_kg": [95.0, 85.0, 105.0],
        }
    )

    correccion = residual.ajustar_residuales(entrenamiento, minimo_entrenamiento=3)

    assert correccion.modelo_frutos is None
    assert correccion.modelo_peso is None
    assert correccion.n_entrenamiento == 2


def test_fachada_legacy_conserva_identidad_del_replay():
    assert _panel_corte_replay is replay.panel_corte_replay
    assert _panel_replay_cache is replay.panel_replay_cache
    assert backtest_hibrido_v1 is replay.backtest_hibrido_v1
    assert backtest_macro_legacy_v1 is replay.backtest_macro_legacy_v1
    assert construir_curva_historica is replay.construir_curva_historica


def test_servicio_es_la_implementacion_y_no_depende_de_una_fachada_historica():
    assert servicio._legacy_panel is proyecciones._legacy_panel
    assert servicio.proyectar_hibrido_v1 is proyecciones.proyectar_hibrido_v1
    assert servicio.proyectar_macro_legacy_v1 is proyecciones.proyectar_macro_legacy_v1

    raiz = Path(servicio.__file__).parent
    for ruta in (raiz / "servicio.py", raiz / "replay.py"):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        imports_historicos = [
            nodo
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom)
            and nodo.module
            and nodo.module.endswith("hibrido_legacy")
        ]
        assert imports_historicos == []


def test_replay_y_servicio_conservan_dependencias_unidireccionales():
    def imports_de(ruta: Path) -> set[str]:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        encontrados = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                encontrados.add(nodo.module)
            elif isinstance(nodo, ast.Import):
                encontrados.update(alias.name for alias in nodo.names)
        return encontrados

    imports_replay = imports_de(Path(replay.__file__))
    imports_servicio = imports_de(Path(servicio.__file__))
    imports_proyecciones = imports_de(Path(proyecciones.__file__))

    assert "servicio" not in imports_replay
    assert "replay" in imports_servicio
    assert "servicio" not in imports_proyecciones
    assert "replay" not in imports_proyecciones


def test_los_motores_canonicos_contienen_la_implementacion_de_negocio():
    for modulo, simbolo in (
        (proyecciones, "proyectar_hibrido_v1"),
        (replay, "backtest_hibrido_v1"),
        (residual, "ajustar_residuales"),
    ):
        assert any(
            isinstance(nodo, (ast.FunctionDef, ast.ClassDef)) and nodo.name == simbolo
            for nodo in ast.walk(ast.parse(Path(modulo.__file__).read_text(encoding="utf-8")))
        )


def test_cache_replay_se_invalida_al_mutar_una_fuente():
    datos = _datos()
    emisiones = _emisiones().iloc[:2]

    primero = _panel_replay_cache(datos, emisiones, horizonte_semanas=2)
    datos.cosecha.loc[datos.cosecha.index[0], "kg"] += 1.0
    segundo = _panel_replay_cache(datos, emisiones, horizonte_semanas=2)

    assert segundo is not primero


def test_cache_replay_rechaza_emisiones_de_varias_campanias():
    emisiones = pd.DataFrame(
        {
            "campania": ["C2025", "C2026"],
            "fecha_emision": pd.to_datetime(["2025-06-02", "2026-06-01"]),
        }
    )

    with pytest.raises(ValueError, match="una sola campaña"):
        _panel_replay_cache(_datos(), emisiones, horizonte_semanas=2)


def test_hibrido_conserva_identidad_y_expone_base_legacy():
    datos = _datos()
    panel = construir_panel_fenologico(datos, _emisiones(), horizonte_semanas=3)
    prediccion = proyectar_hibrido_v1(panel, datos, "2026-06-29", minimo_entrenamiento=5)

    assert not prediccion.empty
    assert set(prediccion.modelo) == {NOMBRE_MODELO}
    esperado = prediccion.plantas * prediccion.frutos_por_planta * prediccion.peso_baya_g / 1000
    np.testing.assert_allclose(prediccion.p50_kg, esperado, rtol=1e-8, atol=1e-8)
    assert prediccion.componentes.map(lambda valor: valor["modelo_base"] == "MacroLegacy_v1").all()
    assert prediccion.componentes.map(lambda valor: valor["etiqueta_causal"] is False).all()


def test_hibrido_no_cambia_si_se_modifica_cosecha_posterior_al_corte():
    emisiones = _emisiones()
    datos_original = _datos()
    panel_original = construir_panel_fenologico(datos_original, emisiones, horizonte_semanas=3)
    original = proyectar_hibrido_v1(
        panel_original, datos_original, "2026-06-29", minimo_entrenamiento=5
    )

    datos_mutado = _datos()
    datos_mutado.cosecha.loc[
        pd.to_datetime(datos_mutado.cosecha.fecha) > pd.Timestamp("2026-06-29"), "kg"
    ] *= 100
    panel_mutado = construir_panel_fenologico(datos_mutado, emisiones, horizonte_semanas=3)
    mutado = proyectar_hibrido_v1(panel_mutado, datos_mutado, "2026-06-29", minimo_entrenamiento=5)
    columnas = [
        "lote_id",
        "fecha_objetivo",
        "frutos_por_planta",
        "peso_baya_g",
        "p50_kg",
        "p10_kg",
        "p90_kg",
    ]
    assert_frame_equal(
        original.sort_values(columnas[:2])[columnas].reset_index(drop=True),
        mutado.sort_values(columnas[:2])[columnas].reset_index(drop=True),
        check_dtype=False,
    )


def test_backtest_hibrido_es_ciego_y_guarda_origen_de_emision():
    predicciones, advertencias = backtest_hibrido_v1(
        _datos(), _emisiones(), horizonte_semanas=3, minimo_entrenamiento=5, max_cortes=10
    )

    assert advertencias == []
    assert not predicciones.empty
    assert predicciones.es_replay_ciego.all()
    assert (
        pd.to_datetime(predicciones.origen_emision) == pd.to_datetime(predicciones.fecha_emision)
    ).all()
    assert (
        pd.to_datetime(predicciones.origen_emision) < pd.to_datetime(predicciones.fecha_objetivo)
    ).all()
    assert predicciones.real_kg.notna().all()


def test_backtest_macro_legacy_es_ciego_y_conserva_realidad_unida_al_final():
    predicciones, advertencias = backtest_macro_legacy_v1(
        _datos(), _emisiones(), horizonte_semanas=3, max_cortes=10
    )

    assert advertencias == []
    assert not predicciones.empty
    assert predicciones.es_replay_ciego.all()
    assert (
        pd.to_datetime(predicciones.origen_emision) < pd.to_datetime(predicciones.fecha_objetivo)
    ).all()
    assert predicciones.real_kg.notna().all()


def test_curva_historica_elige_la_ultima_emision_anterior_a_la_semana():
    predicciones = pd.DataFrame(
        [
            {
                "campania": "C2026",
                "lote_id": 1,
                "fecha_objetivo": pd.Timestamp("2026-07-06"),
                "fecha_emision": pd.Timestamp("2026-06-01"),
                "modelo": "HibridoLegacyResidual_v1",
                "p10_kg": 80,
                "p50_kg": 100,
                "p90_kg": 120,
                "real_kg": 110,
            },
            {
                "campania": "C2026",
                "lote_id": 1,
                "fecha_objetivo": pd.Timestamp("2026-07-06"),
                "fecha_emision": pd.Timestamp("2026-06-29"),
                "modelo": "HibridoLegacyResidual_v1",
                "p10_kg": 90,
                "p50_kg": 105,
                "p90_kg": 125,
                "real_kg": 110,
            },
            {
                "campania": "C2026",
                "lote_id": 1,
                "fecha_objetivo": pd.Timestamp("2026-07-06"),
                "fecha_emision": pd.Timestamp("2026-07-06"),
                "modelo": "HibridoLegacyResidual_v1",
                "p10_kg": 95,
                "p50_kg": 108,
                "p90_kg": 130,
                "real_kg": 110,
            },
        ]
    )
    curva = construir_curva_historica(predicciones)
    fila = curva[curva.modelo.eq("HibridoLegacyResidual_v1")].iloc[0]
    assert fila.p50_kg == 105
    assert fila.origen_emision_min == pd.Timestamp("2026-06-29")
    assert fila.tipo_curva == "vintage_historico"
