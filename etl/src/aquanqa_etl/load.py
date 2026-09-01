"""Carga append-only de snapshots al esquema ``raw``.

Cada fila nueva conserva la huella del archivo físico que la produjo. Repetir el mismo
snapshot por su SHA-256 es un no-op; cargar una versión posterior agrega otro bloque histórico
sin truncar ni sobrescribir el bloque anterior. La vista ``raw.v_*_vigente`` se controla por
promoción explícita y permite que ``stg`` consuma solo una versión aprobada.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from aquanqa_etl.catalogo import (
    CATALOGO_ACCESS,
    CATALOGO_VERSION,
    MAESTRO_LOTES_DESTINO,
    MAESTRO_LOTES_FILAS_ESPERADAS,
    TOTAL_FILAS_ORIGEN,
)
from aquanqa_etl.config import Config
from aquanqa_etl.extract.access import MANIFIESTO_ACCESS

METADATOS_RAW = {
    "source_snapshot_id",
    "source_row_number",
    "source_row_hash",
    "loaded_at",
}

# Tablas que no vienen de Access, con su origen y su cifra esperada (None = sin referencia).
EXTERNAS: dict[str, tuple[str, str, int | None]] = {
    MAESTRO_LOTES_DESTINO: ("M_Lotes.xlsx", "xlsx", MAESTRO_LOTES_FILAS_ESPERADAS),
    "tareo": ("Query Tareo 2026.xlsx", "xlsx", None),
}

# Excel y otros orígenes externos tienen su propio snapshot. No bloquean la primera milla de
# Access: la migración completa de raw puede ejecutarse primero y el maestro vigente se carga
# después, antes de promover capas que necesiten resolver identidad.
# Ningún Excel bloquea la primera milla: Access se conserva completo en raw aunque el maestro
# todavía no esté disponible. El maestro se publica por separado y recién es requisito para
# resolver identidad al materializar core; tareo sigue siendo opcional.
EXTERNAS_REQUERIDAS: set[str] = set()


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


def _sha256_archivo(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as fh:
        while bloque := fh.read(1 << 20):
            digest.update(bloque)
    return digest.hexdigest()


def _ruta_externa(config: Config, tabla: str) -> Path:
    """Busca el CSV externo junto al snapshot y, si este es inmutable, en su raíz de salida."""
    directa = config.csv_de(tabla)
    if directa.is_file():
        return directa
    # data/salida/snapshots/C2026/<snapshot> -> data/salida
    for padre in config.dir_extraccion.parents:
        if (padre / "snapshots").is_dir():
            candidata = padre / f"{tabla}.csv"
            if candidata.is_file():
                return candidata
    return directa


def _ruta_catalogo_access(config: Config, sha256: str, campania: str | None) -> Path | None:
    """Encuentra el catálogo técnico asociado al SHA, aunque el snapshot sea antiguo."""
    if not campania:
        return None
    for padre in (config.dir_extraccion, *config.dir_extraccion.parents):
        carpeta = padre / "catalogos" / campania
        if not carpeta.is_dir():
            continue
        candidatos = sorted(carpeta.glob(f"{sha256[:16]}*_access_catalog.json"))
        if candidatos:
            return candidatos[-1]
    return None


def _registrar_catalogo_access(
    conexion, *, source_snapshot_id: int, config: Config, manifiesto: dict
) -> None:
    """Persiste el catálogo técnico sin alterar las columnas de las tablas raw."""
    catalogo = manifiesto if manifiesto.get("tipo") == "access_catalogo" else None
    if catalogo is None:
        tablas_manifiesto = manifiesto.get("tablas") or {}
        if any(
            (detalle or {}).get("esquema") is not None
            for detalle in tablas_manifiesto.values()
        ):
            catalogo = {
                "schema_hash": manifiesto.get("schema_hash"),
                "tablas": {
                    destino: {
                        "objeto_origen": (detalle or {}).get("objeto_origen", destino),
                        "schema_hash": (detalle or {}).get("schema_hash"),
                        "columnas": (detalle or {}).get("esquema", []),
                        "indices": (detalle or {}).get("indices", []),
                        "claves_primarias": (detalle or {}).get("claves_primarias", []),
                    }
                    for destino, detalle in tablas_manifiesto.items()
                },
                "relaciones": manifiesto.get("relaciones") or [],
            }
    if catalogo is None:
        ruta_catalogo = _ruta_catalogo_access(
            config, manifiesto.get("sha256", ""), manifiesto.get("campania")
        )
        if ruta_catalogo is None:
            return
        catalogo = json.loads(ruta_catalogo.read_text(encoding="utf-8"))

    with conexion.cursor() as cur:
        for destino, detalle in (catalogo.get("tablas") or {}).items():
            cur.execute(
                """
                INSERT INTO raw.access_schema_catalog
                    (source_snapshot_id, tabla_destino, objeto_origen, schema_hash,
                     columnas, indices, claves_primarias)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                ON CONFLICT (source_snapshot_id, tabla_destino) DO UPDATE SET
                    objeto_origen = EXCLUDED.objeto_origen,
                    schema_hash = EXCLUDED.schema_hash,
                    columnas = EXCLUDED.columnas,
                    indices = EXCLUDED.indices,
                    claves_primarias = EXCLUDED.claves_primarias,
                    registrado_en = now()
                """,
                (
                    source_snapshot_id,
                    destino,
                    detalle.get("objeto_origen", destino),
                    detalle.get("schema_hash") or catalogo.get("schema_hash"),
                    json.dumps(detalle.get("columnas", []), ensure_ascii=False, default=str),
                    json.dumps(detalle.get("indices", []), ensure_ascii=False, default=str),
                    json.dumps(
                        detalle.get("claves_primarias", []), ensure_ascii=False, default=str
                    ),
                ),
            )
        for relacion in catalogo.get("relaciones") or []:
            nombre = str(relacion.get("nombre") or "").strip()
            padre = str(relacion.get("tabla_padre") or "").strip()
            hija = str(relacion.get("tabla_hija") or "").strip()
            if not nombre:
                continue
            estado = "catalogada" if padre and hija else "incompleta"
            atributos = relacion.get("atributos")
            if not isinstance(atributos, dict):
                atributos = {"dao_attributes": atributos}
            cur.execute(
                """
                INSERT INTO raw.access_relation_catalog
                    (source_snapshot_id, nombre, tabla_padre, tabla_hija,
                     atributos, campos, estado, detalle)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                ON CONFLICT (source_snapshot_id, nombre) DO UPDATE SET
                    tabla_padre = EXCLUDED.tabla_padre,
                    tabla_hija = EXCLUDED.tabla_hija,
                    atributos = EXCLUDED.atributos,
                    campos = EXCLUDED.campos,
                    estado = EXCLUDED.estado,
                    detalle = EXCLUDED.detalle,
                    registrado_en = now()
                """,
                (
                    source_snapshot_id,
                    nombre,
                    padre or "(desconocida)",
                    hija or "(desconocida)",
                    json.dumps(atributos, ensure_ascii=False, default=str),
                    json.dumps(relacion.get("campos") or [], ensure_ascii=False, default=str),
                    estado,
                    "backend=dao" if relacion.get("backend", "dao") == "dao" else None,
                ),
            )


def _copiar(
    conexion,
    tabla: str,
    ruta: Path,
    columnas: list[str],
    source_snapshot_id: int | None = None,
    *,
    tipo_fuente: str = "access",
    campania: str | None = None,
) -> int:
    lista = ", ".join(f'"{c}"' for c in columnas)
    if source_snapshot_id is None:
        raise RuntimeError(f"La tabla raw.{tabla} no puede cargarse sin source_snapshot_id.")

    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT source_snapshot_id
            FROM raw.v_snapshot_publicado
            WHERE tipo = %s AND campania = %s
            """,
            (tipo_fuente, campania or ""),
        )
        fila_publicada = cur.fetchone()
        snapshot_anterior_id = int(fila_publicada[0]) if fila_publicada else None

        cur.execute("DROP TABLE IF EXISTS pg_temp._aquanqa_stage")
        cur.execute("DROP TABLE IF EXISTS pg_temp._aquanqa_huella_anterior")
        cur.execute("DROP TABLE IF EXISTS pg_temp._aquanqa_huella_nueva")
        cur.execute(
            f"""
            CREATE TEMP TABLE _aquanqa_stage ON COMMIT DROP AS
            SELECT {lista}
            FROM raw.{tabla}
            WITH NO DATA
            """
        )
        cur.execute(
            f"""
            CREATE TEMP TABLE _aquanqa_huella_anterior ON COMMIT DROP AS
            SELECT source_row_hash AS huella, count(*)::bigint AS n
            FROM raw.{tabla}
            WHERE source_snapshot_id = %s
            GROUP BY 1
            """,
            (snapshot_anterior_id or -1,),
        )

        sql = f"COPY pg_temp._aquanqa_stage ({lista}) FROM STDIN WITH (FORMAT csv, HEADER true)"
        with cur.copy(sql) as copia, ruta.open("rb") as fh:
            while bloque := fh.read(1 << 20):
                copia.write(bloque)
        cur.execute("SELECT count(*) FROM pg_temp._aquanqa_stage")
        fila = cur.fetchone()
        filas = int(fila[0]) if fila else 0

        # Un reintento del mismo snapshot reemplaza únicamente su partición lógica. Esto
        # cubre fallos después del COPY o una carga parcial reanudada sin duplicar filas de
        # ese snapshot; los snapshots anteriores permanecen intactos.
        cur.execute(
            f"DELETE FROM raw.{tabla} WHERE source_snapshot_id = %s",
            (source_snapshot_id,),
        )
        cur.execute(
            f"""
            INSERT INTO raw.{tabla} ({lista}, source_snapshot_id, source_row_number,
                                     source_row_hash, loaded_at)
            SELECT {lista}, %s, row_number() OVER (),
                   md5(row_to_json(fila)::text), now()
            FROM pg_temp._aquanqa_stage fila
            """,
            (source_snapshot_id,),
        )

        cur.execute("SELECT COALESCE(sum(n), 0) FROM _aquanqa_huella_anterior")
        filas_anteriores = int(cur.fetchone()[0])
        cur.execute(
            f"""
            CREATE TEMP TABLE _aquanqa_huella_nueva ON COMMIT DROP AS
            SELECT source_row_hash AS huella, count(*)::bigint AS n
            FROM raw.{tabla}
            WHERE source_snapshot_id = %s
            GROUP BY 1
            """,
            (source_snapshot_id,),
        )
        cur.execute(
            """
            WITH diferencia AS (
                SELECT COALESCE(nueva.n, 0) - COALESCE(anterior.n, 0) AS delta
                FROM _aquanqa_huella_nueva nueva
                FULL JOIN _aquanqa_huella_anterior anterior USING (huella)
            )
            INSERT INTO raw.source_table_delta
                (source_snapshot_id, snapshot_anterior_id, tabla_destino,
                 filas_anteriores, filas_actuales,
                 filas_nuevas, filas_eliminadas, filas_modificadas, metodo)
            SELECT %s, %s, %s, %s, %s,
                   COALESCE(sum(GREATEST(delta, 0)), 0),
                   COALESCE(sum(GREATEST(-delta, 0)), 0),
                   0,
                   'huella_multiconjunto_por_snapshot'
            FROM diferencia
            ON CONFLICT (source_snapshot_id, tabla_destino) DO UPDATE SET
                snapshot_anterior_id=EXCLUDED.snapshot_anterior_id,
                filas_anteriores=EXCLUDED.filas_anteriores,
                filas_actuales=EXCLUDED.filas_actuales,
                filas_nuevas=EXCLUDED.filas_nuevas,
                filas_eliminadas=EXCLUDED.filas_eliminadas,
                filas_modificadas=EXCLUDED.filas_modificadas,
                metodo=EXCLUDED.metodo,
                calculado_en=now()
            """,
            (source_snapshot_id, snapshot_anterior_id, tabla, filas_anteriores, filas),
        )
        return filas


