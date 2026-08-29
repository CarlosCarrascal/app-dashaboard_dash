from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analitica.proyeccion.reconciliacion import bottom_up, verificar_coherencia
from analitica.proyeccion.relaciones import generar_claims
from analitica.proyeccion.torneo import decidir_campeon

RAIZ = Path(__file__).resolve().parents[3]


def test_bottom_up_es_exactamente_coherente():
    lotes = pd.DataFrame(
        {
            "modelo": ["R09_publicado", "R09_publicado"],
            "fecha_emision": pd.to_datetime(["2026-01-05"] * 2),
            "fecha_objetivo": pd.to_datetime(["2026-01-12"] * 2),
            "horizonte_semanas": [1, 1],
            "banda_horizonte": ["operativo", "operativo"],
            "empresa": ["A", "A"],
            "fundo": ["F", "F"],
            "modulo": ["M", "M"],
            "lote": ["L001", "L002"],
            "p10_kg": [8.0, 16.0],
            "p50_kg": [10.0, 20.0],
            "p90_kg": [12.0, 24.0],
        }
    )
    controles = verificar_coherencia(bottom_up(lotes))
    assert set(controles.estado) == {"ok"}
    assert controles.max_diferencia_kg.max() == 0


def _relacion(**cambios) -> pd.DataFrame:
    base = {
        "hipotesis_id": "H1",
        "hipotesis": "GDD precede floración",
        "predictor": "gdd_7",
        "respuesta": "flores",
        "rezago_semanas": 2,
        "n_efectivo": 60,
        "pearson": 0.8,
        "pearson_ic_inferior": 0.6,
        "pearson_ic_superior": 0.9,
        "p_ajustado_bh": 0.001,
        "placebo_supera_estimacion": False,
        "estabilidad_signo_modulo": 0.9,
        "modulos": 4,
    }
    return pd.DataFrame([{**base, **cambios}])


def test_generador_de_claims_no_promueve_asociaciones_a_causal():
    claims = generar_claims(_relacion())
    assert set(claims.clase_evidencia) == {"temporal"}
    assert "causal" in claims.afirmacion.iloc[0]
    # «Consistente», no «replicado»: el análisis comprueba que la asociación resiste sus
    # propios filtros, nunca que se haya repetido en otra campaña.
    assert set(claims.estado) == {"consistente"}


def test_una_muestra_corta_no_llega_a_consistente():
    """El umbral era `n_efectivo >= 5`, que en semanas no descarta absolutamente nada."""
    claims = generar_claims(_relacion(n_efectivo=20))
    assert set(claims.estado) == {"exploratorio"}


def test_el_modelo_mixto_puede_desmentir_a_la_correlacion():
    """Es la única pieza que trata las medidas repetidas del mismo lote como lo que son.

    Sin esta comprobación se publicó H2 como asociación establecida mientras su MixedLM
    daba p = 0,43: la correlación pasaba sus filtros y nadie confrontaba las dos cifras.
    """
    inferencia = pd.DataFrame(
        [
            {
                "hipotesis_id": "H1",
                "metodo": "MixedLM",
                "estado": "ok",
                "n": 30000,
                "estimacion": -0.004,
                "p_valor": 0.43,
            }
        ]
    )
    claims = generar_claims(_relacion(), inferencia)
    assert set(claims.estado) == {"exploratorio"}

    concuerda = inferencia.assign(p_valor=[0.0001])
    assert set(generar_claims(_relacion(), concuerda).estado) == {"consistente"}


