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
import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
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

MANIFIESTO_ACCESS = "access_snapshot.json"
"""Manifiesto reproducible de la copia Access que originó los CSV extraídos."""


@dataclass(frozen=True, slots=True)
class ResultadoExtraccion:
    tabla: str
    destino: str
    filas: int
    ruta_csv: Path
    esperadas: int | None
    extraido_en: dt.datetime
    sha256_csv: str = ""

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


def _resolver_origen(cursor, tabla: Tabla) -> str:
    """Devuelve el nombre real del objeto Access, admitiendo grafías históricas conocidas."""
    for origen in (tabla.origen, *tabla.origen_alternativas):
        try:
            cursor.execute(f"SELECT * FROM [{origen}] WHERE 1=0")
            return origen
        except Exception:
            continue
    nombres = ", ".join((tabla.origen, *tabla.origen_alternativas))
    raise RuntimeError(
        f"No encuentro la tabla Access {nombres}. La copia no cumple el catálogo vigente."
    )


def _resolver_columnas(cursor, tabla: Tabla, origen: str) -> tuple[str | None, ...]:
    """Resuelve alias de columnas sin cambiar el contrato canónico de raw."""
    try:
        disponibles = {
            str(fila.column_name): str(fila.column_name)
            for fila in cursor.columns(table=origen).fetchall()
        }
    except Exception as exc:
        raise RuntimeError(f"No puedo inspeccionar las columnas de Access {origen}: {exc}") from exc
    alias = dict(tabla.columnas_alternativas)
    resueltas = []
    faltantes = []
    for columna in tabla.cols_origen:
        if columna in disponibles:
            resueltas.append(columna)
            continue
        encontrada = next((c for c in alias.get(columna, ()) if c in disponibles), None)
        if encontrada is None:
            if columna in tabla.columnas_opcionales:
                resueltas.append(None)
                continue
            faltantes.append(columna)
        else:
            resueltas.append(encontrada)
    if faltantes:
        raise RuntimeError(
            f"La tabla Access {origen} no tiene las columnas {faltantes}; "
            f"encontradas: {sorted(disponibles)}"
        )
    return tuple(resueltas)


def _schema_descriptor(cursor, origen: str) -> list[dict[str, Any]]:
    """Obtiene una descripción estable de las columnas para detectar cambios de estructura."""
    try:
        filas = cursor.columns(table=origen).fetchall()
    except Exception:
        filas = []
    descriptor = []
    for fila in filas:
        descriptor.append(
            {
                "nombre": getattr(fila, "column_name", None),
                "tipo": getattr(fila, "type_name", None),
                "tipo_codigo": getattr(fila, "data_type", None),
                "tamano": getattr(fila, "column_size", None),
                "digitos_decimales": getattr(fila, "decimal_digits", None),
                "radix": getattr(fila, "num_prec_radix", None),
                "nullable": getattr(fila, "nullable", None),
                "por_defecto": getattr(fila, "column_def", None),
                "posicion": getattr(fila, "ordinal_position", None),
            }
        )
    return descriptor


def _indices_descriptor(cursor, origen: str) -> list[dict[str, Any]]:
    """Obtiene índices Access, incluyendo sus columnas y unicidad."""
    try:
        filas = cursor.statistics(table=origen, unique=False, quick=True).fetchall()
    except Exception as exc:
        return [{"error": f"No se pudo leer statistics(): {exc}"}]
    indices = []
    for fila in filas:
        nombre = getattr(fila, "index_name", None)
        columna = getattr(fila, "column_name", None)
        # statistics() también devuelve una fila de resumen de tabla sin índice/columna.
        if not nombre or not columna:
            continue
        indices.append(
            {
                "nombre": str(nombre),
                "no_unico": getattr(fila, "non_unique", None),
                "tipo": getattr(fila, "type", None),
                "posicion": getattr(fila, "ordinal_position", None),
                "columna": str(columna),
                "orden": getattr(fila, "asc_or_desc", None),
                "cardinalidad": getattr(fila, "cardinality", None),
                "paginas": getattr(fila, "pages", None),
                "filtro": getattr(fila, "filter_condition", None),
            }
        )
    return indices


