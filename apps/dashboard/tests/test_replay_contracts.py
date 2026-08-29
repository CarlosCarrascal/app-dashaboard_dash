"""Contratos temporales y de certificación del replay de Proyección."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from pages.analitica.proyeccion_domain import (
    alinear_replay_con_real_comun,
    seleccionar_emision_coherente,
)
from servicios import proyeccion as servicio_proyeccion
from servicios.proyeccion import (
    R09_REGLA_VARIANTES,
    _certificacion_disponible,
    _validar_un_contrato_por_campania,
    es_version_r09_canonica,
)


def test_semana_parcial_se_excluye_antes_de_completar_ceros():
    predicciones = pd.DataFrame(
        {
            "modelo": ["R09_publicado", "R09_publicado"],
            "campania": ["C2026", "C2026"],
            "lote_id": [1, 1],
            "fecha_emision": [pd.Timestamp("2026-08-03"), pd.Timestamp("2026-08-10")],
            "fecha_objetivo": [pd.Timestamp("2026-08-10"), pd.Timestamp("2026-08-17")],
            "horizonte_semanas": [1, 1],
            "p50_kg": [110.0, 900.0],
            "real_kg": [100.0, None],
        }
    )
    # El servicio real solo entrega períodos cerrados. La semana 17–23/08 todavía
    # no pertenece a este calendario y no puede convertirse en real igual a cero.
    reales_cerrados = pd.DataFrame(
        {
            "campania": ["C2026"],
            "lote_id": [1],
            "fecha_objetivo": [pd.Timestamp("2026-08-10")],
            "real_kg": [100.0],
        }
    )

    alineado = alinear_replay_con_real_comun(predicciones, reales_cerrados, "R09_publicado")

    assert alineado["fecha_objetivo"].tolist() == [pd.Timestamp("2026-08-10")]
    assert alineado["real_kg"].sum() == 100.0
    assert alineado["p50_kg"].sum() == 110.0


def test_vintage_se_elige_por_semana_y_no_por_lote():
    tabla = pd.DataFrame(
        {
            "modelo": ["R09_publicado"] * 5,
            "campania": ["C2026"] * 5,
            "lote_id": [1, 2, 1, 2, 1],
            "fecha_emision": pd.to_datetime(
                ["2026-08-03", "2026-08-03", "2026-08-10", "2026-08-10", "2026-08-17"]
            ),
            "fecha_objetivo": pd.to_datetime(["2026-08-17"] * 5),
            "horizonte_semanas": [2, 2, 1, 1, 0],
            "p50_kg": [90.0, 80.0, 100.0, 95.0, 999.0],
        }
    )

    elegido = seleccionar_emision_coherente(tabla)

    assert set(elegido["lote_id"]) == {1, 2}
    assert elegido["fecha_emision"].nunique() == 1
    assert elegido["fecha_emision"].iat[0] == pd.Timestamp("2026-08-10")
    assert set(elegido["horizonte_semanas"]) == {1}
    assert elegido["p50_kg"].sum() == 195.0


def test_vintage_no_rellena_lotes_desde_otra_emision():
    tabla = pd.DataFrame(
        {
            "modelo": ["MacroLegacy_v1"] * 3,
            "campania": ["C2026"] * 3,
            "lote_id": [1, 2, 1],
            "fecha_emision": pd.to_datetime(["2026-08-03", "2026-08-03", "2026-08-10"]),
            "fecha_objetivo": pd.to_datetime(["2026-08-17"] * 3),
            "horizonte_semanas": [2, 2, 1],
            "p50_kg": [90.0, 80.0, 100.0],
        }
    )

    elegido = seleccionar_emision_coherente(tabla)

    # El lote 2 queda como ausencia de cobertura del vintage 10/08. Recuperarlo desde
    # 03/08 fabricaría una emisión que nunca existió.
    assert elegido["lote_id"].tolist() == [1]
    assert elegido["fecha_emision"].iat[0] == pd.Timestamp("2026-08-10")


def test_r09_solo_admite_version_base_documentada():
    assert es_version_r09_canonica("S35")
    assert es_version_r09_canonica("s035")
    assert not es_version_r09_canonica("S35_v2")
    assert not es_version_r09_canonica("S35_EDI")
    assert not es_version_r09_canonica("S35 copia")
    assert "promoción explícita" in R09_REGLA_VARIANTES


class _CursorFalso:
    def __init__(self, relaciones: set[str]):
        self.relaciones = relaciones
        self.relacion = ""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, _sql, parametros):
        self.relacion = parametros[0]

    def fetchone(self):
        return (self.relacion if self.relacion in self.relaciones else None,)


class _ConexionFalsa:
    def __init__(self, relaciones: set[str]):
        self.relaciones = relaciones

    def cursor(self):
        return _CursorFalso(self.relaciones)


def test_no_hay_certificacion_si_falta_release_o_contrato():
    assert not _certificacion_disponible(_ConexionFalsa(set()))
    assert not _certificacion_disponible(_ConexionFalsa({"analytics.model_series_release"}))


def test_replay_bloquea_dos_contratos_en_la_misma_campania():
    releases = pd.DataFrame(
        {
            "campania": ["C2026", "C2026", "C2025"],
            "evaluation_contract_id": [1, 2, 3],
        }
    )

    with pytest.raises(ValueError, match="contratos incompatibles"):
        _validar_un_contrato_por_campania(releases)
    assert _certificacion_disponible(
        _ConexionFalsa({"analytics.model_series_release", "analytics.evaluation_contract"})
    )


def test_replay_exige_contrato_de_evaluacion_aprobado():
    codigo = Path(servicio_proyeccion.__file__).read_text(encoding="utf-8")
    assert codigo.count("AND c.estado = 'approved'") >= 2


def test_servicio_sin_release_no_sustituye_con_latest_run(monkeypatch):
    consultas: list[str] = []

    class _ConexionContexto:
        def __enter__(self):
            return object()

        def __exit__(self, *_):
            return False

    def _consulta_falsa(_conexion, _relacion, sql):
        consultas.append(sql)
        return pd.DataFrame(
            {
                "campania": ["C2026"],
                "fecha_objetivo": [pd.Timestamp("2026-08-10")],
                "lote_id": [1],
                "real_kg": [100.0],
            }
        )

    monkeypatch.setattr(servicio_proyeccion.settings, "postgres_dsn", lambda: "postgres://test")
    monkeypatch.setattr(servicio_proyeccion, "_consulta_si_existe", _consulta_falsa)
    monkeypatch.setattr(servicio_proyeccion, "_certificacion_disponible", lambda _: False)
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *_args, **_kwargs: _ConexionContexto()),
    )

    estado = servicio_proyeccion._cache_replay.__wrapped__(0)

    assert estado["certificacion"]["estado"] == "no_certificado"
    assert estado["replay_detalle"].empty
    assert "No se usó la última corrida" in estado["error"]
    # Sin una release aprobada el servicio debe detenerse antes de consultar
    # cosecha o predicciones mutables. Así tampoco puede sustituir el contrato
    # ausente por la última corrida técnicamente exitosa.
    assert consultas == []
