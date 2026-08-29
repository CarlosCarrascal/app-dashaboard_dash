from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from aquanqa_etl.config import Config
from aquanqa_etl.extract.access import (
    ResultadoExtraccion,
    _guardar_manifiesto_access,
    extraer_access,
)
from aquanqa_etl.load import _validar_snapshot_access


def _config(tmp_path):
    access_db = tmp_path / "BD_AQUANQA_26.accdb"
    access_db.write_bytes(b"access-fixture")
    return Config(
        access_db=access_db,
        access_campania="C2026",
        access_por_campania={"C2026": access_db},
        maestro_lotes=tmp_path / "M_Lotes.xlsx",
        tareo=tmp_path / "Tareo.xlsx",
        dir_extraccion=tmp_path / "salida",
        pg_host="localhost",
        pg_port=5432,
        pg_database="aquanqa",
        pg_user="postgres",
        pg_password="",
    )


def test_manifiesto_declara_extraccion_parcial(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    resultado = ResultadoExtraccion(
        tabla="E01_Ramas",
        destino="e01_ramas",
        filas=3,
        ruta_csv=config.csv_de("e01_ramas"),
        esperadas=3,
        extraido_en=datetime.now(UTC),
        sha256_csv="abc",
    )

    ruta = _guardar_manifiesto_access(config, [resultado], {"filas": 0})
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))

    assert manifiesto["alcance"] == "parcial"
    assert manifiesto["snapshot_completo"] is False
    assert manifiesto["tablas_catalogo"] == 23
    assert manifiesto["tablas_extraidas"] == 1
    assert "e01_ramas" not in manifiesto["tablas_omitidas"]
    assert len(manifiesto["tablas_omitidas"]) == 22


def test_manifiesto_declara_extraccion_completa(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    from aquanqa_etl.catalogo import CATALOGO_ACCESS

    resultados = [
        ResultadoExtraccion(
            tabla=tabla.origen,
            destino=tabla.destino,
            filas=0,
            ruta_csv=config.csv_de(tabla.destino),
            esperadas=tabla.filas_esperadas,
            extraido_en=datetime.now(UTC),
        )
        for tabla in CATALOGO_ACCESS
    ]

    ruta = _guardar_manifiesto_access(config, resultados, {"filas": 0})
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))

    assert manifiesto["alcance"] == "completo"
    assert manifiesto["snapshot_completo"] is True
    assert manifiesto["tablas_omitidas"] == []


def test_extraer_access_rechaza_tabla_no_catalogada(tmp_path):
    with pytest.raises(ValueError, match="no reconocidas"):
        extraer_access(_config(tmp_path), solo={"tabla_inexistente"})


