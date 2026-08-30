"""Métricas, controles y regla de promoción de las familias que publican componentes.

Sin entrenar nada: se construyen las salidas a mano para poder afirmar exactamente qué
debería medir cada métrica.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from analitica.proyeccion.calidad import controles_componentes
from analitica.proyeccion.metricas import (
    _escala_naive,
    metricas_pareadas_modelos,
    metricas_pronostico,
)
from analitica.proyeccion.torneo import REGLA_PROMOCION, _identidad_coherente


def _predicciones(base_plantas: str = "catalogo", coherente: bool = True) -> pd.DataFrame:
    """Salida ya ensamblada de una familia de componentes.

    Los valores varían por semana y por lote a propósito: con una serie constante, el error
    del método simple es cero y todas las métricas escaladas salen indefinidas.
    """
    filas = []
    for semana in range(8):
        objetivo = pd.Timestamp("2026-02-02") + pd.to_timedelta(semana, unit="W")
        for lote in range(4):
            plantas = 5000.0 + 250 * lote
            frutos = 50.0 + 4 * (semana % 4) + lote
            peso = 3.0 + 0.08 * (semana % 5)
            kg = plantas * frutos * peso / 1000
            filas.append(
                {
                    "modelo": "Componentes_identidad",
                    "banda_horizonte": "operativo",
                    "campania": "C2026",
                    "lote_id": lote,
                    "lote": f"L{lote}",
                    "fundo": "F1",
                    "fecha_emision": objetivo - pd.Timedelta(weeks=1),
                    "fecha_objetivo": objetivo,
                    "p50_kg": kg if coherente else kg * 2,
                    "p10_kg": kg * 0.8,
                    "p90_kg": kg * 1.2,
                    "real_kg": kg * 1.05,
                    "plantas": plantas,
                    "plantas_reales": 2000.0,
                    "frutos_por_planta": frutos,
                    "peso_baya_g": peso,
                    "peso_real_g": peso * 1.02,
                    "base_plantas": base_plantas,
                    "frutos_reales_por_planta_catalogo": frutos * 1.05,
                    "frutos_reales_por_planta": frutos * 2.6,
                }
            )
    return pd.DataFrame(filas)


def test_las_metricas_de_frutos_usan_la_base_que_declara_la_fila():
    """La comprobación del desalineo de bases.

    `frutos_reales_por_planta` se despeja sobre plantas cosechadas y el modelo predice
    sobre plantas de catálogo. Comparar contra la serie equivocada mide la diferencia entre
    definiciones —aquí, un factor 2,6— en lugar del error del modelo.
    """
    catalogo = metricas_pronostico(_predicciones("catalogo")).iloc[0]
    cosechadas = metricas_pronostico(_predicciones("efectivas")).iloc[0]
    assert catalogo["base_plantas_evaluada"] == "catalogo"
    assert catalogo["mae_frutos_por_planta"] < 5
    assert cosechadas["mae_frutos_por_planta"] > 50


def test_cada_componente_reporta_su_propio_denominador():
    tabla = _predicciones()
    tabla.loc[tabla.index[:16], "peso_real_g"] = np.nan
    fila = metricas_pronostico(tabla).iloc[0]
    assert fila["n_peso_baya_g"] == 16
    assert fila["n_frutos_por_planta"] == 32
    assert fila["n_peso_baya_g"] < fila["n"]


def test_se_reporta_el_sesgo_por_componente_y_no_solo_la_magnitud():
    """Dos sesgos opuestos se cancelan en el producto: sin esta métrica no se detectan."""
    fila = metricas_pronostico(_predicciones()).iloc[0]
    for clave in (
        "sesgo_pct_frutos_por_planta",
        "sesgo_pct_peso_baya_g",
        "wape_frutos_por_planta",
        "wape_peso_baya_g",
        "mase_frutos_por_planta",
        "mase_peso_baya_g",
    ):
        assert np.isfinite(fila[clave]), clave
    assert fila["sesgo_pct_frutos_por_planta"] < 0, "el modelo predice por debajo del real"


def test_el_residuo_de_identidad_delata_un_ensamblado_roto():
    coherente = metricas_pronostico(_predicciones(coherente=True)).iloc[0]
    roto = metricas_pronostico(_predicciones(coherente=False)).iloc[0]
    assert coherente["residuo_identidad_pct"] < 1e-9
    assert roto["residuo_identidad_pct"] > 40


def test_la_escala_naive_respeta_la_columna_que_se_le_pide():
    tabla = _predicciones().rename(columns={"lote": "serie_id"})
    assert _escala_naive(tabla) != _escala_naive(tabla, columna="peso_real_g")
    assert np.isnan(_escala_naive(tabla, columna="columna_inexistente"))


def test_la_comparacion_pareada_usa_el_mismo_real_y_el_mismo_n():
    base = _predicciones().assign(modelo="R09_publicado")
    challenger = _predicciones().assign(modelo="FenologicoComponentes_v1")
    # R09 no publicó un real para una semana sin cosecha, pero el objetivo observado
    # de la rejilla independiente sí es cero. Ambos deben evaluarse contra ese mismo cero.
    base.loc[base.index[0], "real_kg"] = np.nan
    challenger.loc[challenger.index[0], "real_kg"] = 0.0
    metricas = metricas_pareadas_modelos(
        pd.concat([base, challenger], ignore_index=True),
        modelo_base="R09_publicado",
        modelo_candidato="FenologicoComponentes_v1",
    )
    assert set(metricas.modelo) == {"R09_publicado", "FenologicoComponentes_v1"}
    assert metricas.n.nunique() == 1
    assert metricas.volumen_real_kg.nunique() == 1


def test_el_control_detecta_un_producto_que_no_reconstruye_su_kg():
    reglas = controles_componentes(_predicciones(coherente=False))
    fila = reglas[reglas.regla == "identidad_kg_reconstruye_componentes"].iloc[0]
    assert fila.estado == "error"
    assert fila.afectados == 32


def test_el_control_pasa_cuando_la_identidad_cierra():
    reglas = controles_componentes(_predicciones(coherente=True))
    fila = reglas[reglas.regla == "identidad_kg_reconstruye_componentes"].iloc[0]
    assert fila.estado == "ok"
    assert fila.afectados == 0


def test_los_modelos_sin_componentes_propios_no_se_controlan():
    """Un modelo que no declara `base_plantas` no tiene nada que reconstruir."""
    tabla = _predicciones().drop(columns=["base_plantas"])
    assert controles_componentes(tabla).empty


def test_la_promocion_exige_que_la_identidad_cierre():
    assert REGLA_PROMOCION["requiere_identidad_coherente"] is True
    assert _identidad_coherente(_predicciones(coherente=True), "Componentes_identidad")
    assert not _identidad_coherente(_predicciones(coherente=False), "Componentes_identidad")


def test_el_check_de_identidad_no_penaliza_a_quien_no_publica_componentes():
    tabla = _predicciones(coherente=False).drop(columns=["base_plantas"])
    assert _identidad_coherente(tabla, "Componentes_identidad")


def test_la_decision_registra_el_check_nuevo():
    """Con un retador comparable, la fila de decisión debe llevar el check de identidad."""
    from analitica.proyeccion.torneo import decidir_campeon

    retador = _predicciones()
    base = retador.assign(modelo="R09_publicado", p50_kg=retador.p50_kg * 1.15)
    predicciones = pd.concat([retador, base], ignore_index=True)
    decisiones = decidir_campeon(predicciones, metricas_pronostico(predicciones))
    evaluadas = decisiones[decisiones.challenger.notna()]
    assert not evaluadas.empty, "el fixture debe producir al menos un retador comparable"
    checks = json.loads(evaluadas.iloc[0].checks)
    assert "identidad_componentes_coherente" in checks
    assert checks["identidad_componentes_coherente"] is True


def test_un_retador_con_identidad_rota_no_se_promueve():
    """Aunque gane en error, si su producto no reconstruye su kg no puede promoverse."""
    from analitica.proyeccion.torneo import decidir_campeon

    retador = _predicciones(coherente=False)
    base = retador.assign(modelo="R09_publicado", p50_kg=retador.real_kg * 3)
    predicciones = pd.concat([retador, base], ignore_index=True)
    decisiones = decidir_campeon(predicciones, metricas_pronostico(predicciones))
    evaluadas = decisiones[decisiones.challenger.notna()]
    assert not evaluadas.empty
    fila = evaluadas.iloc[0]
    assert json.loads(fila.checks)["identidad_componentes_coherente"] is False
    assert fila.resultado == "retener"


def test_la_combinacion_no_hereda_la_autoria_de_los_componentes():
    """Una media ponderada de kilos no es el producto de los componentes que combina.

    `challenger_combinacion` construye su fila heredando la metadata de una de las
    predicciones combinadas. Si arrastra `base_plantas`, el control de identidad le exige
    reconstruir un kg que por definición no puede reconstruir.
    """
    from analitica.proyeccion.modelos import challenger_combinacion

    componentes = _predicciones()
    base = componentes.assign(modelo="R09_publicado", p50_kg=componentes.p50_kg * 1.2)
    combinada = challenger_combinacion(
        pd.concat([componentes, base], ignore_index=True), minimo_historial=4
    )
    if combinada.empty:
        return
    assert "base_plantas" not in combinada or combinada.base_plantas.isna().all()
    assert controles_componentes(combinada).empty


def test_el_contrato_rechaza_un_ensamblado_que_no_cierra():
    """Falla en el momento del ensamblado, antes de que el número llegue a una métrica."""
    import pytest

    from analitica.proyeccion.contratos import validar_predicciones_componentes

    with pytest.raises(ValueError, match="no reconstruye"):
        validar_predicciones_componentes(_predicciones(coherente=False))
    validar_predicciones_componentes(_predicciones(coherente=True))


def test_el_contrato_rechaza_componentes_fisicamente_imposibles():
    import pytest

    from analitica.proyeccion.contratos import validar_predicciones_componentes

    tabla = _predicciones()
    tabla.loc[tabla.index[0], "plantas"] = 0
    with pytest.raises(ValueError, match="imposibles"):
        validar_predicciones_componentes(tabla)


def test_el_contrato_de_backtest_acota_el_peso_de_baya():
    """El techo sale de lo observado en cosecha, no de una constante inventada."""
    import pandera.pandas as pa
    import pytest

    from analitica.proyeccion.contratos import LIMITE_PESO_BAYA_G, validar_backtest

    assert LIMITE_PESO_BAYA_G > 7.14, "debe dejar margen sobre el máximo observado"
    tabla = _predicciones().assign(
        horizonte_semanas=1, version_fuente="S01", modulo="M1", peso_baya_g=999.0
    )
    with pytest.raises(pa.errors.SchemaError):
        validar_backtest(tabla)


def test_las_familias_sin_componentes_siguen_validando():
    """`required=False`: un modelo que no publica componentes no debe fallar el contrato."""
    from analitica.proyeccion.contratos import validar_backtest

    tabla = (
        _predicciones()
        .assign(horizonte_semanas=1, version_fuente="S01", modulo="M1")
        .drop(columns=["plantas", "frutos_por_planta", "peso_baya_g"])
    )
    assert not validar_backtest(tabla).empty


def test_una_metrica_descriptiva_no_intenta_guardarse_como_numero():
    """`analytics.metric.valor` es double precision: el texto va a `atributos`.

    `base_plantas_evaluada` describe contra qué serie se evaluó la métrica; no es una
    métrica. Intentar insertarla como valor hace fallar la corrida entera al persistir.
    """
    import inspect

    from analitica.proyeccion.persistencia import RepositorioAnalytics

    codigo = inspect.getsource(RepositorioAnalytics.guardar_metricas)
    assert "is_numeric_dtype" in codigo, "debe separar métricas numéricas de descriptivas"

    fila = metricas_pronostico(_predicciones()).iloc[0]
    assert isinstance(fila["base_plantas_evaluada"], str)
    numericas = [
        c
        for c in metricas_pronostico(_predicciones()).columns
        if c not in ("modelo", "banda_horizonte", "n", "volumen_real_kg")
        and pd.api.types.is_numeric_dtype(metricas_pronostico(_predicciones())[c])
    ]
    assert "base_plantas_evaluada" not in numericas
    assert "wape" in numericas and "residuo_identidad_pct" in numericas