def _archivar_r09_actual(conexion) -> None:
    """Conserva la copia R09 previa antes del TRUNCATE idempotente de raw."""
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT source_snapshot_id
            FROM raw.carga_log
            WHERE tabla_destino = 'r09_forecast_semanal'
              AND source_snapshot_id IS NOT NULL
            ORDER BY cargado_en DESC, carga_id DESC
            LIMIT 1
            """
        )
        fila = cur.fetchone()
        if not fila:
            return
        snapshot_anterior = int(fila[0])
        cur.execute(
            """
            INSERT INTO raw.r09_forecast_semanal_snapshot
                (source_snapshot_id, campania, pasada, modulo, turno, lote, area,
                 fecha_cos_ant, fecha_cos, sem, frt_cos, peso, frutos_total, rend,
                 kg, dr, version, fund_ppto, fundo)
            SELECT %s, campania, pasada, modulo, turno, lote, area,
                   fecha_cos_ant, fecha_cos, sem, frt_cos, peso, frutos_total, rend,
                   kg, dr, version, fund_ppto, fundo
            FROM raw.r09_forecast_semanal
            WHERE NOT EXISTS (
                SELECT 1 FROM raw.r09_forecast_semanal_snapshot
                WHERE source_snapshot_id = %s
            )
            """,
            (snapshot_anterior, snapshot_anterior),
        )


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
    source_snapshot_id: int | None = None,
) -> None:
    with conexion.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw.carga_log
                (tabla_destino, objeto_origen, origen, ruta_origen,
                 filas_cargadas, filas_esperadas, extraido_en, estado, detalle,
                 source_snapshot_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                source_snapshot_id,
            ),
        )


def _manifiesto_json(valor: object) -> dict:
    if isinstance(valor, dict):
        return valor
    if isinstance(valor, str):
        try:
            contenido = json.loads(valor)
        except json.JSONDecodeError:
            return {}
        return contenido if isinstance(contenido, dict) else {}
    return {}


def _snapshot_access_cubre(
    manifiesto: dict, *, solo: set[str] | None, destinos_catalogo: set[str]
) -> bool:
    contrato = manifiesto.get("contrato_raw") or {}
    if (
        manifiesto.get("catalogo_version", 0) < CATALOGO_VERSION
        or contrato.get("version") != CATALOGO_VERSION
        or contrato.get("estado") != "completo"
        or contrato.get("columnas_no_mapeadas")
    ):
        return False
    tablas = set((manifiesto.get("tablas") or {}).keys())
    if solo is None or destinos_catalogo <= solo:
        return (
            manifiesto.get("snapshot_completo") is True
            and manifiesto.get("alcance") == "completo"
            and destinos_catalogo <= tablas
        )
    return (destinos_catalogo & solo) <= tablas


def _registrar_snapshot_access(
    conexion, config: Config, solo: set[str] | None = None
) -> tuple[int | None, bool]:
    ruta = config.dir_extraccion / MANIFIESTO_ACCESS
    if not ruta.exists():
        return None, False
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
    r09 = manifiesto.get("r09", {})
    destinos_catalogo = {tabla.destino for tabla in CATALOGO_ACCESS}
    destinos_solicitados = destinos_catalogo if solo is None else destinos_catalogo & solo
    if not destinos_solicitados:
        return None, False
    with conexion.cursor() as cur:
        # Serializa dos cargas concurrentes del mismo archivo físico antes de consultar e
        # insertar el snapshot; así no pueden ganar ambas la carrera de idempotencia.
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"access|{config.access_campania}|{manifiesto['sha256']}",),
        )
        cur.execute(
            """
            SELECT source_snapshot_id, estado, manifiesto
            FROM raw.source_snapshot
            WHERE tipo = 'access' AND campania = %s AND sha256 = %s
            ORDER BY source_snapshot_id DESC
            """,
            (config.access_campania, manifiesto["sha256"]),
        )
        snapshot_previo_id: int | None = None
        for existente in cur.fetchall():
            if snapshot_previo_id is None:
                snapshot_previo_id = int(existente[0])
            if not _snapshot_access_cubre(
                _manifiesto_json(existente[2]),
                solo=solo,
                destinos_catalogo=destinos_catalogo,
            ):
                continue
            return int(existente[0]), str(existente[1]) in {
                "cargado", "aprobado", "publicado"
            }
        cur.execute(
            """
            INSERT INTO raw.source_snapshot
                (tipo, campania, ruta_origen, nombre_archivo, sha256, bytes,
                 modificado_en, extraido_en, solo_lectura,
                 version_minima_r09, version_maxima_r09, filas_r09,
                 conteos_tabla, manifiesto, version_fuente, schema_hash, estado,
                 reemplaza_snapshot_id)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, 'detectado', %s)
            RETURNING source_snapshot_id
            """,
            (
                manifiesto["tipo"],
                manifiesto.get("campania"),
                manifiesto["ruta_origen"],
                manifiesto["nombre_archivo"],
                manifiesto["sha256"],
                manifiesto.get("bytes"),
                manifiesto.get("modificado_en"),
                manifiesto["extraido_en"],
                manifiesto.get("solo_lectura", True),
                r09.get("version_minima"),
                r09.get("version_maxima"),
                r09.get("filas"),
                json.dumps(manifiesto.get("tablas", {}), ensure_ascii=False),
                json.dumps(manifiesto, ensure_ascii=False),
                manifiesto.get("version_fuente"),
                manifiesto.get("schema_hash"),
                snapshot_previo_id,
            ),
        )
        fila = cur.fetchone()
        return (int(fila[0]), False) if fila else (None, False)


def _registrar_snapshot_xlsx(
    conexion, config: Config, tabla: str, ruta: Path
) -> tuple[int, bool]:
    """Registra un Excel externo como snapshot independiente del Access."""
    from aquanqa_etl.extract.access import _sha256_archivo

    sha256 = _sha256_archivo(ruta)
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"xlsx|{config.access_campania}|{tabla}|{sha256}",),
        )
        cur.execute(
            """
            SELECT source_snapshot_id, estado
            FROM raw.source_snapshot
            WHERE tipo = 'xlsx'
              AND campania = %s
              AND sha256 = %s
              AND manifiesto->>'tabla' = %s
            ORDER BY source_snapshot_id DESC
            LIMIT 1
            """,
            (config.access_campania, sha256, tabla),
        )
        existente = cur.fetchone()
        if existente:
            return int(existente[0]), str(existente[1]) in {
                "cargado", "aprobado", "publicado"
            }
        estadistica = ruta.stat()
        cur.execute(
            """
            INSERT INTO raw.source_snapshot
                (tipo, campania, ruta_origen, nombre_archivo, sha256, bytes,
                 modificado_en, extraido_en, solo_lectura, version_fuente,
                 manifiesto, estado)
            VALUES
                ('xlsx', %s, %s, %s, %s, %s, %s, now(), true, 'vigente',
                 %s::jsonb, 'detectado')
            RETURNING source_snapshot_id
            """,
            (
                config.access_campania,
                str(ruta.resolve()),
                ruta.name,
                sha256,
                estadistica.st_size,
                dt.datetime.fromtimestamp(estadistica.st_mtime, tz=dt.UTC),
                json.dumps({"tabla": tabla, "archivo": str(ruta)}, ensure_ascii=False),
            ),
        )
        return int(cur.fetchone()[0]), False


def _tablas_snapshot_cargadas(conexion, source_snapshot_id: int | None) -> set[str]:
    if source_snapshot_id is None:
        return set()
    with conexion.cursor() as cur:
        cur.execute(
            """
            SELECT tabla_destino
            FROM raw.source_table_snapshot
            WHERE source_snapshot_id = %s AND estado = 'cargado'
            """,
            (source_snapshot_id,),
        )
        return {str(fila[0]) for fila in cur.fetchall()}


def _validar_snapshot_access(config: Config, solo: set[str] | None) -> None:
    """Impide que una carga completa confunda un extracto parcial con el origen.

    La operación de una tabla concreta sigue siendo válida para corregir o repetir una
    extracción (`--solo`). En cambio, una carga completa debe tener un manifiesto completo
    y todos los CSV del catálogo; de lo contrario `raw` quedaría mezclando tablas nuevas con
    datos de una ejecución anterior o con tablas ausentes.
    """
    destinos_catalogo = {tabla.destino for tabla in CATALOGO_ACCESS}
    carga_access_completa = solo is None or destinos_catalogo <= solo

    ruta_manifiesto = config.dir_extraccion / MANIFIESTO_ACCESS
    if not ruta_manifiesto.is_file():
        if not carga_access_completa:
            return
        raise RuntimeError(
            "No existe el manifiesto Access de una carga completa: "
            f"{ruta_manifiesto}. Ejecuta primero `python -m aquanqa_etl extract`."
        )

    try:
        manifiesto = json.loads(ruta_manifiesto.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"El manifiesto Access no se puede leer: {ruta_manifiesto}") from exc

    if manifiesto.get("tipo") != "access":
        raise RuntimeError("El manifiesto seleccionado no declara tipo='access'.")

    campania_manifiesto = str(manifiesto.get("campania", "")).strip().upper()
    if not campania_manifiesto:
        raise RuntimeError("El manifiesto Access no declara la campaña de origen.")
    if campania_manifiesto != config.access_campania.upper():
        raise RuntimeError(
            "El manifiesto Access pertenece a la campaña "
            f"{campania_manifiesto}, pero la configuración solicita {config.access_campania}."
        )

    tablas_manifiesto = manifiesto.get("tablas") or {}
    if not carga_access_completa:
        destinos_a_validar = destinos_catalogo.intersection(solo or set())
    else:
        destinos_a_validar = destinos_catalogo

    if carga_access_completa and (
        manifiesto.get("snapshot_completo") is not True or manifiesto.get("alcance") != "completo"
    ):
        alcance = manifiesto.get("alcance", "desconocido")
        raise RuntimeError(
            "La carga completa requiere un snapshot Access completo; "
            f"el manifiesto declara alcance={alcance!r}. Repite `python -m aquanqa_etl extract`."
        )

    # Solo una carga completa puede convertirse en la base de comparación. Las cargas
    # parciales siguen permitidas para reparar una tabla puntual; las rutas reales de
    # extracción ya validaron el contrato completo antes de producir el CSV.
    if carga_access_completa:
        contrato = manifiesto.get("contrato_raw") or {}
        if manifiesto.get("catalogo_version", 0) < CATALOGO_VERSION:
            raise RuntimeError(
                "El manifiesto Access usa un contrato de columnas antiguo "
                f"(v{manifiesto.get('catalogo_version', 0)}; se requiere v{CATALOGO_VERSION}). "
                "Repite la extracción completa para no cargar columnas omitidas."
            )
        if contrato.get("version") != CATALOGO_VERSION or contrato.get("estado") != "completo":
            raise RuntimeError(
                "El manifiesto Access no demuestra que todas las columnas físicas fueron revisadas "
                "y mapeadas a raw. Repite la extracción con el catálogo vigente."
            )
        if contrato.get("columnas_no_mapeadas"):
            raise RuntimeError(
                "El manifiesto Access contiene columnas físicas no mapeadas: "
                f"{contrato['columnas_no_mapeadas']}."
            )

    if carga_access_completa:
        tablas_manifiesto_nombres = set(tablas_manifiesto.keys())
        faltantes_manifiesto = sorted(destinos_catalogo - tablas_manifiesto_nombres)
        faltantes_csv = sorted(
            destino for destino in destinos_catalogo if not config.csv_de(destino).is_file()
        )
        if faltantes_manifiesto or faltantes_csv:
            detalle = []
            if faltantes_manifiesto:
                detalle.append(f"faltan en manifiesto: {', '.join(faltantes_manifiesto)}")
            if faltantes_csv:
                detalle.append(f"faltan CSV: {', '.join(faltantes_csv)}")
            raise RuntimeError(
                "El snapshot Access está incompleto para una carga completa ("
                + "; ".join(detalle)
                + "). Repite la extracción completa."
            )

    if carga_access_completa and solo is None:
        faltantes_externas = sorted(
            tabla for tabla in EXTERNAS_REQUERIDAS if not _ruta_externa(config, tabla).is_file()
        )
        if faltantes_externas:
            raise RuntimeError(
                "La carga completa requiere estos CSV externos y no están presentes: "
                f"{', '.join(faltantes_externas)}. Ejecuta primero la extracción completa."
            )

    for destino in sorted(destinos_a_validar):
        esperado = (tablas_manifiesto.get(destino) or {}).get("sha256_csv")
        if not esperado:
            raise RuntimeError(
                f"El manifiesto Access no registra la huella del CSV de {destino}. "
                "Repite su extracción antes de cargarlo."
            )
        ruta_csv = config.csv_de(destino)
        if not ruta_csv.is_file():
            raise RuntimeError(f"No existe el CSV Access seleccionado: {ruta_csv}.")
        if _sha256_archivo(ruta_csv) != esperado:
            raise RuntimeError(
                f"El CSV de {destino} no coincide con la huella del manifiesto Access. "
                "Repite su extracción antes de cargarlo."
            )


def _registrar_consultas_access(
    conexion, snapshot_id: int, manifiesto: dict, consultas_override: list[dict] | None = None
) -> None:
    consultas = (
        consultas_override
        if consultas_override is not None
        else manifiesto.get("consultas") or []
    )
    with conexion.cursor() as cur:
        for consulta in consultas:
            nombre = consulta.get("nombre")
            if not nombre:
                continue
            cur.execute(
                """
                INSERT INTO raw.access_query_catalog
                    (source_snapshot_id, nombre, tipo_objeto, definicion_sql,
                     dependencias, proposito, estado, detalle)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (source_snapshot_id, nombre) DO UPDATE SET
                    tipo_objeto = EXCLUDED.tipo_objeto,
                    definicion_sql = EXCLUDED.definicion_sql,
                    dependencias = EXCLUDED.dependencias,
                    proposito = EXCLUDED.proposito,
                    estado = EXCLUDED.estado,
                    detalle = EXCLUDED.detalle
                """,
                (
                    snapshot_id,
                    nombre,
                    consulta.get("tipo_objeto", "VIEW"),
                    consulta.get("definicion_sql"),
                    json.dumps(consulta.get("dependencias", []), ensure_ascii=False),
                    consulta.get("proposito"),
                    consulta.get("estado", "no_disponible"),
                    consulta.get("detalle"),
                ),
            )


def _registrar_tabla_snapshot(
    conexion,
    *,
    source_snapshot_id: int,
    tabla: str,
    objeto: str,
    filas: int,
    filas_origen: int | None,
    sha256_csv: str | None,
    schema_hash: str | None = None,
    estado: str = "cargado",
    detalle: str | None = None,
) -> None:
    with conexion.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw.source_table_snapshot
                (source_snapshot_id, tabla_destino, objeto_origen,
                 filas_origen, filas_csv, sha256_csv, schema_hash, estado, detalle)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_snapshot_id, tabla_destino) DO UPDATE SET
                objeto_origen = EXCLUDED.objeto_origen,
                filas_origen = EXCLUDED.filas_origen,
                filas_csv = EXCLUDED.filas_csv,
                sha256_csv = EXCLUDED.sha256_csv,
                schema_hash = EXCLUDED.schema_hash,
                estado = EXCLUDED.estado,
                detalle = EXCLUDED.detalle,
                registrado_en = now()
            """,
            (
                source_snapshot_id,
                tabla,
                objeto,
                filas_origen,
                filas,
                sha256_csv,
                schema_hash,
                estado,
                detalle,
            ),
        )


