"""Captura de una línea base de una base PostgreSQL sin modificarla."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from collections.abc import Sequence

from aquanqa_etl.config import Config, raiz_repo


def registrar_baseline(
    config: Config,
    output: str | Path | None = None,
    *,
    schemas: Sequence[str] | None = None,
) -> Path:
    """Guarda conteos exactos de tablas para comprobar no regresión.

    Sin ``schemas`` conserva el comportamiento histórico y registra todas las tablas
    de usuario. Con ``schemas=('core',)`` permite congelar una línea base de un
    esquema concreto sin mezclarla con raw/stg/qua.
    """
    import psycopg
    from psycopg import sql

    with psycopg.connect(config.dsn) as conexion, conexion.cursor() as cur:
        if schemas:
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema = ANY(%s)
                ORDER BY table_schema, table_name
                """,
                (list(schemas),),
            )
        else:
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                """
            )
        tablas = cur.fetchall()
        filas = []
        for esquema, tabla in tablas:
            cur.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(esquema), sql.Identifier(tabla)
                )
            )
            filas.append(
                {"schema": esquema, "tabla": tabla, "filas": int(cur.fetchone()[0])}
            )

        cur.execute("SELECT to_regclass('raw.v_snapshot_publicado')")
        if cur.fetchone()[0] is None:
            publicaciones = []
        else:
            cur.execute(
                """
                SELECT tipo, campania, source_snapshot_id, accion
                FROM raw.v_snapshot_publicado
                ORDER BY tipo, campania
                """
            )
            publicaciones = [
                {
                    "tipo": tipo,
                    "campania": campania,
                    "source_snapshot_id": snapshot_id,
                    "accion": accion,
                }
                for tipo, campania, snapshot_id, accion in cur.fetchall()
            ]

    if output is None:
        marca = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        ruta = raiz_repo() / "data" / "salida" / "guardas" / f"{config.pg_database}_{marca}.json"
    else:
        ruta = Path(output).expanduser()
        if not ruta.is_absolute():
            ruta = raiz_repo() / ruta
    ruta = ruta.resolve()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tipo": "postgresql_baseline",
        "alcance": list(schemas) if schemas else "todas_las_tablas_de_usuario",
        "capturado_en": dt.datetime.now(dt.UTC).isoformat(),
        "database": config.pg_database,
        "host": config.pg_host,
        "tablas": filas,
        "publicaciones_vigentes": publicaciones,
    }
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Baseline PostgreSQL: {ruta} · {len(filas)} tablas")
    return ruta
