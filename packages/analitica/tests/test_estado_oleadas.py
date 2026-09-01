from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analitica.aplicacion.procesos.estado_oleadas import (
    CONFIGURACION_CONGELADA,
    ConfiguracionEstadoOleadas,
    proyectar_estado_oleadas_asof,
)
from analitica.aplicacion.procesos.torneo import ejecutar_torneo


def _panel(*, con_real: bool = True) -> pd.DataFrame:
    filas = []
    emisiones = pd.date_range("2026-01-05", periods=5, freq="7D")
    for indice, emision in enumerate(emisiones):
        for horizonte in (1, 2):
            objetivo = emision + pd.to_timedelta(7 * horizonte, unit="D")
            real = float(2 * (100 + 10 * horizonte + indice)) if con_real else np.nan
            filas.append(
                {
                    "campania": "C2026",
                    "lote_id": "L01",
                    "lote": "L01",
                    "fundo": "F01",
                    "modulo": "M01",
                    "fecha_emision": emision,
                    "fecha_objetivo": objetivo,
                    "horizonte_semanas": horizonte,
                    "banda_horizonte": "operativo",
                    "version_fuente": "S01",
                    "modelo": "R09_publicado",
                    "p50_kg": float(100 + 10 * horizonte + indice),
                    "p10_kg": float(50 + 5 * horizonte),
                    "p90_kg": float(150 + 15 * horizonte),
                    "real_kg": real,
                    "kg_componentes": float(100 + 10 * horizonte + indice),
                }
            )
    return pd.DataFrame(filas)


def _oleadas(panel: pd.DataFrame) -> pd.DataFrame:
    salida = panel[["campania", "lote_id", "fecha_emision", "fecha_objetivo"]].copy()
    salida["participacion_ola_1"] = 0.2
    salida["participacion_ola_2"] = 0.5
    salida["participacion_ola_3"] = 0.3
    return salida


def test_configuracion_congelada_corrige_r09_y_reparte_el_p50_en_oleadas():
    panel = _panel()
    salida, metadata = proyectar_estado_oleadas_asof(panel, panel_oleadas=_oleadas(panel))

    assert metadata["modelo"] == "HibridoEstadoOleadas_v1"
    assert metadata["publicable"] is False
    assert salida.modelo.eq("HibridoEstadoOleadas_v1").all()
    assert salida.loc[0, "p50_base_kg"] == pytest.approx(panel.loc[0, "p50_kg"])
    assert salida.loc[0, "factor_estado_asof"] == pytest.approx(1.0)
    np.testing.assert_allclose(
        salida[[f"kg_ola_{indice}_ajustada" for indice in range(1, 4)]].sum(axis=1),
        salida.p50_kg,
    )
    assert salida.ola_principal.eq("ola_2").all()
    assert salida.driver_mecanico_principal.eq("ola_2").all()
    assert salida.componentes.iloc[0]["etiqueta_causal"] is False

    manual = _oleadas(panel).drop(columns="lote_id").assign(lote="L01")
    salida_manual, metadata_manual = proyectar_estado_oleadas_asof(
        panel, panel_oleadas=manual
    )
    assert metadata_manual["n_filas_con_oleadas"] == len(panel)
    assert salida_manual.tiene_descomposicion_oleadas.all()


def test_no_lee_resultados_futuros_y_puede_emitir_sin_real():
    panel = _panel()
    original, _ = proyectar_estado_oleadas_asof(panel)
    mutado = panel.copy()
    mutado.loc[mutado.fecha_objetivo > pd.Timestamp("2026-02-01"), "real_kg"] = 999999.0
    repetido, _ = proyectar_estado_oleadas_asof(mutado)
    clave = ["campania", "lote_id", "fecha_emision", "fecha_objetivo"]
    a = original[original.fecha_objetivo <= pd.Timestamp("2026-02-01")].set_index(clave)
    b = repetido[repetido.fecha_objetivo <= pd.Timestamp("2026-02-01")].set_index(clave)
    pd.testing.assert_series_equal(a.p50_kg, b.p50_kg, check_names=False)

    vivo, _ = proyectar_estado_oleadas_asof(_panel(con_real=False))
    assert len(vivo) == len(panel)
    assert vivo.factor_estado_asof.eq(1.0).all()