def test_carga_completa_rechaza_manifiesto_parcial(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    resultado = ResultadoExtraccion(
        tabla="E01_Ramas",
        destino="e01_ramas",
        filas=3,
        ruta_csv=config.csv_de("e01_ramas"),
        esperadas=3,
        extraido_en=datetime.now(UTC),
        sha256_csv="abc",
    )
    _guardar_manifiesto_access(config, [resultado], {"filas": 0})

    with pytest.raises(RuntimeError, match="snapshot Access completo"):
        _validar_snapshot_access(config, solo=None)


def test_carga_de_tabla_concreta_permita_manifiesto_parcial(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    ruta_csv = config.csv_de("e01_ramas")
    ruta_csv.write_text("lote_id\n1\n", encoding="utf-8")
    huella = hashlib.sha256(ruta_csv.read_bytes()).hexdigest()
    resultado = ResultadoExtraccion(
        tabla="E01_Ramas",
        destino="e01_ramas",
        filas=3,
        ruta_csv=ruta_csv,
        esperadas=3,
        extraido_en=datetime.now(UTC),
        sha256_csv=huella,
    )
    _guardar_manifiesto_access(config, [resultado], {"filas": 0})

    _validar_snapshot_access(config, solo={"e01_ramas"})


def test_carga_completa_rechaza_csv_faltante_aunque_manifiesto_sea_completo(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    from aquanqa_etl.catalogo import CATALOGO_ACCESS

    resultados = [
        ResultadoExtraccion(
            tabla=tabla.origen,
            destino=tabla.destino,
            filas=0,
            ruta_csv=config.csv_de(tabla.destino),
            esperadas=tabla.filas_esperadas,
            extraido_en=datetime.now(UTC),
        )
        for tabla in CATALOGO_ACCESS
    ]
    _guardar_manifiesto_access(config, resultados, {"filas": 0})

    with pytest.raises(RuntimeError, match="faltan CSV"):
        _validar_snapshot_access(config, solo=None)


def test_carga_completa_permite_access_sin_maestro_externo(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    from aquanqa_etl.catalogo import CATALOGO_ACCESS

    for tabla in CATALOGO_ACCESS:
        config.csv_de(tabla.destino).write_text("\n", encoding="utf-8")
    resultados = [
        ResultadoExtraccion(
            tabla=tabla.origen,
            destino=tabla.destino,
            filas=0,
            ruta_csv=config.csv_de(tabla.destino),
            esperadas=tabla.filas_esperadas,
            extraido_en=datetime.now(UTC),
            sha256_csv=hashlib.sha256(
                config.csv_de(tabla.destino).read_bytes()
            ).hexdigest(),
        )
        for tabla in CATALOGO_ACCESS
    ]
    _guardar_manifiesto_access(config, resultados, {"filas": 0})

    _validar_snapshot_access(config, solo=None)


def test_carga_rechaza_csv_access_alterado_frente_al_manifiesto(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    resultado = ResultadoExtraccion(
        tabla="E01_Ramas",
        destino="e01_ramas",
        filas=1,
        ruta_csv=config.csv_de("e01_ramas"),
        esperadas=1,
        extraido_en=datetime.now(UTC),
        sha256_csv="hash-original",
    )
    _guardar_manifiesto_access(config, [resultado], {"filas": 0})
    config.csv_de("e01_ramas").write_text("lote_id\n1\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="huella"):
        _validar_snapshot_access(config, solo={"e01_ramas"})


def test_carga_rechaza_manifiesto_de_otra_campania(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    resultado = ResultadoExtraccion(
        tabla="E01_Ramas",
        destino="e01_ramas",
        filas=1,
        ruta_csv=config.csv_de("e01_ramas"),
        esperadas=1,
        extraido_en=datetime.now(UTC),
        sha256_csv=None,
    )
    ruta = _guardar_manifiesto_access(config, [resultado], {"filas": 0})
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
    manifiesto["campania"] = "C2025"
    ruta.write_text(json.dumps(manifiesto), encoding="utf-8")

    with pytest.raises(RuntimeError, match="pertenece a la campaña"):
        _validar_snapshot_access(config, solo={"e01_ramas"})


def test_carga_rechaza_manifiesto_sin_campania(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    resultado = ResultadoExtraccion(
        tabla="E01_Ramas",
        destino="e01_ramas",
        filas=1,
        ruta_csv=config.csv_de("e01_ramas"),
        esperadas=1,
        extraido_en=datetime.now(UTC),
        sha256_csv="hash-original",
    )
    ruta = _guardar_manifiesto_access(config, [resultado], {"filas": 0})
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
    manifiesto.pop("campania")
    ruta.write_text(json.dumps(manifiesto), encoding="utf-8")

    with pytest.raises(RuntimeError, match="no declara la campaña"):
        _validar_snapshot_access(config, solo={"e01_ramas"})


def test_carga_rechaza_manifiesto_de_tipo_distinto_de_access(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    resultado = ResultadoExtraccion(
        tabla="E01_Ramas",
        destino="e01_ramas",
        filas=1,
        ruta_csv=config.csv_de("e01_ramas"),
        esperadas=1,
        extraido_en=datetime.now(UTC),
        sha256_csv="hash-original",
    )
    ruta = _guardar_manifiesto_access(config, [resultado], {"filas": 0})
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
    manifiesto["tipo"] = "xlsx"
    ruta.write_text(json.dumps(manifiesto), encoding="utf-8")

    with pytest.raises(RuntimeError, match="tipo='access'"):
        _validar_snapshot_access(config, solo={"e01_ramas"})


def test_carga_completa_rechaza_hash_access_ausente(tmp_path):
    config = _config(tmp_path)
    config.dir_extraccion.mkdir()
    from aquanqa_etl.catalogo import CATALOGO_ACCESS

    resultados = [
        ResultadoExtraccion(
            tabla=tabla.origen,
            destino=tabla.destino,
            filas=0,
            ruta_csv=config.csv_de(tabla.destino),
            esperadas=tabla.filas_esperadas,
            extraido_en=datetime.now(UTC),
        )
        for tabla in CATALOGO_ACCESS
    ]
    _guardar_manifiesto_access(config, resultados, {"filas": 0})
    for tabla in CATALOGO_ACCESS:
        config.csv_de(tabla.destino).write_text("\n", encoding="utf-8")
    config.csv_de("m_lotes_maestro").write_text("\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="no registra la huella"):
        _validar_snapshot_access(config, solo=None)
