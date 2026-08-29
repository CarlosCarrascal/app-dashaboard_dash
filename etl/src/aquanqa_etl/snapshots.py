"""Gobierno de snapshots cargados en ``raw``.

La extracción y la carga son pasos distintos de la publicación. Este módulo implementa el
gate mínimo: comprobar que cada tabla del manifiesto tiene su bloque cargado y que el número de
filas de PostgreSQL coincide con el CSV antes de cambiar la vista vigente.
"""

from __future__ import annotations

import json
from typing import Any

from aquanqa_etl.catalogo import CATALOGO_ACCESS
from aquanqa_etl.config import Config


def _campania_coincide(real: object, solicitada: str | None) -> bool:
    if solicitada is None:
        return True
    return str(real or "").strip().upper() == solicitada.strip().upper()


def _snapshot(
    cur, *, snapshot_id: int | None, tipo: str, campania: str | None
) -> tuple[Any, ...] | None:
    if snapshot_id is not None:
        cur.execute(
            """
            SELECT source_snapshot_id, tipo, campania, estado, sha256, manifiesto
            FROM raw.source_snapshot
            WHERE source_snapshot_id = %s
            """,
            (snapshot_id,),
        )
    else:
        cur.execute(
            """
            SELECT source_snapshot_id, tipo, campania, estado, sha256, manifiesto
            FROM raw.source_snapshot
            WHERE tipo = %s
              AND (%s IS NULL OR campania = %s)
            ORDER BY source_snapshot_id DESC
            LIMIT 1
            """,
            (tipo, campania, campania),
        )
    return cur.fetchone()


def _tablas_a_validar(tipo: str, manifiesto: dict[str, Any]) -> set[str]:
    if tipo == "access":
        return set((manifiesto.get("tablas") or {}).keys())
    tabla = manifiesto.get("tabla")
    return {tabla} if tabla else set()


def _validar_con_cursor(cur, snapshot_id: int, tipo: str, estado: str, sha256: str,
                        manifiesto: dict[str, Any]) -> list[str]:
    problemas: list[str] = []
    if len(sha256 or "") != 64:
        problemas.append("el snapshot no tiene una huella SHA-256 válida")
    if estado not in {"cargado", "en_validacion", "aprobado", "publicado", "revertido"}:
        problemas.append(
            f"el estado actual es {estado!r}; se requiere 'cargado' o posterior"
        )

    if not isinstance(manifiesto, dict):
        problemas.append("el manifiesto no es un objeto JSON válido")
        manifiesto = {}
    if manifiesto.get("tipo") and manifiesto.get("tipo") != tipo:
        problemas.append(
            f"el manifiesto declara tipo={manifiesto.get('tipo')!r}, no {tipo!r}"
        )
    if manifiesto.get("sha256") and manifiesto.get("sha256") != sha256:
        problemas.append("la huella del manifiesto no coincide con raw.source_snapshot")

    esperadas = manifiesto.get("tablas") or {}
    tablas = _tablas_a_validar(tipo, manifiesto)
    if tipo == "access" and (
        manifiesto.get("snapshot_completo") is not True
        or manifiesto.get("alcance") != "completo"
    ):
        problemas.append(
            "el manifiesto Access es parcial y no puede publicarse como snapshot completo"
        )
    if tipo == "access":
        catalogo = {tabla.destino for tabla in CATALOGO_ACCESS}
        faltantes_catalogo = sorted(catalogo - tablas)
        if faltantes_catalogo:
            problemas.append(
                "faltan tablas del catálogo Access: " + ", ".join(faltantes_catalogo)
            )

    for tabla in sorted(tablas):
        detalle = esperadas.get(tabla) or {}
        filas_manifest = detalle.get("filas")
        cur.execute(
            """
            SELECT filas_csv, sha256_csv, schema_hash, estado
            FROM raw.source_table_snapshot
            WHERE source_snapshot_id = %s AND tabla_destino = %s
            """,
            (snapshot_id, tabla),
        )
        control = cur.fetchone()
        if not control:
            problemas.append(f"raw.{tabla}: no tiene control de tabla para el snapshot")
            continue
        if control[3] != "cargado":
            problemas.append(f"raw.{tabla}: estado de control {control[3]!r}")
        if filas_manifest is not None and int(control[0]) != int(filas_manifest):
            problemas.append(
                f"raw.{tabla}: control={control[0]} y manifiesto={filas_manifest}"
            )
        detalle_hash_csv = detalle.get("sha256_csv")
        if detalle_hash_csv and control[1] != detalle_hash_csv:
            problemas.append(f"raw.{tabla}: hash CSV del control y manifiesto no coinciden")
        detalle_schema_hash = detalle.get("schema_hash")
        if detalle_schema_hash and control[2] != detalle_schema_hash:
            problemas.append(
                f"raw.{tabla}: schema_hash del control y manifiesto no coinciden"
            )
        # Tabla viene del catálogo/manifiesto generado por el ETL, no de entrada libre.
        from psycopg import sql

        cur.execute(
            sql.SQL("SELECT count(*) FROM raw.{} WHERE source_snapshot_id = %s").format(
                sql.Identifier(tabla)
            ),
            (snapshot_id,),
        )
        filas_raw = int(cur.fetchone()[0])
        if filas_manifest is not None and filas_raw != int(filas_manifest):
            problemas.append(
                f"raw.{tabla}: filas cargadas={filas_raw} y manifiesto={filas_manifest}"
            )
    if tipo == "access":
        if manifiesto.get("schema_hash") is not None and not str(
            manifiesto.get("schema_hash")
        ).strip():
            problemas.append("el manifiesto Access declara un schema_hash vacío")
        cur.execute(
            """
            SELECT count(*)
            FROM raw.source_table_snapshot
            WHERE source_snapshot_id = %s
            """,
            (snapshot_id,),
        )
        controles = int(cur.fetchone()[0])
        if controles != len(tablas):
            problemas.append(
                f"el snapshot tiene {controles} controles de tabla y se esperaban {len(tablas)}"
            )
        if manifiesto.get("catalogo_version") is not None:
            cur.execute(
                """
                SELECT count(*)
                FROM raw.access_schema_catalog
                WHERE source_snapshot_id = %s
                """,
                (snapshot_id,),
            )
            catalogadas = int(cur.fetchone()[0])
            if catalogadas != len(tablas):
                problemas.append(
                    f"el catálogo técnico tiene {catalogadas} tablas y se esperaban {len(tablas)}"
                )
        consultas = manifiesto.get("consultas") or []
        if consultas:
            cur.execute(
                """
                SELECT count(*)
                FROM raw.access_query_catalog
                WHERE source_snapshot_id = %s
                """,
                (snapshot_id,),
            )
            catalogadas = int(cur.fetchone()[0])
            if catalogadas != len(consultas):
                problemas.append(
                    f"el catálogo de consultas tiene {catalogadas} y el manifiesto {len(consultas)}"
                )
        relaciones = manifiesto.get("relaciones") or []
        if relaciones:
            cur.execute(
                """
                SELECT count(*)
                FROM raw.access_relation_catalog
                WHERE source_snapshot_id = %s
                """,
                (snapshot_id,),
            )
            catalogadas = int(cur.fetchone()[0])
            if catalogadas != len(relaciones):
                problemas.append(
                    "el catálogo de relaciones tiene "
                    f"{catalogadas} y el manifiesto {len(relaciones)}"
                )
    return problemas


