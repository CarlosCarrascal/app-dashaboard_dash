from __future__ import annotations

from aquanqa_etl.extract.access import (
    _catalogo_dao_no_disponible,
    _enriquecer_consultas_dao,
)


def test_catalogo_dao_no_disponible_es_explicito():
    catalogo = _catalogo_dao_no_disponible("DAO no instalado")
    assert catalogo["backend"] == "dao"
    assert catalogo["estado"] == "no_disponible"
    assert catalogo["relaciones"] == []
    assert catalogo["querydefs"] == []


def test_querydefs_dao_conserva_sql_y_dependencias():
    consultas = _enriquecer_consultas_dao(
        [{"nombre": "Consulta existente", "estado": "ejecutable"}],
        {
            "estado": "disponible",
            "querydefs": [
                {
                    "nombre": "Consulta existente",
                    "tipo_objeto": "QUERYDEF",
                    "definicion_sql": "SELECT * FROM M_Lotes;",
                    "dependencias": ["M_Lotes"],
                    "tipo_codigo": 0,
                },
                {
                    "nombre": "Consulta nueva",
                    "definicion_sql": "SELECT * FROM E01_Ramas;",
                    "dependencias": ["E01_Ramas"],
                },
            ],
        },
    )

    por_nombre = {consulta["nombre"]: consulta for consulta in consultas}
    assert por_nombre["Consulta existente"]["definicion_sql"] == "SELECT * FROM M_Lotes;"
    assert por_nombre["Consulta existente"]["dependencias"] == ["M_Lotes"]
    assert por_nombre["Consulta nueva"]["backend"] == "dao"
    assert por_nombre["Consulta nueva"]["dependencias"] == ["E01_Ramas"]
