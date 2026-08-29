from __future__ import annotations

from aquanqa_etl.catalogo import CATALOGO_ACCESS
from aquanqa_etl.modelo import (
    BLOQUES_MODELO,
    MODELO_VERSION,
    RELACIONES_MODELO,
    TABLAS_MODELO,
    hash_modelo,
    payload_modelo,
    validar_modelo,
)


def test_modelo_cubre_exactamente_las_fuentes_access():
    validar_modelo()
    fuentes = {tabla.destino for tabla in CATALOGO_ACCESS}
    assert {tabla.tabla_raw for tabla in TABLAS_MODELO} == fuentes
    assert sum(len(bloque.tablas_raw) for bloque in BLOQUES_MODELO) == len(fuentes)


def test_una_fuente_pertenece_a_un_solo_bloque():
    fuentes = [tabla for bloque in BLOQUES_MODELO for tabla in bloque.tablas_raw]
    assert len(fuentes) == len(set(fuentes))


def test_raw_only_no_finge_un_destino_core():
    pendientes = {tabla.tabla_raw for tabla in TABLAS_MODELO if tabla.decision == "raw_only"}
    assert pendientes == {
        "h01_detalle_cosecha",
        "m_presupuesto_mo",
        "r08_forecast_campania_24",
        "r08_forecast_campania_25",
        "r09_forecast_semanal_25",
    }
    assert all(not tabla.core_objetos for tabla in TABLAS_MODELO if tabla.tabla_raw in pendientes)


def test_access_m_lotes_es_la_unica_fuente_maestra_principal():
    maestros = [tabla.tabla_raw for tabla in TABLAS_MODELO if tabla.fuente_maestra]
    assert maestros == ["m_lotes"]
    assert next(tabla for tabla in TABLAS_MODELO if tabla.tabla_raw == "m_lotes").decision == "core"


def test_relaciones_no_repite_codigo_y_conserva_columnas_balanceadas():
    codigos = [relacion.codigo for relacion in RELACIONES_MODELO]
    assert len(codigos) == len(set(codigos))
    assert all(
        len(relacion.columnas_padre) == len(relacion.columnas_hijo)
        for relacion in RELACIONES_MODELO
    )


def test_contrato_semantico_es_determinista():
    assert payload_modelo(MODELO_VERSION) == payload_modelo(MODELO_VERSION)
    assert hash_modelo(MODELO_VERSION) == hash_modelo(MODELO_VERSION)
    assert len(hash_modelo(MODELO_VERSION)) == 64
