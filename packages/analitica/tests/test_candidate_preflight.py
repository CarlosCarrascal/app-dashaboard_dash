from __future__ import annotations

import json

import pandas as pd
from test_fenologico_v1 import _datos

from analitica.proyeccion.candidatos import (
    EXIT_CONTRACT_REJECTED,
    EXIT_OK,
    EXIT_QUALITY_REJECTED,
    CacheCandidate,
    clonar_datos_proyeccion,
    evaluar_preflight,
    json_reproducible,
    obtener_o_construir_cache,
    seleccionar_emisiones_micro_desde_fuente,
    sha256_dataframe,
)
from analitica.scripts import persistir_hibrido_parametros_asof as runner

HORIZONTES = (1, 2, 4, 6)
REFERENCIAS = {
    "MacroLegacy_v1": 76,
    "HibridoOcurrenciaOnline_v2": 76,
    "R09_publicado": 76,
}


def _predicciones(
    modelo: str,
    *,
    factor: float = 1.0,
    omitir_horizonte: int | None = None,
    contemporanea: bool = False,
    parcial: bool = False,
) -> pd.DataFrame:
    emision = pd.Timestamp("2026-01-05")
    filas = []
    for horizonte in HORIZONTES:
        if horizonte == omitir_horizonte:
            continue
        objetivo = emision + pd.to_timedelta(int(horizonte), unit="W")
        filas.append(
            {
                "modelo": modelo,
                "version_modelo": "test-v1",
                "campania": "C2026",
                "lote_id": 1,
                "fecha_emision": objetivo if contemporanea and horizonte == 1 else emision,
                "fecha_objetivo": objetivo,
                "horizonte_semanas": horizonte,
                "p50_kg": 100.0 * factor,
                "real_kg": 100.0,
            }
        )
    if parcial:
        filas.append(
            {
                "modelo": modelo,
                "version_modelo": "test-v1",
                "campania": "C2026",
                "lote_id": 1,
                "fecha_emision": pd.Timestamp("2026-02-23"),
                "fecha_objetivo": pd.Timestamp("2026-03-02"),
                "horizonte_semanas": 1,
                "p50_kg": 100.0 * factor,
                "real_kg": 100.0,
            }
        )
    return pd.DataFrame(filas)


def _baselines(*, parcial: bool = False) -> dict[str, pd.DataFrame]:
    return {modelo: _predicciones(modelo, parcial=parcial) for modelo in REFERENCIAS}


def _cosecha(watermark: str = "2026-02-22") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campania": ["C2026"],
            "fecha": [pd.Timestamp(watermark)],
            "kg": [400.0],
        }
    )


def test_preflight_aprueba_universo_identico_y_json_es_reproducible():
    resultado = evaluar_preflight(
        _predicciones("HibridoParametrosAsOf_v1"),
        _baselines(),
        campania="C2026",
        cosecha=_cosecha(),
        baseline_run_ids=REFERENCIAS,
    )

    assert resultado["exit_code"] == EXIT_OK
    assert resultado["estado"] == "passed"
    assert resultado["metricas"]["candidato"]["wape"] == 0
    assert resultado["horizontes_presentes"] == [1, 2, 4, 6]
    assert json.loads(json_reproducible(resultado))["keyset_sha256"] == resultado["keyset_sha256"]


def test_semana_parcial_se_detecta_y_se_excluye_de_precision():
    resultado = evaluar_preflight(
        _predicciones("HibridoParametrosAsOf_v1", parcial=True),
        _baselines(parcial=True),
        campania="C2026",
        cosecha=_cosecha("2026-03-04"),
        baseline_run_ids=REFERENCIAS,
    )

    assert resultado["exit_code"] == EXIT_OK
    assert resultado["semana_parcial_excluida_filas"] == 1
    assert resultado["metricas"]["candidato"]["n_lote_emision_semana"] == 4


def test_cierre_certificado_prevalece_sobre_un_watermark_real_mas_reciente():
    resultado = evaluar_preflight(
        _predicciones("HibridoParametrosAsOf_v1", parcial=True),
        _baselines(parcial=True),
        campania="C2026",
        cosecha=_cosecha("2026-03-08"),
        baseline_run_ids=REFERENCIAS,
        cerrado_hasta="2026-02-22",
    )

    assert resultado["exit_code"] == EXIT_OK
    assert resultado["watermark_real"] == "2026-02-22T00:00:00"
    assert resultado["watermark_fuente_real"] == "2026-03-08T00:00:00"
    assert resultado["metricas"]["candidato"]["n_lote_emision_semana"] == 4


def test_emision_contemporanea_y_hash_de_universo_distinto_rechazan_contrato():
    resultado = evaluar_preflight(
        _predicciones("HibridoParametrosAsOf_v1", contemporanea=True),
        _baselines(),
        campania="C2026",
        cosecha=_cosecha(),
        baseline_run_ids=REFERENCIAS,
        expected_keyset_sha256="0" * 64,
    )

    assert resultado["exit_code"] == EXIT_CONTRACT_REJECTED
    reglas = {fila["regla"] for fila in resultado["contratos"]}
    assert "emision_estrictamente_anterior" in reglas
    assert "universo_inmutable" in reglas


def test_entrada_invalida_no_se_convierte_en_ausencia():
    candidato = _predicciones("HibridoParametrosAsOf_v1")
    candidato["p50_kg"] = candidato["p50_kg"].astype(object)
    candidato.loc[0, "p50_kg"] = "no-numérico"
    resultado = evaluar_preflight(
        candidato,
        _baselines(),
        campania="C2026",
        cosecha=_cosecha(),
        baseline_run_ids=REFERENCIAS,
    )
    assert resultado["exit_code"] == EXIT_CONTRACT_REJECTED
    assert any(fila["regla"] == "p50_kg_valido" for fila in resultado["contratos"])