def validar_snapshot(
    config: Config,
    *,
    snapshot_id: int | None = None,
    tipo: str = "access",
    campania: str | None = None,
) -> list[str]:
    """Devuelve problemas; una lista vacía significa que puede promoverse."""
    import psycopg

    with psycopg.connect(config.dsn) as conexion, conexion.cursor() as cur:
        fila = _snapshot(cur, snapshot_id=snapshot_id, tipo=tipo, campania=campania)
        if not fila:
            return [
                "no existe el snapshot solicitado"
                if snapshot_id is not None
                else f"no existe un snapshot tipo={tipo!r} campaña={campania!r}"
            ]
        sid, tipo_real, campania_real, estado, sha256, manifiesto = fila
        if tipo_real != tipo:
            return [f"el snapshot {sid} es tipo {tipo_real!r}, no {tipo!r}"]
        if not _campania_coincide(campania_real, campania):
            return [
                f"el snapshot {sid} pertenece a la campaña {campania_real!r}, "
                f"no a {campania!r}"
            ]
        try:
            manifiesto_dict = (
                manifiesto if isinstance(manifiesto, dict) else json.loads(manifiesto)
            )
        except (TypeError, json.JSONDecodeError):
            manifiesto_dict = {}
        estado_original = str(estado)
        if estado_original != "publicado":
            cur.execute(
                """
                UPDATE raw.source_snapshot
                SET estado = 'en_validacion', actualizado_en = now()
                WHERE source_snapshot_id = %s
                """,
                (sid,),
            )
        problemas = _validar_con_cursor(
            cur, int(sid), tipo_real, str(estado), str(sha256), manifiesto_dict
        )
        if estado_original != "publicado":
            nuevo_estado = "en_revision" if problemas else "aprobado"
            cur.execute(
                """
                UPDATE raw.source_snapshot
                SET estado = %s, actualizado_en = now()
                WHERE source_snapshot_id = %s
                """,
                (nuevo_estado, sid),
            )
        return problemas


