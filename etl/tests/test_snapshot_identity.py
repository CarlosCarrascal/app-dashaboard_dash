from aquanqa_etl.catalogo import CATALOGO_ACCESS, CATALOGO_VERSION
from aquanqa_etl.load import _snapshot_access_cubre
from aquanqa_etl.snapshots import _campania_coincide

DESTINOS = {tabla.destino for tabla in CATALOGO_ACCESS}


def _contrato_raw_vigente():
    return {
        "version": CATALOGO_VERSION,
        "estado": "completo",
        "columnas_no_mapeadas": [],
    }


def test_snapshot_parcial_no_se_reutiliza_para_carga_completa():
    parcial = {
        "alcance": "parcial",
        "snapshot_completo": False,
        "tablas": {"e01_ramas": {}},
        "catalogo_version": CATALOGO_VERSION,
        "contrato_raw": _contrato_raw_vigente(),
    }

    assert not _snapshot_access_cubre(
        parcial,
        solo=None,
        destinos_catalogo=DESTINOS,
    )


def test_snapshot_completo_se_puede_reutilizar_para_una_tabla():
    completo = {
        "alcance": "completo",
        "snapshot_completo": True,
        "tablas": {destino: {} for destino in DESTINOS},
        "catalogo_version": CATALOGO_VERSION,
        "contrato_raw": _contrato_raw_vigente(),
    }

    assert _snapshot_access_cubre(
        completo,
        solo={"e01_ramas"},
        destinos_catalogo=DESTINOS,
    )


def test_snapshot_parcial_cubre_solo_las_tablas_extraidas():
    parcial = {
        "alcance": "parcial",
        "snapshot_completo": False,
        "tablas": {"e01_ramas": {}, "e02_conteo_flores": {}},
        "catalogo_version": CATALOGO_VERSION,
        "contrato_raw": _contrato_raw_vigente(),
    }

    assert _snapshot_access_cubre(
        parcial,
        solo={"e01_ramas"},
        destinos_catalogo=DESTINOS,
    )
    assert not _snapshot_access_cubre(
        parcial,
        solo={"e01_ramas", "e03_conteo_estados"},
        destinos_catalogo=DESTINOS,
    )


def test_snapshot_no_cruza_campanias():
    assert _campania_coincide("C2026", "c2026")
    assert not _campania_coincide("C2025", "C2026")
    assert not _campania_coincide(None, "C2026")