def cargar_raw(
    config: Config,
    solo: set[str] | None = None,
    registrar=print,
) -> list[ResultadoCarga]:
    """Carga un snapshot completo a `raw` sin truncar histórico anterior."""
    _validar_snapshot_access(config, solo)
    import psycopg

    previstas: dict[str, tuple[str, str, int | None]] = {
        t.destino: (t.origen, "access", t.filas_esperadas) for t in CATALOGO_ACCESS
    }
    previstas.update(EXTERNAS)

    resultados: list[ResultadoCarga] = []
    with psycopg.connect(config.dsn, autocommit=False) as conexion:
        source_snapshot_id, snapshot_estado_cargado = _registrar_snapshot_access(
            conexion, config, solo
        )
        destinos_access_solicitados = {
            tabla.destino for tabla in CATALOGO_ACCESS
            if solo is None or tabla.destino in solo
        }
        if source_snapshot_id is None and destinos_access_solicitados:
            raise RuntimeError("No se pudo registrar el snapshot Access seleccionado.")
        tablas_access_cargadas = _tablas_snapshot_cargadas(conexion, source_snapshot_id)
        access_faltantes = destinos_access_solicitados - tablas_access_cargadas
        acceso_ya_cargado = snapshot_estado_cargado and not access_faltantes
        if acceso_ya_cargado:
            registrar(
                f"Snapshot Access {source_snapshot_id} ya cargado; "
                "sus filas se omiten y se conservan las históricas."
            )

        ruta_manifiesto = config.dir_extraccion / MANIFIESTO_ACCESS
        manifiesto = (
            json.loads(ruta_manifiesto.read_text(encoding="utf-8"))
            if ruta_manifiesto.is_file()
            else {}
        )
        if source_snapshot_id is not None:
            _registrar_catalogo_access(
                conexion,
                source_snapshot_id=source_snapshot_id,
                config=config,
                manifiesto=manifiesto,
            )
        if source_snapshot_id is not None:
            # El catálogo es metadata idempotente: se actualiza también al reintentar un
            # snapshot ya cargado, por ejemplo después de mejorar el inspector ODBC.
            consultas = manifiesto.get("consultas") or []
            if consultas and not any(consulta.get("proposito") for consulta in consultas):
                ruta_catalogo = _ruta_catalogo_access(
                    config, manifiesto.get("sha256", ""), manifiesto.get("campania")
                )
                if ruta_catalogo is not None:
                    try:
                        catalogo = json.loads(ruta_catalogo.read_text(encoding="utf-8"))
                        consultas_catalogo = catalogo.get("consultas") or []
                        if consultas_catalogo:
                            consultas = consultas_catalogo
                    except (OSError, json.JSONDecodeError):
                        pass
            _registrar_consultas_access(
                conexion, source_snapshot_id, manifiesto, consultas_override=consultas
            )
        if source_snapshot_id is not None and (not snapshot_estado_cargado or access_faltantes):
            with conexion.cursor() as cur:
                cur.execute(
                    """
                    UPDATE raw.source_snapshot
                    SET estado = 'cargando', actualizado_en = now()
                    WHERE source_snapshot_id = %s
                    """,
                    (source_snapshot_id,),
                )

        for tabla, (objeto, origen, esperadas) in previstas.items():
            if solo is not None and tabla not in solo:
                continue
            if origen == "access" and tabla in tablas_access_cargadas:
                continue
            ruta = config.csv_de(tabla) if origen == "access" else _ruta_externa(config, tabla)
            if not ruta.exists():
                if tabla in EXTERNAS:
                    registrar(f"  {tabla:<24} sin CSV: se omite (origen opcional)")
                else:
                    registrar(f"  {tabla:<24} SIN CSV — falta extraer")
                continue

            columnas_csv = _cabecera_csv(ruta)
            columnas_tabla = _columnas_de(conexion, tabla)
            columnas_raw = [c for c in columnas_tabla if c not in METADATOS_RAW]
            if not columnas_raw:
                raise RuntimeError(
                    f"La tabla raw.{tabla} no existe. Ejecuta primero:  npm run sql 10_raw"
                )
            if columnas_csv != columnas_raw:
                raise RuntimeError(
                    f"Las columnas del CSV de {tabla} no coinciden con raw.{tabla}.\n"
                    f"  CSV: {columnas_csv}\n  raw: {columnas_raw}\n"
                    "  El catálogo (catalogo.py) y el DDL (db/sql/10_raw) han "
                    "divergido: corrige uno de los dos antes de cargar."
                )

            if origen == "access":
                snapshot_id_tabla = source_snapshot_id
                detalle_manifest = (manifiesto.get("tablas") or {}).get(tabla) or {}
                filas_origen = detalle_manifest.get("filas")
                sha256_csv = detalle_manifest.get("sha256_csv")
                schema_hash = detalle_manifest.get("schema_hash")
                ruta_origen = ruta
            else:
                ruta_origen = {
                    MAESTRO_LOTES_DESTINO: config.maestro_lotes,
                    "tareo": config.tareo,
                }[tabla]
                if not ruta_origen.is_file():
                    registrar(f"  {tabla:<24} sin archivo externo: se omite")
                    continue
                snapshot_id_tabla, external_ya_cargado = _registrar_snapshot_xlsx(
                    conexion, config, tabla, ruta_origen
                )
                if external_ya_cargado:
                    registrar(
                        f"  {tabla:<24} snapshot XLSX ya cargado; se omite para no duplicar"
                    )
                    continue
                filas_origen = None
                sha256_csv = _sha256_archivo(ruta)
                schema_hash = None

            filas = _copiar(
                conexion,
                tabla,
                ruta,
                columnas_csv,
                snapshot_id_tabla,
                tipo_fuente=origen,
                campania=config.access_campania,
            )
            if filas_origen is not None and filas != int(filas_origen):
                raise RuntimeError(
                    f"El CSV de {tabla} tiene {filas} filas, pero el manifiesto declara "
                    f"{filas_origen}. La transacción completa será revertida."
                )
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
                source_snapshot_id=snapshot_id_tabla,
            )
            _registrar_tabla_snapshot(
                conexion,
                source_snapshot_id=snapshot_id_tabla,
                tabla=tabla,
                objeto=objeto,
                filas=filas,
                filas_origen=filas_origen,
                sha256_csv=sha256_csv,
                schema_hash=schema_hash,
                detalle=detalle,
            )

            resultados.append(ResultadoCarga(tabla, filas, esperadas, estado))
            marca = "ok" if estado == "ok" else f"DESVIACIÓN {desviacion:+d}"
            registrar(f"  {tabla:<24} {filas:>8,} filas  {marca}")

        with conexion.cursor() as cur:
            if source_snapshot_id is not None and (not snapshot_estado_cargado or access_faltantes):
                cur.execute(
                    """
                    UPDATE raw.source_snapshot
                    SET estado = 'cargado', actualizado_en = now()
                    WHERE source_snapshot_id = %s
                    """,
                    (source_snapshot_id,),
                )
            for tabla in EXTERNAS:
                cur.execute(
                    """
                    UPDATE raw.source_snapshot s
                    SET estado = 'cargado', actualizado_en = now()
                    WHERE s.tipo = 'xlsx'
                      AND s.estado = 'detectado'
                      AND EXISTS (
                          SELECT 1 FROM raw.source_table_snapshot ts
                          WHERE ts.source_snapshot_id = s.source_snapshot_id
                            AND ts.tabla_destino = %s
                            AND ts.estado = 'cargado'
                      )
                    """,
                    (tabla,),
                )
        conexion.commit()

    return resultados


def resumen_carga(
    resultados: list[ResultadoCarga], registrar=print, *, strict_baseline: bool = False
) -> bool:
    """Imprime el total; el baseline histórico es advertencia salvo en modo estricto."""
    total = sum(r.filas for r in resultados)
    de_access = sum(r.filas for r in resultados if r.tabla not in EXTERNAS)
    desviadas = [r for r in resultados if r.estado != "ok"]

    registrar("")
    registrar(f"Total cargado: {total:,} filas ({len(resultados)} tablas)")
    registrar(
        f"  de Access:   {de_access:,}  —  referencia histórica (18 tablas): "
        f"{TOTAL_FILAS_ORIGEN:,}"
    )

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
        registrar(
            "  Tablas con desviación frente al baseline histórico "
            + ("— modo estricto:" if strict_baseline else "— advertencia:")
        )
        for r in desviadas:
            registrar(f"    {r.tabla}: {r.filas:,} frente a {r.esperadas:,} ({r.desviacion:+d})")
    return not desviadas or not strict_baseline