def test_completa_horizonte_faltante_y_lo_marca_como_cola_r09():
    panel = _panel(con_real=False)
    salida, metadata = proyectar_estado_oleadas_asof(panel, horizonte_semanas=3)

    assert set(salida.horizonte_semanas) == {1, 2, 3}
    assert salida.loc[salida.horizonte_semanas.le(2), "horizonte_extendido"].eq(False).all()
    assert salida.loc[salida.horizonte_semanas.eq(3), "horizonte_extendido"].all()
    assert metadata["n_filas_horizonte_extendido"] == len(panel) // 2
    assert salida.loc[salida.horizonte_semanas.eq(3), "real_kg"].isna().all()


def test_extension_hereda_factor_de_estado_de_la_ultima_semana_publicada():
    salida, _ = proyectar_estado_oleadas_asof(_panel(), horizonte_semanas=3)
    ultimo_corte = salida.fecha_emision.max()
    h2 = salida[
        salida.fecha_emision.eq(ultimo_corte) & salida.horizonte_semanas.eq(2)
    ].iloc[0]
    h3 = salida[
        salida.fecha_emision.eq(ultimo_corte) & salida.horizonte_semanas.eq(3)
    ].iloc[0]

    assert h3.horizonte_origen_extension == 2
    assert h3.factor_estado_asof == pytest.approx(h2.factor_estado_asof)
    assert h3.p50_kg == pytest.approx(h3.p50_base_kg * h2.factor_estado_asof)


def test_no_extiende_dos_semanas_mas_alla_de_la_cola_publicada():
    panel = _panel(con_real=False)
    panel = panel[panel.horizonte_semanas.eq(1)].copy()

    salida, metadata = proyectar_estado_oleadas_asof(panel, horizonte_semanas=3)

    assert set(salida.horizonte_semanas) == {1}
    assert metadata["n_filas_horizonte_extendido"] == 0


def test_no_rellena_huecos_internos_de_un_lote():
    panel = _panel(con_real=False)
    panel = panel[panel.fecha_emision.eq(pd.Timestamp("2026-01-05"))].copy()
    h3 = panel.loc[panel.horizonte_semanas.eq(2)].copy()
    h3["horizonte_semanas"] = 3
    h3["fecha_objetivo"] = h3.fecha_emision + pd.Timedelta(weeks=3)
    panel = pd.concat(
        [panel[panel.horizonte_semanas.eq(1)], h3], ignore_index=True
    )

    salida, metadata = proyectar_estado_oleadas_asof(panel, horizonte_semanas=3)

    assert set(salida.horizonte_semanas) == {1, 3}
    assert not salida.horizonte_extendido.any()
    assert metadata["n_filas_horizonte_extendido"] == 0


def test_panel_oleadas_rechaza_clave_duplicada_y_sin_clave():
    panel = _panel(con_real=False)
    duplicado = pd.concat([_oleadas(panel), _oleadas(panel).iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="repite una clave"):
        proyectar_estado_oleadas_asof(panel, panel_oleadas=duplicado)

    sin_lote = _oleadas(panel).drop(columns="lote_id")
    with pytest.raises(ValueError, match="identidad compartida"):
        proyectar_estado_oleadas_asof(panel, panel_oleadas=sin_lote)


def test_familia_se_puede_encender_en_torneo_sin_alterar_por_defecto():
    panel = _panel()
    resultado = ejecutar_torneo(
        panel,
        pd.DataFrame(),
        incluir_macro_legacy=False,
        incluir_hibrido_legacy=False,
        incluir_fenologico_v1=False,
        incluir_componentes=False,
        incluir_ml=False,
        incluir_statsforecast=False,
        incluir_estado_oleadas=True,
    )

    assert "HibridoEstadoOleadas_v1" in set(resultado.predicciones.modelo)
    candidato = resultado.predicciones[
        resultado.predicciones.modelo.eq("HibridoEstadoOleadas_v1")
    ]
    assert set(candidato.p50_kg) != set(panel.p50_kg)
    assert not resultado.metricas.empty


def test_configuracion_no_acepta_intervalos_imposibles():
    with pytest.raises(ValueError, match="escala_intervalo"):
        ConfiguracionEstadoOleadas(escala_intervalo=0)
    assert CONFIGURACION_CONGELADA.residual.factor_min == pytest.approx(0.50)
