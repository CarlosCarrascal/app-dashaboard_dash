from pathlib import Path

import pandas as pd

from servicios import reporting

ROOT = Path(__file__).parents[1]


def test_los_servicios_de_pagina_no_conocen_stg_ni_dim():
    for nombre in ("analytics.py", "proyeccion.py"):
        codigo = (ROOT / "servicios" / nombre).read_text(encoding="utf-8")
        assert "FROM stg." not in codigo
        assert "FROM dim." not in codigo
        assert "JOIN stg." not in codigo
        assert "JOIN dim." not in codigo


def test_la_fachada_reporting_declara_las_lecturas_heredadas():
    codigo = (ROOT / "servicios" / "reporting.py").read_text(encoding="utf-8")
    assert "cosecha_real_analitica" in codigo
    assert "cosecha_real_operativa" in codigo
    assert "r09_referencia" in codigo
    assert "substring(r.campania from '[0-9]{4}')" in codigo
    assert "substring(r.campania from '\\\\d{4}')" not in codigo
    assert "snapshot_por_campania" in codigo
    assert 'tabla["snapshot_id"] = tabla["campania"].map' in codigo


def test_r09_asocia_snapshot_por_campania_y_conserva_vinculo_parcial(monkeypatch):
    fuente = pd.DataFrame(
        {
            "campania": ["C2025", "C2026"],
            "source_snapshot_id": [10, 20],
        }
    )
    snapshots = pd.DataFrame(
        {
            "snapshot_id": [900],
            "source_snapshot_id": [10],
        }
    )
    r09 = pd.DataFrame(
        {
            "campania": ["C2025", "C2026"],
            "snapshot_id": [None, None],
        }
    )

    def consulta_falsa(_conexion, relacion, _sql):
        if relacion == "raw.v_ultimo_snapshot_fuente":
            return fuente
        if relacion == "analytics.dataset_snapshot":
            return snapshots
        if relacion == "stg.v_r09_forecast":
            return r09
        raise AssertionError(relacion)

    monkeypatch.setattr(reporting, "consulta_si_existe", consulta_falsa)

    salida = reporting.r09_referencia(object())

    assert salida.loc[0, "snapshot_id"] == 900
    assert pd.isna(salida.loc[1, "snapshot_id"])
    assert str(salida["snapshot_id"].dtype) == "Int64"


def test_r09_sin_snapshots_access_no_inventa_ids(monkeypatch):
    r09 = pd.DataFrame(
        {
            "campania": ["C2026"],
            "snapshot_id": [None],
        }
    )

    def consulta_falsa(_conexion, relacion, _sql):
        if relacion == "raw.v_ultimo_snapshot_fuente":
            return pd.DataFrame(columns=["campania", "source_snapshot_id"])
        if relacion == "stg.v_r09_forecast":
            return r09
        raise AssertionError(relacion)

    monkeypatch.setattr(reporting, "consulta_si_existe", consulta_falsa)

    salida = reporting.r09_referencia(object())

    assert salida.loc[0, "snapshot_id"] is None
