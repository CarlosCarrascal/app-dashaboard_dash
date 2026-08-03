"""Extracción de `BD_AQUANQA_26.accdb` a CSV UTF-8.

La conexión se abre **siempre de solo lectura**: el compromiso de la auditoría es que el
origen no se modifica, y Access puede seguir en uso mientras esto corre.

Sobre la serialización a CSV: se usa `QUOTE_NOTNULL`, que escribe `None` como campo vacío sin
comillas y una cadena vacía como `""`. Eso permite que `COPY ... FORMAT csv` distinga NULL de
cadena vacía, distinción que importa porque las filas de subtotal de H-06 se detectan
precisamente por tener los identificadores nulos.

Los flotantes se escriben con `repr()`, que garantiza ida y vuelta exacta: las cifras de
control de la auditoría llegan a 15 dígitos significativos y no admiten redondeo.
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from aquanqa_etl.catalogo import CATALOGO_ACCESS, DESCARTADAS, Tabla
from aquanqa_etl.config import Config

LOTE_FILAS = 50_000
"""Filas por lote. Suficiente para que el viaje ODBC sea eficiente sin cargar 155.588 filas
de clima en memoria de golpe."""

DRIVERS_ACCESS = (
    "Microsoft Access Driver (*.mdb, *.accdb)",
    "Microsoft Access Driver (*.mdb)",
)


@dataclass(frozen=True, slots=True)
class ResultadoExtraccion:
    tabla: str
    destino: str
    filas: int
    ruta_csv: Path
    esperadas: int | None
    extraido_en: dt.datetime

    @property
    def desviacion(self) -> int | None:
        return None if self.esperadas is None else self.filas - self.esperadas

    @property
    def ok(self) -> bool:
        return self.desviacion in (None, 0)


def _driver_disponible() -> str:
    import pyodbc

    instalados = set(pyodbc.drivers())
    for candidato in DRIVERS_ACCESS:
        if candidato in instalados:
            return candidato
    raise RuntimeError(
        "No hay driver ODBC de Access instalado.\n"
        "  Instala 'Microsoft Access Database Engine 2016 Redistributable' (versión de 64 bits, "
        "para que coincida con el Python de 64 bits).\n"
        f"  Drivers detectados: {sorted(instalados)}"
    )


def conectar(config: Config):
    """Conexión de solo lectura al .accdb."""
    import pyodbc

    if not config.access_db.exists():
        raise FileNotFoundError(
            f"No encuentro la base de origen en {config.access_db}.\n"
            "  Revisa ACCESS_DB_PATH en .env."
        )
    cadena = f"DRIVER={{{_driver_disponible()}}};DBQ={config.access_db};ReadOnly=1;"
    conexion = pyodbc.connect(cadena, autocommit=False, readonly=True)
    # Codificación: pyodbc envía el SQL por SQLExecDirectW, que espera UTF-16LE. Si se le
    # dice que codifique en UTF-8, los nombres con eñe se corrompen y el driver responde
    # "Pocos parámetros. Se esperaba 1" — porque interpreta [Campaña] como un parámetro
    # desconocido en lugar de como una columna. Es el mismo error engañoso que documenta
    # H-04 tipo B, y aquí se manifiesta al leer H00_VolumenCampo, H01_ProdHistorica,
    # M_Poda, R08_Forecast_Campaña y R09_Forecast_Semanal.
    conexion.setencoding(encoding="utf-16le")
    conexion.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-16le")
    conexion.setdecoding(pyodbc.SQL_CHAR, encoding="utf-8")
    return conexion


def _serializar(valor: Any) -> Any:
    """Convierte un valor de ODBC en algo que el CSV pueda representar sin perder nada.

    Devolver `None` es deliberado: con QUOTE_NOTNULL se escribe como campo vacío y `COPY` lo
    interpreta como NULL.
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, float):
        # repr garantiza ida y vuelta exacta del float64.
        return repr(valor)
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dt.datetime):
        return valor.isoformat(sep=" ")
    if isinstance(valor, (dt.date, dt.time)):
        return valor.isoformat()
    if isinstance(valor, (bytes, bytearray)):
        return valor.hex()
    if isinstance(valor, str):
        # Los textos de Access llegan con relleno o con espacios accidentales; el trim de
        # verdad se hace en stg, aquí solo se quitan los saltos de línea que romperían el CSV
        # y que no aportan nada.
        return valor.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return str(valor)


def _extraer_tabla(cursor, tabla: Tabla, destino: Path) -> int:
    cursor.execute(tabla.select())
    filas = 0
    with destino.open("w", encoding="utf-8", newline="") as fh:
        escritor = csv.writer(fh, lineterminator="\n", quoting=csv.QUOTE_NOTNULL)
        escritor.writerow(tabla.cols_destino)
        while True:
            lote = cursor.fetchmany(LOTE_FILAS)
            if not lote:
                break
            escritor.writerows([_serializar(v) for v in fila] for fila in lote)
            filas += len(lote)
    return filas


def extraer_access(
    config: Config,
    solo: set[str] | None = None,
    registrar=print,
) -> list[ResultadoExtraccion]:
    """Extrae las 17 tablas del catálogo a `config.dir_extraccion`.

    `solo` filtra por nombre de destino, para poder repetir una tabla concreta sin volver a
    extraer las 654.598 filas del origen completo.
    """
    config.dir_extraccion.mkdir(parents=True, exist_ok=True)
    tablas = [t for t in CATALOGO_ACCESS if solo is None or t.destino in solo]

    registrar(f"Origen: {config.access_db}")
    registrar(f"Destino: {config.dir_extraccion}")
    registrar(f"Tablas a extraer: {len(tablas)}")
    for objeto, motivo in DESCARTADAS.items():
        registrar(f"  descartado · {objeto}: {motivo}")

    resultados: list[ResultadoExtraccion] = []
    conexion = conectar(config)
    try:
        cursor = conexion.cursor()
        for tabla in tablas:
            inicio = dt.datetime.now(dt.UTC)
            ruta = config.csv_de(tabla.destino)
            filas = _extraer_tabla(cursor, tabla, ruta)
            resultado = ResultadoExtraccion(
                tabla=tabla.origen,
                destino=tabla.destino,
                filas=filas,
                ruta_csv=ruta,
                esperadas=tabla.filas_esperadas,
                extraido_en=inicio,
            )
            resultados.append(resultado)
            marca = "ok" if resultado.ok else f"DESVIACIÓN {resultado.desviacion:+d}"
            registrar(f"  {tabla.origen:<24} {filas:>8,} filas  {marca}")
    finally:
        # Solo lectura: no hay nada que confirmar, y cerrar sin commit deja el .laccdb intacto.
        conexion.close()

    return resultados
