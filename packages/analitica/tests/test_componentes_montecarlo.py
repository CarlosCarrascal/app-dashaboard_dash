"""Propagación del error de los componentes al intervalo del producto, y alta de familias.

El Monte Carlo es un diagnóstico paralelo: responde cuánta de la incertidumbre en kilos
viene de no saber los frutos y cuánta de no saber el peso. Los intervalos publicados siguen
siendo los calibrados sobre el producto, y estas pruebas fijan esa separación.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.aplicacion.procesos.torneo import FAMILIAS_CHALLENGER
from analitica.dominio.modelos.componentes import intervalos_producto_montecarlo


def _salida(correlacion: float = 0.0, n_emisiones: int = 14, semilla: int = 7) -> pd.DataFrame:
    """Predicciones ya ensambladas con residuos de componente de correlación conocida.

    `correlacion` gobierna la dependencia entre el error de frutos y el de peso: con −1 los
    errores se compensan (más frutos de los previstos, cada uno más liviano) y el producto
    es más estable de lo que sugerirían los componentes por separado.
    """
    rng = np.random.default_rng(semilla)
    filas = []
    for semana in range(n_emisiones):
        emision = pd.Timestamp("2026-01-05") + pd.Timedelta(weeks=semana)
        for lote in range(12):
            base = rng.normal(0, 0.20)
            otro = rng.normal(0, 0.20)
            res_frutos = base
            res_peso = correlacion * base + np.sqrt(max(0.0, 1 - correlacion**2)) * otro
            plantas, frutos, peso = 5000.0, 55.0, 3.4
            filas.append(
                {
                    "modelo": "Componentes_identidad",
                    "banda_horizonte": "operativo",
                    "lote_id": lote,
                    "fecha_emision": emision,
                    "fecha_objetivo": emision + pd.Timedelta(weeks=1),
                    "plantas": plantas,
                    "frutos_por_planta": frutos,
                    "peso_baya_g": peso,
                    "p50_kg": plantas * frutos * peso / 1000,
                    "frutos_reales_por_planta_catalogo": frutos * np.exp(res_frutos),
                    "peso_real_g": peso * np.exp(res_peso),
                }
            )
    return pd.DataFrame(filas)


def test_el_montecarlo_produce_intervalos_ordenados_y_declara_su_muestra():
    salida = intervalos_producto_montecarlo(_salida(), repeticiones=400)
    con_intervalo = salida.dropna(subset=["p10_kg_mc", "p90_kg_mc"])
    assert not con_intervalo.empty
    assert (con_intervalo.p10_kg_mc <= con_intervalo.p50_kg).all()
    assert (con_intervalo.p50_kg <= con_intervalo.p90_kg_mc).all()
    assert (con_intervalo.n_parejas_mc >= 50).all()


def test_las_primeras_emisiones_no_reciben_intervalo_inventado():
    """Sin parejas resueltas suficientes se devuelve NaN, no un intervalo de cuatro casos."""
    salida = intervalos_producto_montecarlo(_salida(), repeticiones=200, minimo_parejas=50)
    primera = salida[salida.fecha_emision == salida.fecha_emision.min()]
    assert primera.p10_kg_mc.isna().all()
    assert (primera.n_parejas_mc == 0).all()


def test_remuestrear_parejas_preserva_la_correlacion_entre_componentes():
    """La razón de ser del método: muestrear la pareja completa y no cada residuo aparte.

    Con errores anticorrelacionados —más frutos, cada uno más liviano— el producto es más
    estable que sus piezas. Un remuestreo independiente rompería esa compensación y daría
    un intervalo más ancho del que los datos justifican.
    """
    anticorrelados = intervalos_producto_montecarlo(
        _salida(correlacion=-0.95), repeticiones=1500
    ).dropna(subset=["p10_kg_mc"])
    independientes = intervalos_producto_montecarlo(
        _salida(correlacion=0.0), repeticiones=1500
    ).dropna(subset=["p10_kg_mc"])
    ancho_anti = (anticorrelados.p90_kg_mc - anticorrelados.p10_kg_mc).mean()
    ancho_indep = (independientes.p90_kg_mc - independientes.p10_kg_mc).mean()
    assert ancho_anti < ancho_indep


def test_el_montecarlo_no_reemplaza_los_intervalos_publicados():
    """Escribe en columnas propias: el control de cobertura sigue comparando entre iguales."""
    entrada = _salida().assign(p10_kg=1.0, p90_kg=2.0)
    salida = intervalos_producto_montecarlo(entrada, repeticiones=200)
    assert (salida.p10_kg == 1.0).all()
    assert (salida.p90_kg == 2.0).all()
    assert {"p10_kg_mc", "p90_kg_mc", "n_parejas_mc"} <= set(salida)


def test_sin_las_columnas_necesarias_devuelve_la_tabla_intacta():
    entrada = _salida().drop(columns=["peso_real_g"])
    salida = intervalos_producto_montecarlo(entrada)
    assert salida.p10_kg_mc.isna().all()
    assert len(salida) == len(entrada)


def test_esta_desactivado_por_defecto_en_el_ensamblado():
    import inspect

    from analitica.dominio.modelos.componentes import challengers_componentes

    firma = inspect.signature(challengers_componentes)
    assert firma.parameters["diagnostico_montecarlo"].default is False


# ── Registro de familias ─────────────────────────────────────────────────────


def test_el_registro_cubre_todas_las_familias_y_todas_avisan_si_no_emiten():
    claves = [f["clave"] for f in FAMILIAS_CHALLENGER]
    assert claves == [
        "macro_legacy",
        "hibrido_legacy",
        "fenologico_v1",
        "componentes",
        "ml",
        "statsforecast",
        "estado_oleadas",
        "gauss_estado",
    ]
    for familia in FAMILIAS_CHALLENGER:
        assert callable(familia["funcion"])
        assert familia["aviso_vacia"], f"{familia['clave']} debe explicar por qué no emitió"


def test_una_familia_vacia_deja_advertencia_y_no_tumba_el_torneo():
    from analitica.aplicacion.procesos import torneo as modulo

    backtest = pd.DataFrame(
        {
            "campania": ["C2026"] * 4,
            "lote_id": [1, 1, 2, 2],
            "lote": ["L1", "L1", "L2", "L2"],
            "fundo": ["F1"] * 4,
            "modulo": ["M1"] * 4,
            "fecha_emision": pd.to_datetime(["2026-01-05"] * 4),
            "fecha_objetivo": pd.to_datetime(["2026-01-12", "2026-01-19"] * 2),
            "horizonte_semanas": [1, 2, 1, 2],
            "banda_horizonte": ["operativo"] * 4,
            "version_fuente": ["S01"] * 4,
            "modelo": ["R09_publicado"] * 4,
            "p50_kg": [100.0, 110.0, 120.0, 130.0],
            "p10_kg": [np.nan] * 4,
            "p90_kg": [np.nan] * 4,
            "real_kg": [105.0, 115.0, 125.0, 135.0],
            "kg_componentes": [100.0, 110.0, 120.0, 130.0],
            "plantas": [5000.0] * 4,
            "frutos_por_planta": [50.0] * 4,
            "peso_baya_g": [3.0] * 4,
        }
    )
    resultado = modulo.ejecutar_torneo(
        backtest, pd.DataFrame(), incluir_ml=True, incluir_statsforecast=False
    )
    assert any("no emitió filas" in a for a in resultado.advertencias)
    assert not resultado.predicciones.empty


def test_una_familia_que_falla_por_dependencia_ausente_no_detiene_el_torneo(monkeypatch):
    from analitica.aplicacion.procesos import torneo as modulo

    def explota(_contexto):
        raise RuntimeError("Instale StatsForecast para habilitar los modelos de serie.")

    registro = tuple(
        {**f, "funcion": explota} if f["clave"] == "statsforecast" else f
        for f in modulo.FAMILIAS_CHALLENGER
    )
    monkeypatch.setattr(modulo, "FAMILIAS_CHALLENGER", registro)
    backtest = pd.DataFrame(
        {
            "campania": ["C2026"] * 2,
            "lote_id": [1, 1],
            "lote": ["L1", "L1"],
            "fundo": ["F1"] * 2,
            "modulo": ["M1"] * 2,
            "fecha_emision": pd.to_datetime(["2026-01-05"] * 2),
            "fecha_objetivo": pd.to_datetime(["2026-01-12", "2026-01-19"]),
            "horizonte_semanas": [1, 2],
            "banda_horizonte": ["operativo"] * 2,
            "version_fuente": ["S01"] * 2,
            "modelo": ["R09_publicado"] * 2,
            "p50_kg": [100.0, 110.0],
            "p10_kg": [np.nan] * 2,
            "p90_kg": [np.nan] * 2,
            "real_kg": [105.0, 115.0],
            "kg_componentes": [100.0, 110.0],
            "plantas": [5000.0] * 2,
            "frutos_por_planta": [50.0] * 2,
            "peso_baya_g": [3.0] * 2,
        }
    )
    resultado = modulo.ejecutar_torneo(
        backtest, pd.DataFrame(), incluir_ml=False, incluir_componentes=False
    )
    assert any("StatsForecast" in a for a in resultado.advertencias)