def test_promocion_es_conjuntiva_y_rechaza_sesgo_fuera_de_rango():
    fechas = pd.date_range("2026-01-05", periods=20, freq="W-MON")
    reales = [100.0 + i for i in range(20)]
    base = pd.DataFrame(
        {
            "modelo": ["R09_publicado"] * 20 + ["challenger"] * 20,
            "banda_horizonte": "operativo",
            "campania": ["C2025"] * 10 + ["C2026"] * 10 + ["C2025"] * 10 + ["C2026"] * 10,
            "fundo": "F1",
            "lote_id": 1,
            "fecha_emision": list(fechas) * 2,
            "fecha_objetivo": list(fechas + pd.Timedelta(days=7)) * 2,
            "real_kg": reales * 2,
            "p10_kg": [r - 10 for r in reales] * 2,
            "p50_kg": [r + 20 for r in reales] + [r + 12 for r in reales],
            "p90_kg": [r + 30 for r in reales] + [r + 15 for r in reales],
        }
    )
    metricas = pd.DataFrame(
        {
            "modelo": ["R09_publicado", "challenger"],
            "banda_horizonte": ["operativo", "operativo"],
            "n": [20, 20],
            "volumen_real_kg": [2000.0, 2000.0],
            "wape": [0.20, 0.10],
            "mase": [1.0, 0.5],
            "sesgo_pct": [20.0, 11.0],
            "cobertura_80": [0.8, 0.8],
        }
    )
    decision = decidir_campeon(base, metricas).iloc[0]
    assert decision.resultado == "retener"
    assert decision.campeon == "R09_publicado"
    assert not json.loads(decision.checks)["sesgo"]


def test_promocion_compara_pares_exactos_y_rechaza_cobertura_de_nicho():
    fechas = pd.date_range("2026-01-05", periods=20, freq="W-MON")
    base = pd.DataFrame(
        {
            "modelo": "R09_publicado",
            "banda_horizonte": "operativo",
            "campania": ["C2025"] * 10 + ["C2026"] * 10,
            "fundo": "F1",
            "lote_id": 1,
            "fecha_emision": fechas,
            "fecha_objetivo": fechas + pd.Timedelta(days=7),
            "real_kg": [100.0 + i for i in range(20)],
            "p10_kg": [60.0 + i for i in range(20)],
            "p50_kg": [150.0 + i for i in range(20)],
            "p90_kg": [180.0 + i for i in range(20)],
        }
    )
    nicho = base.iloc[:4].copy()
    nicho["modelo"] = "challenger_nicho"
    nicho["p10_kg"] = nicho.real_kg - 10
    nicho["p50_kg"] = nicho.real_kg
    nicho["p90_kg"] = nicho.real_kg + 10
    predicciones = pd.concat([base, nicho], ignore_index=True)
    # La tabla precalculada puede sugerir un gran resultado, pero decidir_campeon recalcula
    # base y challenger sobre claves comunes y mide cobertura contra todo el R09.
    metricas = pd.DataFrame(
        {
            "modelo": ["R09_publicado", "challenger_nicho"],
            "banda_horizonte": ["operativo", "operativo"],
            "n": [20, 4],
            "volumen_real_kg": [2190.0, 406.0],
            "wape": [0.5, 0.0],
            "mase": [1.0, 0.0],
            "sesgo_pct": [50.0, 0.0],
            "cobertura_80": [0.0, 1.0],
        }
    )
    decision = decidir_campeon(predicciones, metricas).iloc[0]
    assert decision.resultado == "retener"
    assert decision.cobertura_volumen < 0.20
    assert not json.loads(decision.checks)["volumen"]


def test_catalogo_cientifico_tiene_campos_auditables():
    catalogo = json.loads(
        (RAIZ / "docs" / "cientifico" / "catalogo_evidencia.json").read_text(encoding="utf-8")
    )
    requeridos = {
        "id",
        "titulo",
        "anio",
        "url",
        "cultivo_variedad",
        "metodo",
        "limitaciones",
        "transferibilidad",
        "uso_en_plataforma",
    }
    assert len(catalogo["estudios"]) >= 10
    assert all(requeridos <= set(estudio) for estudio in catalogo["estudios"])
    assert next(e for e in catalogo["estudios"] if e["id"] == "CA244NI")[
        "transferibilidad"
    ].startswith("alta para protocolo")
