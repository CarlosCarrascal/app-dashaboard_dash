"""El catálogo y el DDL de `raw` deben describir lo mismo.

Son dos artefactos distintos por una razón: el SQL es la fuente de verdad de la estructura y
el catálogo la del mapeo de nombres. Pero si divergen, la carga falla a mitad de camino con un
error de columna inexistente. Esta prueba lo detecta antes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aquanqa_etl.catalogo import (
    CATALOGO_ACCESS,
    MAESTRO_LOTES_COLUMNAS,
    MAESTRO_LOTES_DESTINO,
    total_filas_esperadas,
)
from aquanqa_etl.config import raiz_repo

DIR_SQL_RAW = raiz_repo() / "packages" / "db" / "sql" / "10_raw"

TOTAL_REAL = 654_598
"""Suma verificada de las 18 tablas del origen (hallazgo N-10).

Los cuatro documentos de auditoría publican 683.180 como total de la base, en su encabezado
de alcance, su resumen ejecutivo y sus cifras de control. Esa cifra está mal: los recuentos
tabla por tabla son todos correctos, pero su suma es 654.598. La diferencia es de 28.582
filas (4,4%), y no corresponde a ninguna tabla — es un error aritmético.
"""


def _columnas_declaradas_en_sql() -> dict[str, list[str]]:
    """Extrae {tabla: [columnas]} de los CREATE TABLE de 10_raw."""
    tablas: dict[str, list[str]] = {}
    patron = re.compile(
        r"CREATE TABLE IF NOT EXISTS raw\.(\w+)\s*\((.*?)\n\);",
        re.DOTALL | re.IGNORECASE,
    )
    for archivo in sorted(DIR_SQL_RAW.glob("*.sql")):
        contenido = archivo.read_text(encoding="utf-8")
        for nombre, cuerpo in patron.findall(contenido):
            columnas = []
            for linea in cuerpo.splitlines():
                limpia = linea.split("--")[0].strip()
                if not limpia or limpia.startswith(("PRIMARY", "UNIQUE", "CONSTRAINT", "CHECK")):
                    continue
                col = limpia.split()[0].strip('",')
                if col:
                    columnas.append(col)
            tablas[nombre] = columnas
    return tablas


@pytest.fixture(scope="module")
def sql_raw() -> dict[str, list[str]]:
    declaradas = _columnas_declaradas_en_sql()
    assert declaradas, f"No se encontró ningún CREATE TABLE en {DIR_SQL_RAW}"
    return declaradas


def test_toda_tabla_del_catalogo_existe_en_el_ddl(sql_raw):
    faltan = [t.destino for t in CATALOGO_ACCESS if t.destino not in sql_raw]
    assert not faltan, f"El catálogo apunta a tablas que el DDL no crea: {faltan}"


def test_maestro_vigente_existe_en_el_ddl(sql_raw):
    assert MAESTRO_LOTES_DESTINO in sql_raw


@pytest.mark.parametrize("tabla", CATALOGO_ACCESS, ids=lambda t: t.destino)
def test_columnas_coinciden_con_el_ddl(tabla, sql_raw):
    en_ddl = sql_raw[tabla.destino]
    en_catalogo = list(tabla.cols_destino)
    assert en_catalogo == en_ddl, (
        f"raw.{tabla.destino}: el catálogo y el DDL no coinciden.\n"
        f"  catálogo: {en_catalogo}\n"
        f"  DDL:      {en_ddl}"
    )


def test_maestro_columnas_coinciden(sql_raw):
    assert [d for _, d in MAESTRO_LOTES_COLUMNAS] == sql_raw[MAESTRO_LOTES_DESTINO]


def test_el_total_esperado_es_el_verificado_no_el_publicado():
    """Protege contra "corregir" el catálogo para que cuadre con la cifra publicada."""
    assert total_filas_esperadas() == TOTAL_REAL
    assert total_filas_esperadas() != 683_180, (
        "683.180 es la cifra equivocada de los documentos de auditoría (N-10). "
        "El total real de las 18 tablas es 654.598."
    )


def test_no_hay_destinos_repetidos():
    destinos = [t.destino for t in CATALOGO_ACCESS]
    assert len(destinos) == len(set(destinos))


def test_no_hay_columnas_destino_repetidas_en_una_tabla():
    for tabla in CATALOGO_ACCESS:
        cols = list(tabla.cols_destino)
        repetidas = {c for c in cols if cols.count(c) > 1}
        assert not repetidas, f"raw.{tabla.destino} repite columnas: {repetidas}"


def test_los_nombres_de_origen_van_entre_corchetes():
    """Las columnas con espacios, # o acentos solo funcionan entrecomilladas en Jet/ACE."""
    for tabla in CATALOGO_ACCESS:
        sql = tabla.select()
        for col in tabla.cols_origen:
            assert f"[{col}]" in sql, f"{tabla.origen}.{col} no se entrecomilla en el SELECT"
        assert f"FROM [{tabla.origen}]" in sql


def test_columnas_destino_son_ascii_snake_case():
    """En raw los nombres son ASCII: el nombre original vive en el COMMENT del DDL."""
    patron = re.compile(r"^[a-z][a-z0-9_]*$")
    for tabla in CATALOGO_ACCESS:
        for col in tabla.cols_destino:
            assert patron.match(col), f"raw.{tabla.destino}.{col} no es snake_case ASCII"


def test_el_ddl_documenta_cada_tabla():
    """Sin COMMENT, dentro de un año nadie sabrá qué era [# Ramas]."""
    contenido = "\n".join(a.read_text(encoding="utf-8") for a in sorted(DIR_SQL_RAW.glob("*.sql")))
    sin_comentario = [
        t.destino for t in CATALOGO_ACCESS if f"COMMENT ON TABLE raw.{t.destino}" not in contenido
    ]
    assert not sin_comentario, f"Tablas de raw sin COMMENT: {sin_comentario}"


def test_las_tablas_descartadas_no_estan_en_el_catalogo():
    from aquanqa_etl.catalogo import DESCARTADAS

    origenes = {t.origen for t in CATALOGO_ACCESS}
    assert not (origenes & set(DESCARTADAS)), "Una tabla descartada sigue en el catálogo"


def test_ruta_del_repo_se_resuelve():
    raiz = raiz_repo()
    assert (raiz / "package.json").exists()
    assert (raiz / "packages" / "db").is_dir()


def test_ddl_sin_bom():
    """Un BOM en un .sql rompe psql y corrompe los nombres con ñ de las vistas."""
    for archivo in sorted(Path(DIR_SQL_RAW).glob("*.sql")):
        assert not archivo.read_bytes().startswith(b"\xef\xbb\xbf"), f"{archivo.name} tiene BOM"
