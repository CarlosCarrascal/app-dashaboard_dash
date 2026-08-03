"""Carga de los CSV extraídos al esquema `raw`.

`raw` es una foto completa del origen, así que cada carga hace `TRUNCATE` y vuelve a copiar:
es idempotente por construcción y una segunda ejecución no puede duplicar nada — que es
precisamente el defecto que originó H-03 y H-08.

Toda carga deja constancia en `raw.carga_log` con su recuento y su veredicto contra la cifra
publicada en la auditoría.
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from aquanqa_etl.catalogo import (
    CATALOGO_ACCESS,
    MAESTRO_LOTES_DESTINO,
    MAESTRO_LOTES_FILAS_ESPERADAS,
    TOTAL_FILAS_ORIGEN,
)
from aquanqa_etl.config import Config

# Tablas que no vienen de Access, con su origen y su cifra esperada (None = sin referencia).
EXTERNAS: dict[str, tuple[str, str, int | None]] = {
    MAESTRO_LOTES_DESTINO: ("M_Lotes.xlsx", "xlsx", MAESTRO_LOTES_FILAS_ESPERADAS),
    "tareo": ("Query Tareo 2026.xlsx", "xlsx", None),
}


@dataclass(frozen=True, slots=True)
class ResultadoCarga:
    tabla: str
    filas: int
    esperadas: int | None
    estado: str

    @property
    def desviacion(self) -> int | None:
        return None if self.esperadas is None else self.filas - self.esperadas


def _columnas_de(conexion, tabla: str) -> list[str]:
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'raw' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (tabla,),
        )
        return [f[0] for f in cur.fetchall()]


def _cabecera_csv(ruta: Path) -> list[str]:
    with ruta.open("r", encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))


def _copiar(conexion, tabla: str, ruta: Path, columnas: list[str]) -> int:
    lista = ", ".join(f'"{c}"' for c in columnas)
    sql = f"COPY raw.{tabla} ({lista}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with conexion.cursor() as cur:
        cur.execute(f"TRUNCATE raw.{tabla}")
        with cur.copy(sql) as copia, ruta.open("rb") as fh:
            while bloque := fh.read(1 << 20):
                copia.write(bloque)
        cur.execute(f"SELECT count(*) FROM raw.{tabla}")
        fila = cur.fetchone()
        return int(fila[0]) if fila else 0


def _registrar_log(
    conexion,
    *,
    tabla: str,
    objeto_origen: str,
    origen: str,
    ruta_origen: str,
    filas: int,
    esperadas: int | None,
    estado: str,
    detalle: str | None,
) -> None:
    with conexion.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw.carga_log
                (tabla_destino, objeto_origen, origen, ruta_origen,
                 filas_cargadas, filas_esperadas, extraido_en, estado, detalle)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tabla,
                objeto_origen,
                origen,
                ruta_origen,
                filas,
                esperadas,
                dt.datetime.now(dt.UTC),
                estado,
                detalle,
            ),
        )


def cargar_raw(
    config: Config,
    solo: set[str] | None = None,
    registrar=print,
) -> list[ResultadoCarga]:
    """Carga a `raw` todos los CSV presentes en el directorio de extracción."""
    import psycopg

    previstas: dict[str, tuple[str, str, int | None]] = {
        t.destino: (t.origen, "access", t.filas_esperadas) for t in CATALOGO_ACCESS
    }
    previstas.update(EXTERNAS)

    resultados: list[ResultadoCarga] = []
    with psycopg.connect(config.dsn, autocommit=False) as conexion:
        for tabla, (objeto, origen, esperadas) in previstas.items():
            if solo is not None and tabla not in solo:
                continue
            ruta = config.csv_de(tabla)
            if not ruta.exists():
                if tabla in EXTERNAS:
                    registrar(f"  {tabla:<24} sin CSV: se omite (origen opcional)")
                else:
                    registrar(f"  {tabla:<24} SIN CSV — falta extraer")
                continue

            columnas_csv = _cabecera_csv(ruta)
            columnas_tabla = _columnas_de(conexion, tabla)
            if not columnas_tabla:
                raise RuntimeError(
                    f"La tabla raw.{tabla} no existe. Ejecuta primero:  npm run sql 10_raw"
                )
            sobran = [c for c in columnas_csv if c not in columnas_tabla]
            if sobran:
                raise RuntimeError(
                    f"El CSV de {tabla} trae columnas que raw.{tabla} no tiene: {sobran}.\n"
                    "  El catálogo (catalogo.py) y el DDL (packages/db/sql/10_raw) han "
                    "divergido: corrige uno de los dos antes de cargar."
                )

            filas = _copiar(conexion, tabla, ruta, columnas_csv)
            desviacion = None if esperadas is None else filas - esperadas
            estado = "ok" if desviacion in (None, 0) else "desviacion"
            detalle = (
                None
                if estado == "ok"
                else f"Se esperaban {esperadas:,} filas y llegaron {filas:,} ({desviacion:+d})"
            )
            _registrar_log(
                conexion,
                tabla=tabla,
                objeto_origen=objeto,
                origen=origen,
                ruta_origen=str(ruta),
                filas=filas,
                esperadas=esperadas,
                estado=estado,
                detalle=detalle,
            )
            conexion.commit()

            resultados.append(ResultadoCarga(tabla, filas, esperadas, estado))
            marca = "ok" if estado == "ok" else f"DESVIACIÓN {desviacion:+d}"
            registrar(f"  {tabla:<24} {filas:>8,} filas  {marca}")

    return resultados


def resumen_carga(resultados: list[ResultadoCarga], registrar=print) -> bool:
    """Imprime el total y devuelve True si todas las tablas cuadran con la auditoría."""
    total = sum(r.filas for r in resultados)
    de_access = sum(r.filas for r in resultados if r.tabla not in EXTERNAS)
    desviadas = [r for r in resultados if r.estado != "ok"]

    registrar("")
    registrar(f"Total cargado: {total:,} filas ({len(resultados)} tablas)")
    registrar(f"  de Access:   {de_access:,}  —  el origen verificado tiene {TOTAL_FILAS_ORIGEN:,}")

    if de_access == TOTAL_FILAS_ORIGEN:
        registrar("  ✓ raw reproduce exactamente el origen")
        registrar(
            "    (los documentos de auditoría publican 683.180; esa suma está mal, "
            "ver hallazgo N-10)"
        )
    elif not desviadas:
        registrar(f"  · diferencia con el origen: {de_access - TOTAL_FILAS_ORIGEN:+,}")

    if desviadas:
        registrar("")
        registrar("  Tablas con desviación — repetir su extracción antes de continuar:")
        for r in desviadas:
            registrar(f"    {r.tabla}: {r.filas:,} frente a {r.esperadas:,} ({r.desviacion:+d})")
    return not desviadas