def promover_snapshot(
    config: Config,
    *,
    snapshot_id: int | None = None,
    tipo: str = "access",
    campania: str | None = None,
    autorizado_por: str = "etl",
    motivo: str | None = None,
) -> int:
    """Publica un snapshot validado y conserva el anterior para rollback."""
    import psycopg

    problemas = validar_snapshot(
        config, snapshot_id=snapshot_id, tipo=tipo, campania=campania
    )
    if problemas:
        raise RuntimeError("No se puede promover el snapshot:\n  " + "\n  ".join(problemas))

    with psycopg.connect(config.dsn, autocommit=False) as conexion:
        with conexion.cursor() as cur:
            fila = _snapshot(
                cur, snapshot_id=snapshot_id, tipo=tipo, campania=campania
            )
            if not fila:
                raise RuntimeError("El snapshot desapareció antes de promoverlo.")
            sid, tipo_real, campania_real, _, _, _ = fila
            if tipo_real != tipo or not _campania_coincide(campania_real, campania):
                raise RuntimeError(
                    "El snapshot seleccionado no coincide con el tipo o campaña solicitados."
                )
            cur.execute(
                "SELECT estado FROM raw.source_snapshot WHERE source_snapshot_id = %s",
                (sid,),
            )
            estado = str(cur.fetchone()[0])
            if estado not in {"aprobado", "publicado"}:
                raise RuntimeError(
                    f"El snapshot {sid} quedó en estado {estado!r}; "
                    "solo se puede promover uno aprobado."
                )
            cur.execute(
                """
                SELECT source_snapshot_id
                FROM raw.v_snapshot_publicado
                WHERE tipo = %s AND campania = %s
                """,
                (tipo_real, campania_real),
            )
            anterior = cur.fetchone()
            anterior_id = int(anterior[0]) if anterior and anterior[0] is not None else None
            cur.execute(
                """
                INSERT INTO raw.snapshot_publication
                    (tipo, campania, source_snapshot_id, snapshot_anterior_id,
                     accion, motivo, autorizado_por)
                VALUES (%s, %s, %s, %s, 'publicar', %s, %s)
                """,
                (tipo_real, campania_real, sid, anterior_id, motivo, autorizado_por),
            )
            cur.execute(
                """
                UPDATE raw.source_snapshot
                SET estado = 'publicado', reemplaza_snapshot_id = %s, actualizado_en = now()
                WHERE source_snapshot_id = %s
                """,
                (anterior_id, sid),
            )
        conexion.commit()
    return int(sid)


def rollback_snapshot(
    config: Config,
    *,
    snapshot_id: int | None = None,
    tipo: str = "access",
    campania: str | None = None,
    autorizado_por: str = "etl",
    motivo: str | None = None,
) -> int | None:
    """Registra rollback hacia ``snapshot_id`` sin borrar publicaciones anteriores."""
    import psycopg

    with psycopg.connect(config.dsn, autocommit=False) as conexion:
        with conexion.cursor() as cur:
            cur.execute(
                """
                SELECT tipo, campania, source_snapshot_id, accion
                FROM raw.v_snapshot_publicado
                WHERE tipo = %s AND (%s::text IS NULL OR campania = %s)
                """,
                (tipo, campania, campania),
            )
            actual = cur.fetchone()
            if not actual or actual[2] is None:
                raise RuntimeError("No hay un snapshot publicado para revertir.")
            tipo_real, campania_real, actual_id, accion = actual
            actual_id = int(actual_id)
            if snapshot_id is None:
                cur.execute(
                    """
                    SELECT source_snapshot_id
                    FROM raw.snapshot_publication
                    WHERE tipo = %s AND campania = %s
                      AND accion = 'publicar' AND source_snapshot_id <> %s
                    ORDER BY publicado_en DESC, publication_id DESC
                    LIMIT 1
                    """,
                    (tipo_real, campania_real, actual_id),
                )
                objetivo = cur.fetchone()
                if not objetivo:
                    raise RuntimeError("No se encontró un snapshot anterior para rollback.")
                snapshot_id = int(objetivo[0])
            else:
                cur.execute(
                    """
                    SELECT 1 FROM raw.source_snapshot
                    WHERE source_snapshot_id = %s AND tipo = %s AND campania = %s
                    """,
                    (snapshot_id, tipo_real, campania_real),
                )
                if not cur.fetchone():
                    raise RuntimeError(
                        "El snapshot destino del rollback no existe o es de otro tipo."
                    )

            cur.execute(
                """
                INSERT INTO raw.snapshot_publication
                    (tipo, campania, source_snapshot_id, snapshot_anterior_id,
                     accion, motivo, autorizado_por)
                VALUES (%s, %s, %s, %s, 'rollback', %s, %s)
                """,
                (tipo_real, campania_real, actual_id, snapshot_id, motivo, autorizado_por),
            )
            cur.execute(
                """
                UPDATE raw.source_snapshot
                SET estado = 'revertido', actualizado_en = now()
                WHERE source_snapshot_id = %s
                """,
                (actual_id,),
            )
            cur.execute(
                """
                UPDATE raw.source_snapshot
                SET estado = 'publicado', actualizado_en = now()
                WHERE source_snapshot_id = %s
                """,
                (snapshot_id,),
            )
        conexion.commit()
    return snapshot_id
