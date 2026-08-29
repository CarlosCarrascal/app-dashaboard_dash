from __future__ import annotations

import pandas as pd
import pytest

from analitica.proyeccion.pronostico_horizonte import (
    ConfiguracionCorreccionHorizonte,
    aplicar_correccion_horizonte,
    ejecutar_loop_por_horizonte,
    evaluar_mismo_universo,
    metricas_horizonte,
    seleccionar_vintage_coherente,
)


def _panel() -> pd.DataFrame:
    emisiones = pd.date_range("2026-01-05", periods=5, freq="7D")
    filas = []
    for i, emision in enumerate(emisiones):
        for h in (1, 2):
            objetivo = emision + pd.Timedelta(days=7 * h)
            # El real es el doble del baseline sólo cuando ya cerró; la fila
            # futura queda como NaN y nunca puede enseñar su resultado.
            real = (
                float(100 + 25 * i)
                if objetivo + pd.Timedelta(days=6) < emision + pd.Timedelta(days=35)
                else None
            )
            filas.append(
                {
                    "campania": "C2026",
                    "fecha_emision": emision,
                    "fecha_objetivo": objetivo,
                    "horizonte_semanas": h,
                    "lote_id": f"L{i}",
                    "fundo": "Arena" if i % 2 else "Quri",
                    "modulo": "M01",
                    "p50_kg": 100.0,
                    "real_kg": real,
                }
            )
    return pd.DataFrame(filas)


def test_rechaza_emision_contemporanea_y_duplicados() -> None:
    tabla = _panel()
    tabla.loc[0, "fecha_emision"] = tabla.loc[0, "fecha_objetivo"]
    with pytest.raises(ValueError, match="contemporánea"):
        aplicar_correccion_horizonte(tabla)


def test_correccion_no_lee_resultado_futuro() -> None:
    tabla = _panel()
    cfg = ConfiguracionCorreccionHorizonte(nivel="fundo", ventana=4, peso_correccion=1.0)
    original = aplicar_correccion_horizonte(tabla, cfg)
    mutada = tabla.copy()
    # Cambiar sólo resultados que están después de su propia emisión no puede
    # afectar predicciones anteriores. Se comprueba un objetivo muy temprano.
    mutada.loc[mutada["fecha_objetivo"] > pd.Timestamp("2026-01-19"), "real_kg"] = 999999.0
    repetida = aplicar_correccion_horizonte(mutada, cfg)
    clave = ["fecha_emision", "fecha_objetivo", "horizonte_semanas", "lote_id"]
    a = original[original.fecha_objetivo <= pd.Timestamp("2026-01-19")].set_index(clave)["pred_kg"]
    b = repetida[repetida.fecha_objetivo <= pd.Timestamp("2026-01-19")].set_index(clave)["pred_kg"]
    pd.testing.assert_series_equal(a, b, check_names=False)


def test_candidato_no_modifica_baseline_y_metricas_por_horizonte() -> None:
    tabla = _panel()
    cfg = ConfiguracionCorreccionHorizonte(nivel="fundo", peso_correccion=0.75)
    candidato = aplicar_correccion_horizonte(tabla, cfg)
    assert tabla["p50_kg"].tolist() == [100.0] * len(tabla)
    assert set(metricas_horizonte(candidato)["horizonte"]) <= {1, 2}
    comunes = evaluar_mismo_universo(tabla, candidato)
    assert not comunes.empty
    assert {"error_baseline", "error_candidato"} <= set(comunes.columns)


def test_evaluacion_rechaza_universos_distintos() -> None:
    tabla = _panel()
    candidato = tabla.iloc[:-1].copy().assign(pred_kg=lambda frame: frame.p50_kg)
    with pytest.raises(ValueError, match="mismo universo"):
        evaluar_mismo_universo(tabla, candidato)


def test_normalizacion_rechaza_horizonte_fraccionario() -> None:
    tabla = _panel()
    tabla["horizonte_semanas"] = tabla["horizonte_semanas"].astype(float)
    tabla.loc[0, "horizonte_semanas"] = 1.5
    with pytest.raises(ValueError, match="enteros finitos"):
        aplicar_correccion_horizonte(tabla)


def test_ruta_sin_correccion_conserva_la_configuracion() -> None:
    salida = aplicar_correccion_horizonte(_panel())
    assert salida["configuracion_horizonte"].notna().all()


def test_rechaza_calendario_invalido() -> None:
    tabla = _panel()
    tabla = pd.concat([tabla, tabla.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="repite"):
        aplicar_correccion_horizonte(tabla)


def test_vintage_no_suma_emisiones_alternativas() -> None:
    tabla = _panel()
    extra = tabla.iloc[[0]].copy()
    extra["fecha_emision"] = pd.Timestamp("2026-01-06")
    tabla = pd.concat([tabla, extra], ignore_index=True)
    vintage = seleccionar_vintage_coherente(tabla)
    assert len(vintage) < len(tabla)
    assert (
        vintage.groupby(["fecha_objetivo", "horizonte_semanas"]).fecha_emision.nunique().max() == 1
    )


def test_loop_selecciona_cada_horizonte_y_no_es_persistible() -> None:
    tabla = _panel()
    resultado = ejecutar_loop_por_horizonte(
        tabla,
        horizontes=(1, 2),
        configuraciones=[ConfiguracionCorreccionHorizonte()],
        fecha_desarrollo_hasta=pd.Timestamp("2026-01-26"),
    )
    assert resultado["persistible"] is False
    assert set(resultado["resultados"]) == {"1", "2"}
    assert set(resultado["mejor_por_horizonte"]) == {"1", "2"}


def test_correccion_agnostica_reutiliza_otro_horizonte_ya_cerrado() -> None:
    historial = pd.DataFrame(
        [
            {
                "campania": "C2026",
                "fecha_emision": pd.Timestamp("2025-12-22"),
                "fecha_objetivo": pd.Timestamp("2026-01-01"),
                "horizonte_semanas": 1,
                "lote_id": "H1",
                "fundo": "Arena",
                "modulo": "M01",
                "p50_kg": 100.0,
                "real_kg": 200.0,
            },
            {
                "campania": "C2026",
                "fecha_emision": pd.Timestamp("2026-01-15"),
                "fecha_objetivo": pd.Timestamp("2026-02-01"),
                "horizonte_semanas": 2,
                "lote_id": "H2",
                "fundo": "Arena",
                "modulo": "M01",
                "p50_kg": 100.0,
                "real_kg": None,
            },
        ]
    )
    config = ConfiguracionCorreccionHorizonte(
        nivel="global",
        por_horizonte=False,
        regularizacion=0.0,
        factor_max=2.0,
        minimo_observaciones=1,
    )
    salida = aplicar_correccion_horizonte(historial.iloc[[1]], config, panel_historial=historial)

    assert salida.iloc[0]["factor_horizonte_asof"] > 1.9
    assert salida.iloc[0]["pred_kg"] > 190.0