def test_falta_de_cobertura_no_desaparece_del_denominador():
    candidato = _predicciones("HibridoParametrosAsOf_v1")
    candidato = candidato[candidato.horizonte_semanas.ne(4)].copy()
    # El horizonte sigue representado por otro lote, pero falta la mitad del volumen.
    extra = _predicciones("HibridoParametrosAsOf_v1")
    extra["lote_id"] = 2
    candidato = pd.concat([candidato, extra], ignore_index=True)
    baselines = _baselines()
    for modelo, tabla in baselines.items():
        segundo = tabla.copy()
        segundo["lote_id"] = 2
        baselines[modelo] = pd.concat([tabla, segundo], ignore_index=True)

    resultado = evaluar_preflight(
        candidato,
        baselines,
        campania="C2026",
        cosecha=_cosecha(),
        baseline_run_ids=REFERENCIAS,
    )

    assert resultado["exit_code"] == EXIT_QUALITY_REJECTED
    assert resultado["metricas"]["candidato"]["cobertura_volumen"] == 0.875
    assert any(
        gate["regla"] == "cobertura_volumen" and not gate["pasa"] for gate in resultado["gates"]
    )


def test_hpa_malo_se_rechaza_en_micro_replay_antes_de_persistir():
    resultado = evaluar_preflight(
        _predicciones("HibridoParametrosAsOf_v1", factor=2.5),
        _baselines(),
        campania="C2026",
        cosecha=_cosecha(),
        baseline_run_ids=REFERENCIAS,
    )

    assert resultado["exit_code"] == EXIT_QUALITY_REJECTED
    assert resultado["metricas"]["candidato"]["wape"] == 1.5
    rechazadas = {gate["regla"] for gate in resultado["gates"] if not gate["pasa"]}
    assert {"wape_absoluto", "sesgo_absoluto", "deterioro_global_macro"} <= rechazadas


def test_prior_excel_se_aplica_al_clon_y_no_muta_el_contrato_original(monkeypatch):
    original = _datos()
    original.parametros_legacy = pd.DataFrame({"lote_id": [99], "X1": [200.0]})
    clon = clonar_datos_proyeccion(original)
    parametros = pd.DataFrame({"lote_id": [1], "X1": [220.0]})
    manifiesto = pd.DataFrame({"archivo": ["S01.xlsx"]})
    faltantes = pd.DataFrame(columns=["fundo"])
    monkeypatch.setattr(
        runner,
        "cargar_parametros_historicos",
        lambda *args, **kwargs: (parametros, manifiesto, faltantes),
    )

    runner._cargar_priors_excel(
        clon,
        pd.DataFrame({"fecha_emision": [pd.Timestamp("2026-01-05")]}),
        "ignorado",
    )

    assert original.parametros_legacy.to_dict("records") == [{"lote_id": 99, "X1": 200.0}]
    assert clon.parametros_legacy.to_dict("records") == [{"lote_id": 1, "X1": 220.0}]


def test_seleccion_micro_es_determinista_y_cache_reutiliza_resultado(tmp_path):
    emisiones = pd.DataFrame(
        {
            "campania": ["C2026"] * 6,
            "fecha_emision": pd.date_range("2026-01-05", periods=6, freq="7D"),
        }
    )
    cosecha = pd.DataFrame(
        {
            "campania": ["C2026"] * 7,
                "fecha": pd.date_range("2026-01-12", periods=7, freq="7D")
                + pd.to_timedelta(6, unit="D"),
            "kg": [10, 20, 40, 80, 40, 20, 10],
        }
    )
    primera = seleccionar_emisiones_micro_desde_fuente(emisiones, cosecha, "C2026")
    segunda = seleccionar_emisiones_micro_desde_fuente(emisiones, cosecha, "C2026")
    pd.testing.assert_frame_equal(primera, segunda)

    cache = CacheCandidate(tmp_path)
    llamadas = 0

    def constructor():
        nonlocal llamadas
        llamadas += 1
        pred = _predicciones("HibridoParametrosAsOf_v1")
        return pred, pd.DataFrame({"x": [1]}), {"schema": "test"}

    uno = obtener_o_construir_cache(cache, "abc", constructor)
    dos = obtener_o_construir_cache(cache, "abc", constructor)
    assert llamadas == 1
    assert uno[2]["cache_hit"] is False
    assert dos[2]["cache_hit"] is True
    assert sha256_dataframe(uno[0], ["lote_id", "p50_kg"]) == sha256_dataframe(
        dos[0], ["lote_id", "p50_kg"]
    )


def test_cache_corrupta_se_reconstruye(tmp_path):
    cache = CacheCandidate(tmp_path)
    clave = "corrupta"
    pred = _predicciones("HibridoParametrosAsOf_v1")
    cache.guardar(clave, pred, pd.DataFrame({"x": [1]}), {"schema": "test"})
    (tmp_path / f"{clave}.pkl.gz").write_bytes(b"no es pickle")

    llamadas = 0

    def constructor():
        nonlocal llamadas
        llamadas += 1
        return pred, pd.DataFrame({"x": [1]}), {"schema": "test"}

    resultado = obtener_o_construir_cache(cache, clave, constructor)
    assert llamadas == 1
    assert resultado[2]["cache_hit"] is False
