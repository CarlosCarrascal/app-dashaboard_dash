from __future__ import annotations

import pandas as pd
import pytest

from analitica.aplicacion.procesos.seleccion_candidatos import (
    CandidatoMezcla,
    aplicar_candidato,
    preparar_panel,
    successive_halving,
)


def _fuente() -> pd.DataFrame:
    filas = []
    for campania, inicio in (("C2025", "2025-01-06"), ("C2026", "2026-03-02")):
        for semana in range(8):
            objetivo = pd.Timestamp(inicio) + pd.Timedelta(weeks=semana)
            emision = objetivo - pd.Timedelta(days=7)
            real = 100 + 10 * semana
            for lote_id in (1, 2):
                for modelo, pred in (
                    ("MacroLegacy_v1", real * 0.8 / 2),
                    ("HibridoOcurrenciaOnline_v2", real * 0.95 / 2),
                ):
                    filas.append(
                        {
                            "evaluation_contract_id": 1 if campania == "C2025" else 2,
                            "campania": campania,
                            "fecha_emision": emision,
                            "fecha_objetivo": objetivo,
                            "lote_id": lote_id,
                            "modelo": modelo,
                            "p50_kg": pred,
                            "real_kg": real / 2,
                        }
                    )
    return pd.DataFrame(filas)


def test_preparar_panel_rechaza_emision_contemporanea():
    tabla = _fuente()
    tabla.loc[0, "fecha_emision"] = tabla.loc[0, "fecha_objetivo"]
    with pytest.raises(ValueError, match="contemporánea"):
        preparar_panel(tabla)


def test_peso_online_no_usa_resultado_de_la_semana_actual():
    panel = preparar_panel(_fuente())
    candidato = CandidatoMezcla("online", "online", ventana=3, regularizacion=4)
    original = aplicar_candidato(panel, candidato)
    mutado = panel.copy()
    ultima = mutado.fecha_objetivo.max()
    mutado.loc[mutado.fecha_objetivo.eq(ultima), "real_kg"] *= 100
    nuevo = aplicar_candidato(mutado, candidato)
    columnas = ["campania", "fecha_objetivo", "lote_id", "pred_kg"]
    pd.testing.assert_frame_equal(
        original.loc[original.fecha_objetivo.eq(ultima), columnas].reset_index(drop=True),
        nuevo.loc[nuevo.fecha_objetivo.eq(ultima), columnas].reset_index(drop=True),
    )


def test_successive_halving_es_candidate_only_y_valida_otra_campania():
    panel = preparar_panel(_fuente())
    candidatos = [
        CandidatoMezcla("macro", "fijo", peso_fijo=1.0, peso_max=1.0),
        CandidatoMezcla("hibrido", "fijo", peso_fijo=0.5),
    ]
    resultado = successive_halving(panel, candidatos)
    assert resultado["campania_desarrollo"] == "C2025"
    assert resultado["campania_validacion"] == "C2026"
    assert resultado["decision"]["publicable"] is False
    assert len(resultado["rondas"]) == 3