def _claves_primarias_descriptor(cursor, origen: str) -> list[dict[str, Any]]:
    """Obtiene las claves primarias Access mediante la metadata ODBC."""
    try:
        filas = cursor.primaryKeys(table=origen).fetchall()
    except Exception as exc:
        return [{"error": f"No se pudo leer primaryKeys(): {exc}"}]
    return [
        {
            "nombre": getattr(fila, "pk_name", None),
            "columna": getattr(fila, "column_name", None),
            "posicion": getattr(fila, "key_seq", None),
        }
        for fila in filas
    ]


def _hash_schema(
    esquema: dict[str, list[dict[str, Any]]],
    indices: dict[str, list[dict[str, Any]]] | None = None,
    claves_primarias: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    """Calcula la huella de columnas, índices y claves, no solo de los nombres."""
    contenido = json.dumps(
        {
            "columnas": esquema,
            "indices": indices or {},
            "claves_primarias": claves_primarias or {},
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode()
    return hashlib.sha256(contenido).hexdigest()


def _hash_tabla_schema(
    origen: str,
    esquemas: dict[str, list[dict[str, Any]]],
    indices: dict[str, list[dict[str, Any]]],
    claves_primarias: dict[str, list[dict[str, Any]]],
) -> str:
    """Calcula una huella por tabla para validar el control granular del snapshot."""
    return _hash_schema(
        {origen: esquemas.get(origen, [])},
        {origen: indices.get(origen, [])},
        {origen: claves_primarias.get(origen, [])},
    )


def _catalogo_dao_no_disponible(detalle: str) -> dict[str, Any]:
    return {
        "backend": "dao",
        "estado": "no_disponible",
        "detalle": detalle,
        "tablas": [],
        "relaciones": [],
        "querydefs": [],
    }


def _powershell_executable() -> str | None:
    """Localiza Windows PowerShell o PowerShell 7 sin asumir una instalación concreta."""
    for candidato in ("powershell.exe", "pwsh.exe", "pwsh"):
        ruta = shutil.which(candidato)
        if ruta:
            return ruta
    return None


def _catalogar_access_dao(config: Config, *, require_dao: bool = False) -> dict[str, Any]:
    """Obtiene relaciones y QueryDef.SQL usando DAO, siempre en modo solo lectura.

    ODBC sigue siendo el camino compatible para extraer filas. DAO se intenta como una
    segunda fuente de metadata porque el driver ODBC puede ocultar relaciones o la SQL de
    consultas guardadas. La ausencia de DAO queda declarada en el catálogo y no se disfraza
    como si no existieran relaciones.
    """
    helper = Path(__file__).resolve().parents[4] / "scripts" / "access" / "catalogar-access.ps1"
    powershell = _powershell_executable()
    if powershell is None:
        detalle = "No se encontró powershell.exe ni pwsh para ejecutar el inspector DAO."
        if require_dao:
            raise RuntimeError(detalle)
        return _catalogo_dao_no_disponible(detalle)
    if not helper.is_file():
        detalle = f"No existe el inspector DAO: {helper}"
        if require_dao:
            raise RuntimeError(detalle)
        return _catalogo_dao_no_disponible(detalle)

    try:
        with tempfile.TemporaryDirectory(prefix="aquanqa_dao_") as temporal:
            salida = Path(temporal) / "catalogo_dao.json"
            proceso = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(helper),
                    "-AccessPath",
                    str(config.access_db.resolve()),
                    "-OutputPath",
                    str(salida),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            if proceso.returncode != 0:
                detalle = (proceso.stderr or proceso.stdout or "error desconocido").strip()
                raise RuntimeError(detalle)
            if not salida.is_file():
                raise RuntimeError("El inspector DAO terminó sin producir JSON.")
            catalogo = json.loads(salida.read_text(encoding="utf-8"))
            if not isinstance(catalogo, dict) or catalogo.get("estado") != "disponible":
                raise RuntimeError("El inspector DAO produjo un resultado incompleto.")
            return catalogo
    except Exception as exc:
        detalle = f"No se pudo catalogar Access mediante DAO: {exc}"
        if require_dao:
            raise RuntimeError(detalle) from exc
        return _catalogo_dao_no_disponible(detalle)


def _incorporar_catalogo_dao(
    esquemas: dict[str, list[dict[str, Any]]],
    indices: dict[str, list[dict[str, Any]]],
    claves_primarias: dict[str, list[dict[str, Any]]],
    catalogo_dao: dict[str, Any],
) -> None:
    """Reemplaza metadata ODBC por la más completa de DAO cuando ambas están disponibles."""
    if catalogo_dao.get("estado") != "disponible":
        return
    por_nombre = {
        str(tabla.get("nombre")): tabla
        for tabla in catalogo_dao.get("tablas", [])
        if tabla.get("nombre")
    }
    por_nombre_normalizado = {nombre.casefold(): tabla for nombre, tabla in por_nombre.items()}
    for origen in list(esquemas):
        tabla = por_nombre.get(origen) or por_nombre_normalizado.get(origen.casefold())
        if not tabla:
            continue
        esquemas[origen] = list(tabla.get("campos") or [])
        indices[origen] = list(tabla.get("indices") or [])
        claves_primarias[origen] = [
            {
                "nombre": indice.get("nombre"),
                "columna": campo.get("nombre"),
                "posicion": campo.get("posicion"),
            }
            for indice in tabla.get("indices") or []
            if indice.get("primario")
            for campo in indice.get("campos") or []
        ]


def _enriquecer_consultas_dao(
    consultas: list[dict[str, Any]], catalogo_dao: dict[str, Any]
) -> list[dict[str, Any]]:
    """Añade SQL/dependencias de DAO a las consultas detectadas por ODBC."""
    resultado = {
        str(consulta.get("nombre")): dict(consulta)
        for consulta in consultas
        if consulta.get("nombre")
    }
    if catalogo_dao.get("estado") != "disponible":
        return sorted(resultado.values(), key=lambda x: x.get("nombre") or "")
    for querydef in catalogo_dao.get("querydefs") or []:
        nombre = str(querydef.get("nombre") or "").strip()
        if not nombre or nombre.startswith(("~", "MSys")):
            continue
        consulta = resultado.setdefault(
            nombre,
            {
                "nombre": nombre,
                "tipo_objeto": "QUERYDEF",
                "proposito": _proposito_consulta(nombre),
                "estado": "catalogada",
                "detalle": None,
            },
        )
        consulta.update(
            {
                "tipo_objeto": querydef.get("tipo_objeto") or "QUERYDEF",
                "definicion_sql": querydef.get("definicion_sql") or None,
                "dependencias": list(querydef.get("dependencias") or []),
                "estado": "catalogada",
                "detalle": None,
                "backend": "dao",
                "tipo_codigo": querydef.get("tipo_codigo"),
            }
        )
        consulta.setdefault("proposito", _proposito_consulta(nombre))
    return sorted(resultado.values(), key=lambda x: x.get("nombre") or "")


def _catalogar_tablas(
    cursor, tablas: list[Tabla]
) -> tuple[
    dict[str, str],
    dict[str, tuple[str | None, ...]],
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
]:
    """Inspecciona tablas una vez y devuelve origen, columnas, esquema, índices y PK."""
    origenes: dict[str, str] = {}
    columnas_resueltas: dict[str, tuple[str | None, ...]] = {}
    esquemas: dict[str, list[dict[str, Any]]] = {}
    indices: dict[str, list[dict[str, Any]]] = {}
    claves_primarias: dict[str, list[dict[str, Any]]] = {}
    for tabla in tablas:
        origen = _resolver_origen(cursor, tabla)
        origenes[tabla.destino] = origen
        columnas_resueltas[tabla.destino] = _resolver_columnas(cursor, tabla, origen)
        esquemas[origen] = _schema_descriptor(cursor, origen)
        indices[origen] = _indices_descriptor(cursor, origen)
        claves_primarias[origen] = _claves_primarias_descriptor(cursor, origen)
    return origenes, columnas_resueltas, esquemas, indices, claves_primarias


def _proposito_consulta(nombre: str) -> str:
    """Asigna una familia operativa sin fingir que reemplaza la SQL de Access."""
    texto = nombre.upper()
    if texto.startswith("H05"):
        return "clima"
    if texto.startswith("H02"):
        return "packing / Elifab"
    if texto.startswith("H01") or texto.startswith("R01"):
        return "cosecha"
    if texto.startswith("R08"):
        return "forecast de campaña"
    if texto.startswith("R09"):
        return "forecast semanal"
    if texto.startswith("M"):
        return "maestro / configuración"
    if texto.startswith("E"):
        return "evaluación de campo"
    if texto.startswith(("01", "02", "03", "04", "05")):
        return "consulta operativa histórica"
    return "consulta Access heredada; revisar definición"


def _catalogar_consultas(cursor) -> list[dict[str, Any]]:
    """Lista las consultas guardadas y marca si pueden abrirse por ODBC.

    ACE/ODBC no expone de forma uniforme el SQL de las consultas guardadas. Se conserva el
    estado de ejecución y se deja la definición vacía cuando el driver no la publica; esto es
    preferible a inventar una definición o materializar el resultado como tabla.
    """
    consultas: list[dict[str, Any]] = []
    try:
        objetos = cursor.tables().fetchall()
    except Exception as exc:
        return [
            {
                "nombre": None,
                "tipo_objeto": "VIEW",
                "definicion_sql": None,
                "dependencias": [],
                "proposito": "no disponible: no se pudo leer el catálogo ODBC",
                "estado": "no_disponible",
                "detalle": f"No se pudo leer el catálogo de consultas: {exc}",
            }
        ]

    for objeto in objetos:
        nombre = getattr(objeto, "table_name", None)
        tipo = str(getattr(objeto, "table_type", "")).upper()
        if not nombre or not (tipo in {"VIEW", "QUERY"} or "VIEW" in tipo):
            continue
        if str(nombre).startswith(("MSys", "~")):
            continue
        try:
            cursor.execute(f"SELECT TOP 0 * FROM [{nombre}]")
            estado = "ejecutable"
            detalle = None
        except Exception as exc:
            estado = "rota"
            detalle = str(exc)
        consultas.append(
            {
                "nombre": str(nombre),
                "tipo_objeto": tipo or "VIEW",
                "definicion_sql": None,
                # ACE/ODBC no publica QueryDef.SQL ni su grafo de dependencias de forma
                # consistente. Se declara vacío para no inventar relaciones; la consulta queda
                # marcada para futura ingeniería inversa.
                "dependencias": [],
                "proposito": _proposito_consulta(str(nombre)),
                "estado": estado,
                "detalle": detalle,
            }
        )
    return sorted(consultas, key=lambda x: x["nombre"] or "")


def _sha256_archivo(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as fh:
        while bloque := fh.read(1 << 20):
            digest.update(bloque)
    return digest.hexdigest()


def _versiones_r09(cursor) -> dict[str, Any]:
    """Resume las emisiones R09 sin asumir que el texto de versión es correlativo."""
    # Las copias Access no son homogéneas: la base histórica documentada usa `Version`,
    # mientras algunas exportaciones antiguas exponían `Versión`. El catálogo de extracción
    # ya normaliza ambos casos a `version`; el manifiesto debe hacer lo mismo y no bloquear
    # una copia válida por el nombre de una columna.
    try:
        cursor.execute(
            """
            SELECT [Version], Count(*) AS filas
            FROM [R09_Forecast_Semanal]
            GROUP BY [Version]
            """
        )
    except Exception:
        cursor.execute(
            """
            SELECT [Versión], Count(*) AS filas
            FROM [R09_Forecast_Semanal]
            GROUP BY [Versión]
            """
        )
    conteos = {str(version): int(filas) for version, filas in cursor.fetchall()}

    def numero(version: str) -> int:
        texto = version.upper().strip()
        return int(texto[1:]) if texto.startswith("S") and texto[1:].isdigit() else -1

    ordenadas = sorted(conteos, key=lambda version: (numero(version), version))
    return {
        "filas": sum(conteos.values()),
        "version_minima": ordenadas[0] if ordenadas else None,
        "version_maxima": ordenadas[-1] if ordenadas else None,
        "conteos_por_version": conteos,
    }


def _guardar_manifiesto_access(
    config: Config,
    resultados: list[ResultadoExtraccion],
    r09: dict[str, Any],
    *,
    schema_hash: str | None = None,
    consultas: list[dict[str, Any]] | None = None,
    sha256: str | None = None,
    columnas_origen: dict[str, tuple[str | None, ...]] | None = None,
    esquemas: dict[str, list[dict[str, Any]]] | None = None,
    indices: dict[str, list[dict[str, Any]]] | None = None,
    claves_primarias: dict[str, list[dict[str, Any]]] | None = None,
    relaciones: list[dict[str, Any]] | None = None,
    catalogo_dao: dict[str, Any] | None = None,
) -> Path:
    destinos_catalogo = {tabla.destino for tabla in CATALOGO_ACCESS}
    destinos_extraidos = {resultado.destino for resultado in resultados}
    tablas_omitidas = sorted(destinos_catalogo - destinos_extraidos)
    alcance_completo = not tablas_omitidas
    estadistica = config.access_db.stat()
    manifiesto = {
        "tipo": "access",
        "catalogo_version": 4,
        "campania": config.access_campania,
        "solo_lectura": True,
        "ruta_origen": str(config.access_db.resolve()),
        "nombre_archivo": config.access_db.name,
        "sha256": sha256 or _sha256_archivo(config.access_db),
        "version_fuente": config.access_version_fuente,
        "schema_hash": schema_hash,
        "bytes": estadistica.st_size,
        "modificado_en": dt.datetime.fromtimestamp(
            estadistica.st_mtime, tz=dt.UTC
        ).isoformat(),
        "extraido_en": dt.datetime.now(dt.UTC).isoformat(),
        "alcance": "completo" if alcance_completo else "parcial",
        "snapshot_completo": alcance_completo,
        "tablas_catalogo": len(destinos_catalogo),
        "tablas_extraidas": len(destinos_extraidos),
        "tablas_omitidas": tablas_omitidas,
        "esquema": esquemas or {},
        "indices": indices or {},
        "claves_primarias": claves_primarias or {},
        "tablas": {
            resultado.destino: {
                "objeto_origen": resultado.tabla,
                "columnas_origen": list((columnas_origen or {}).get(resultado.destino, ())),
                "esquema": (esquemas or {}).get(resultado.tabla, []),
                "indices": (indices or {}).get(resultado.tabla, []),
                "claves_primarias": (claves_primarias or {}).get(resultado.tabla, []),
                "schema_hash": _hash_tabla_schema(
                    resultado.tabla, esquemas or {}, indices or {}, claves_primarias or {}
                ),
                "filas": resultado.filas,
                "esperadas": resultado.esperadas,
                "estado": "ok" if resultado.ok else "desviacion",
                "sha256_csv": resultado.sha256_csv,
            }
            for resultado in resultados
        },
        "consultas": consultas or [],
        "relaciones": relaciones or [],
        "catalogo_backends": {
            "odbc": "disponible",
            "dao": {
                "estado": (catalogo_dao or {}).get("estado", "no_disponible"),
                "detalle": (catalogo_dao or {}).get("detalle"),
                "tablas": len((catalogo_dao or {}).get("tablas") or []),
                "relaciones": len((catalogo_dao or {}).get("relaciones") or []),
                "querydefs": len((catalogo_dao or {}).get("querydefs") or []),
            },
        },
        "r09": r09,
    }
    ruta = config.dir_extraccion / MANIFIESTO_ACCESS
    ruta.write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ruta


def _guardar_catalogo_access(
    config: Config,
    *,
    sha256: str,
    origenes: dict[str, str],
    columnas_origen: dict[str, tuple[str | None, ...]],
    esquemas: dict[str, list[dict[str, Any]]],
    indices: dict[str, list[dict[str, Any]]],
    claves_primarias: dict[str, list[dict[str, Any]]],
    filas: dict[str, int],
    consultas: list[dict[str, Any]],
    relaciones: list[dict[str, Any]] | None = None,
    catalogo_dao: dict[str, Any] | None = None,
) -> Path:
    """Guarda el catálogo técnico fuera del snapshot CSV, sin mutar snapshots existentes."""
    payload = {
        "tipo": "access_catalogo",
        "catalogo_version": 4,
        "backend": "dao" if (catalogo_dao or {}).get("estado") == "disponible" else "odbc",
        "backend_estado": (catalogo_dao or {}).get("estado", "no_disponible"),
        "backend_detalle": (catalogo_dao or {}).get("detalle"),
        "campania": config.access_campania,
        "ruta_origen": str(config.access_db.resolve()),
        "nombre_archivo": config.access_db.name,
        "sha256": sha256,
        "version_fuente": config.access_version_fuente,
        "extraido_en": dt.datetime.now(dt.UTC).isoformat(),
        "tablas_catalogo": len(origenes),
        "tablas": {
            destino: {
                "objeto_origen": origenes[destino],
                "columnas_origen": list(columnas_origen[destino]),
                "filas": filas.get(destino),
                "columnas": esquemas.get(origenes[destino], []),
                "indices": indices.get(origenes[destino], []),
                "claves_primarias": claves_primarias.get(origenes[destino], []),
                "schema_hash": _hash_tabla_schema(
                    origenes[destino], esquemas, indices, claves_primarias
                ),
            }
            for destino in sorted(origenes)
        },
        "consultas": consultas,
        "relaciones": relaciones or [],
        "schema_hash": _hash_schema(esquemas, indices, claves_primarias),
    }
    ruta_base = (
        config.dir_extraccion
        / "catalogos"
        / config.access_campania
        / f"{sha256[:16]}_access_catalog.json"
    )
    ruta_base.parent.mkdir(parents=True, exist_ok=True)
    if ruta_base.exists():
        try:
            anterior = json.loads(ruta_base.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            anterior = {}
        consultas_anteriores = anterior.get("consultas") or []
        completo = all(
            consulta.get("proposito")
            for consulta in consultas_anteriores
            if consulta.get("nombre")
        )
        if (
            anterior.get("catalogo_version", 0) >= payload["catalogo_version"]
            and completo
            and "relaciones" in anterior
            and anterior.get("backend_estado") == payload.get("backend_estado")
        ):
            return ruta_base
        ruta = ruta_base.with_name(
            f"{sha256[:16]}_v{payload['catalogo_version']}_access_catalog.json"
        )
    else:
        ruta = ruta_base
    ruta.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return ruta


def catalogar_access(
    config: Config, registrar=print, *, require_dao: bool = False
) -> Path:
    """Inspecciona Access en solo lectura y genera su catálogo técnico completo."""
    if not config.access_db.is_file():
        raise FileNotFoundError(f"No encuentro la base de origen en {config.access_db}.")
    sha256_origen = _sha256_archivo(config.access_db)
    catalogo_dao = _catalogar_access_dao(config, require_dao=require_dao)
    conexion = conectar(config)
    try:
        cursor = conexion.cursor()
        tablas = list(CATALOGO_ACCESS)
        origenes, columnas, esquemas, indices, claves = _catalogar_tablas(cursor, tablas)
        _incorporar_catalogo_dao(esquemas, indices, claves, catalogo_dao)
        filas: dict[str, int] = {}
        for destino, origen in origenes.items():
            cursor.execute(f"SELECT COUNT(*) FROM [{origen}]")
            fila = cursor.fetchone()
            filas[destino] = int(fila[0]) if fila else 0
        consultas = _enriquecer_consultas_dao(_catalogar_consultas(cursor), catalogo_dao)
        ruta = _guardar_catalogo_access(
            config,
            sha256=sha256_origen,
            origenes=origenes,
            columnas_origen=columnas,
            esquemas=esquemas,
            indices=indices,
            claves_primarias=claves,
            filas=filas,
            consultas=consultas,
            relaciones=list(catalogo_dao.get("relaciones") or []),
            catalogo_dao=catalogo_dao,
        )
    finally:
        conexion.close()
    registrar(
        f"Catálogo Access: {ruta} · {len(origenes)} tablas · {len(consultas)} consultas · "
        f"{len(catalogo_dao.get('relaciones') or [])} relaciones DAO · "
        f"DAO={catalogo_dao.get('estado')} · "
        f"schema_hash={_hash_schema(esquemas, indices, claves)[:16]}"
    )
    return ruta


def _buscar_snapshot_existente(
    config: Config, sha256: str, solo: set[str] | None = None
) -> Path | None:
    """Busca una extracción previa del mismo archivo físico dentro del directorio de salida."""
    raiz = config.dir_extraccion / "snapshots" / config.access_campania
    if not raiz.is_dir():
        return None
    for manifiesto in raiz.glob("*/" + MANIFIESTO_ACCESS):
        try:
            contenido = json.loads(manifiesto.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if contenido.get("tipo") != "access" or contenido.get("sha256") != sha256:
            continue
        tablas = set((contenido.get("tablas") or {}).keys())
        if solo is None and contenido.get("snapshot_completo") is not True:
            continue
        if solo is not None and not set(solo) <= tablas:
            continue
        return manifiesto.parent
    return None


def _resultados_de_snapshot(
    ruta: Path, solo: set[str] | None = None
) -> list[ResultadoExtraccion]:
    manifiesto = json.loads((ruta / MANIFIESTO_ACCESS).read_text(encoding="utf-8"))
    resultados = []
    for destino, detalle in (manifiesto.get("tablas") or {}).items():
        if solo is not None and destino not in solo:
            continue
        resultados.append(
            ResultadoExtraccion(
                tabla=detalle.get("objeto_origen", destino),
                destino=destino,
                filas=int(detalle.get("filas", 0)),
                ruta_csv=ruta / f"{destino}.csv",
                esperadas=detalle.get("esperadas"),
                extraido_en=dt.datetime.now(dt.UTC),
                sha256_csv=detalle.get("sha256_csv", ""),
            )
        )
    return resultados


def extraer_access(
    config: Config,
    solo: set[str] | None = None,
    registrar=print,
    *,
    require_dao: bool = False,
) -> list[ResultadoExtraccion]:
    """Extrae las tablas del catálogo a un snapshot inmutable.

    `solo` filtra por nombre de destino, para poder repetir una tabla concreta sin volver a
    extraer las 654.598 filas del origen completo.
    """
    if not config.access_db.is_file():
        raise FileNotFoundError(
            f"No encuentro la base de origen en {config.access_db}.\n"
            "  Revisa ACCESS_DB_PATH o --access-path."
        )
    config.dir_extraccion.mkdir(parents=True, exist_ok=True)
    sha256_origen = _sha256_archivo(config.access_db)
    catalogo_dao = _catalogar_access_dao(config, require_dao=require_dao)
    destinos_catalogo = {tabla.destino for tabla in CATALOGO_ACCESS}
    if solo is not None:
        desconocidas = sorted(set(solo) - destinos_catalogo)
        if desconocidas:
            raise ValueError(
                "Tablas Access no reconocidas por el catálogo: "
                f"{desconocidas}. Usa `npm run py catalogo` para consultar destinos válidos."
            )
    existente = _buscar_snapshot_existente(config, sha256_origen, solo)
    if existente is not None:
        registrar(f"Snapshot Access existente: {existente} · se reutiliza por SHA-256")
        return _resultados_de_snapshot(existente, solo)
    tablas = [t for t in CATALOGO_ACCESS if solo is None or t.destino in solo]

    marca = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    ruta_snapshot = (
        config.dir_extraccion
        / "snapshots"
        / config.access_campania
        / f"{marca}_{sha256_origen[:16]}"
    )
    config_snapshot = replace(config, dir_extraccion=ruta_snapshot)
    ruta_snapshot.mkdir(parents=True, exist_ok=False)

    registrar(f"Origen: {config.access_db}")
    registrar(f"Destino: {ruta_snapshot}")
    registrar(f"Tablas a extraer: {len(tablas)}")
    for objeto, motivo in DESCARTADAS.items():
        registrar(f"  descartado · {objeto}: {motivo}")

    resultados: list[ResultadoExtraccion] = []
    conexion = conectar(config)
    try:
        cursor = conexion.cursor()
        try:
            r09 = _versiones_r09(cursor)
        except Exception:
            r09 = {
                "filas": 0,
                "version_minima": None,
                "version_maxima": None,
                "conteos_por_version": {},
            }
        esquemas: dict[str, list[dict[str, Any]]] = {}
        indices: dict[str, list[dict[str, Any]]] = {}
        claves_primarias: dict[str, list[dict[str, Any]]] = {}
        columnas_resueltas: dict[str, tuple[str | None, ...]] = {}
        for tabla in tablas:
            inicio = dt.datetime.now(dt.UTC)
            origen = _resolver_origen(cursor, tabla)
            esquemas[origen] = _schema_descriptor(cursor, origen)
            indices[origen] = _indices_descriptor(cursor, origen)
            claves_primarias[origen] = _claves_primarias_descriptor(cursor, origen)
            columnas_origen = _resolver_columnas(cursor, tabla, origen)
            columnas_resueltas[tabla.destino] = columnas_origen
            ruta = config_snapshot.csv_de(tabla.destino)
            cursor.execute(tabla.select(origen, columnas_origen))
            filas = 0
            with ruta.open("w", encoding="utf-8", newline="") as fh:
                escritor = csv.writer(fh, lineterminator="\n", quoting=csv.QUOTE_NOTNULL)
                escritor.writerow(tabla.cols_destino)
                while True:
                    lote = cursor.fetchmany(LOTE_FILAS)
                    if not lote:
                        break
                    escritor.writerows([_serializar(v) for v in fila] for fila in lote)
                    filas += len(lote)
            resultado = ResultadoExtraccion(
                tabla=origen,
                destino=tabla.destino,
                filas=filas,
                ruta_csv=ruta,
                esperadas=tabla.filas_esperadas,
                extraido_en=inicio,
                sha256_csv=_sha256_archivo(ruta),
            )
            resultados.append(resultado)
            marca = "ok" if resultado.ok else f"DESVIACIÓN {resultado.desviacion:+d}"
            registrar(f"  {tabla.origen:<24} {filas:>8,} filas  {marca}")
        _incorporar_catalogo_dao(esquemas, indices, claves_primarias, catalogo_dao)
        consultas = _enriquecer_consultas_dao(_catalogar_consultas(cursor), catalogo_dao)
        ruta_manifiesto = _guardar_manifiesto_access(
            config_snapshot,
            resultados,
            r09,
            schema_hash=_hash_schema(esquemas, indices, claves_primarias),
            consultas=consultas,
            sha256=sha256_origen,
            columnas_origen=columnas_resueltas,
            esquemas=esquemas,
            indices=indices,
            claves_primarias=claves_primarias,
            relaciones=list(catalogo_dao.get("relaciones") or []),
            catalogo_dao=catalogo_dao,
        )
        registrar(
            "Snapshot Access: "
            f"{ruta_manifiesto} · R09 hasta {r09['version_maxima'] or 'sin versiones'}"
        )
    finally:
        # Solo lectura: no hay nada que confirmar, y cerrar sin commit deja el .laccdb intacto.
        conexion.close()

    return resultados
