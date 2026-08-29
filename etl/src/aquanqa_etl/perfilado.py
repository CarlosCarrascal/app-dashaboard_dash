"""Perfilado reproducible de snapshots raw antes de cargar staging/core.

El perfilado nunca corrige ni descarta datos. Calcula métricas sobre un ``source_snapshot_id``
concreto, guarda el resultado en ``raw`` y deja las relaciones en estado candidata/validada;
la aprobación de una FK sigue siendo una acción explícita.
"""

from __future__ import annotations

import json
from typing import Any

from aquanqa_etl.config import Config
from aquanqa_etl.modelo import (
    MODELO_VERSION,
    RELACIONES_MODELO,
    TABLAS_MODELO,
    RelacionModelo,
    TablaModelo,
)


def _ident(name: str):
    from psycopg import sql

    return sql.Identifier(name)


def _table(name: str):
    from psycopg import sql

    return sql.SQL("raw.{}").format(_ident(name))


def _normalized_identifier(column: str, alias: str = ""):
    from psycopg import sql

    reference = sql.SQL("{}.{}").format(_ident(alias), _ident(column)) if alias else _ident(column)
    return sql.SQL("NULLIF(btrim({}), '')").format(reference)


def _nonempty_condition(columns: tuple[str, ...], alias: str = ""):
    from psycopg import sql

    expressions = [
        sql.SQL("{} IS NOT NULL").format(_normalized_identifier(column, alias))
        for column in columns
    ]
    return sql.SQL(" AND ").join(expressions) if expressions else sql.SQL("TRUE")


def _row_key(columns: tuple[str, ...], alias: str = "", *, timestamp: bool = False):
    from psycopg import sql

    expressions = []
    for column in columns:
        expression = _normalized_identifier(column, alias)
        if timestamp:
            expression = sql.SQL("left({}, 10)").format(expression)
        expressions.append(expression)
    # ROW(...) evita concatenaciones ambiguas en claves compuestas (por ejemplo A|BC y AB|C).
    return sql.SQL("ROW({})").format(sql.SQL(", ").join(expressions))


def _resolver_modelo(cur, modelo_version: str | None) -> str:
    if modelo_version:
        cur.execute(
            """
            SELECT modelo_version
            FROM raw.migracion_modelo_version
            WHERE modelo_version = %s AND estado = 'aprobado'
            """,
            (modelo_version,),
        )
    else:
        cur.execute("SELECT raw.fn_modelo_version_vigente()")
    fila = cur.fetchone()
    if not fila or not fila[0]:
        raise RuntimeError(
            "No existe un modelo semántico aprobado. Ejecuta primero `py modelo register` "
            "contra aquanqa_migracion."
        )
    return str(fila[0])


def _resolver_snapshot(cur, snapshot_id: int | None, campania: str | None) -> int:
    if snapshot_id is not None:
        cur.execute(
            """
            SELECT source_snapshot_id
            FROM raw.source_snapshot
            WHERE source_snapshot_id = %s AND tipo = 'access'
              AND (%s::text IS NULL OR campania = %s)
            """,
            (snapshot_id, campania, campania),
        )
    else:
        cur.execute(
            """
            SELECT source_snapshot_id
            FROM raw.source_snapshot
            WHERE tipo = 'access'
              AND (%s::text IS NULL OR campania = %s)
              AND estado IN ('cargado', 'aprobado', 'publicado', 'revertido')
            ORDER BY extraido_en DESC, source_snapshot_id DESC
            LIMIT 1
            """,
            (campania, campania),
        )
    fila = cur.fetchone()
    if not fila:
        raise RuntimeError("No existe el snapshot Access solicitado en raw.source_snapshot.")
    return int(fila[0])


def _tabla_disponible(cur, tabla: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'raw' AND table_name = %s
        )
        """,
        (tabla,),
    )
    return bool(cur.fetchone()[0])


def _perfil_tabla(cur, tabla: TablaModelo, snapshot_id: int) -> dict[str, Any]:
    from psycopg import sql

    columnas = _columnas_raw(cur, tabla.tabla_raw)
    cur.execute(
        sql.SQL(
            """
            SELECT count(*)::bigint,
                   count(DISTINCT source_row_hash)::bigint,
                   {columnas}
            FROM {tabla}
            WHERE source_snapshot_id = %s
            """
        ).format(
            columnas=sql.SQL(", ").join(
                sql.SQL("count(*) FILTER (WHERE {} IS NULL OR btrim({}) = '')::bigint").format(
                    _ident(columna), _ident(columna)
                )
                for columna in columnas
            )
            if columnas
            else sql.SQL("0::bigint"),
            tabla=_table(tabla.tabla_raw),
        ),
        (snapshot_id,),
    )
    fila = cur.fetchone()
    filas = int(fila[0])
    distintas = int(fila[1])
    nulos = {columna: int(fila[i + 2]) for i, columna in enumerate(columnas)}
    claves: list[dict[str, Any]] = []
    alertas: list[str] = []
    for clave in tabla.claves_candidatas:
        if not clave:
            continue
        faltantes = [columna for columna in clave if columna not in columnas]
        if faltantes:
            claves.append(
                {
                    "columnas": list(clave),
                    "estado": "no_evaluable",
                    "columnas_faltantes": faltantes,
                    "filas_con_clave": None,
                    "claves_distintas": None,
                    "grupos_duplicados": None,
                    "filas_sin_clave": None,
                }
            )
            alertas.append(
                f"clave candidata ({', '.join(clave)}) no evaluable; "
                f"faltan columnas: {', '.join(faltantes)}"
            )
            continue
        expresiones = sql.SQL(", ").join(_ident(columna) for columna in clave)
        condiciones = sql.SQL(" AND ").join(
            sql.SQL("{} IS NOT NULL AND btrim({}) <> ''").format(_ident(columna), _ident(columna))
            for columna in clave
        )
        cur.execute(
            sql.SQL(
                """
                SELECT count(*)::bigint
                FROM (
                    SELECT {expresiones}
                    FROM {tabla}
                    WHERE source_snapshot_id = %s AND {condiciones}
                    GROUP BY {expresiones}
                    HAVING count(*) > 1
                ) duplicadas
                """
            ).format(
                expresiones=expresiones,
                tabla=_table(tabla.tabla_raw),
                condiciones=condiciones,
            ),
            (snapshot_id,),
        )
        duplicados = int(cur.fetchone()[0])
        cur.execute(
            sql.SQL(
                """
                SELECT count(DISTINCT ({expresiones}))::bigint,
                       count(*) FILTER (WHERE NOT ({condiciones}))::bigint
                FROM {tabla}
                WHERE source_snapshot_id = %s
                """
            ).format(
                expresiones=expresiones,
                tabla=_table(tabla.tabla_raw),
                condiciones=condiciones,
            ),
            (snapshot_id,),
        )
        distintos_clave, filas_sin_clave = cur.fetchone()
        registro = {
            "columnas": list(clave),
            "filas_con_clave": filas - int(filas_sin_clave or 0),
            "claves_distintas": int(distintos_clave or 0),
            "grupos_duplicados": duplicados,
            "filas_sin_clave": int(filas_sin_clave or 0),
        }
        claves.append(registro)
        if duplicados:
            alertas.append(
                f"clave candidata ({', '.join(clave)}) tiene {duplicados} grupos duplicados"
            )
        if filas_sin_clave:
            alertas.append(
                f"clave candidata ({', '.join(clave)}) no aplica a {filas_sin_clave} filas"
            )
    if filas != distintas:
        alertas.append(f"{filas - distintas} filas duplicadas por source_row_hash")
    return {
        "filas_raw": filas,
        "filas_distintas": distintas,
        "filas_duplicadas": max(filas - distintas, 0),
        "columnas": nulos,
        "claves": claves,
        "estado": "con_alertas" if alertas else "perfilada",
        "detalle": "; ".join(alertas) if alertas else None,
    }


def _columnas_raw(cur, tabla: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = %s
          AND column_name NOT IN ('source_snapshot_id', 'source_row_number',
                                  'source_row_hash', 'loaded_at')
        ORDER BY ordinal_position
        """,
        (tabla,),
    )
    return [str(fila[0]) for fila in cur.fetchall()]


def _guardar_perfil(
    cur, modelo_version: str, snapshot_id: int, tabla: str, perfil: dict[str, Any]
) -> None:
    cur.execute(
        """
        INSERT INTO raw.migracion_perfil_tabla
            (modelo_version, source_snapshot_id, tabla_raw, filas_raw,
             filas_distintas, filas_duplicadas, columnas, claves, estado, detalle)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        """,
        (
            modelo_version,
            snapshot_id,
            tabla,
            perfil["filas_raw"],
            perfil["filas_distintas"],
            perfil["filas_duplicadas"],
            json.dumps(perfil["columnas"], ensure_ascii=False),
            json.dumps(perfil["claves"], ensure_ascii=False),
            perfil["estado"],
            perfil["detalle"],
        ),
    )


def _evaluar_relacion_directa(cur, relacion: RelacionModelo, snapshot_id: int) -> dict[str, Any]:
    from psycopg import sql

    timestamp = relacion.metodo == "directa_timestamp"
    parent_key = _row_key(relacion.columnas_padre, "p", timestamp=False)
    child_key = _row_key(relacion.columnas_hijo, "h", timestamp=timestamp)
    parent_condition = _nonempty_condition(relacion.columnas_padre, "p")
    child_condition = _nonempty_condition(relacion.columnas_hijo, "h")
    query = sql.SQL(
        """
        WITH padre AS (
            SELECT {parent_key} AS clave, count(*)::bigint AS n
            FROM {parent_table} p
            WHERE p.source_snapshot_id = %s AND {parent_condition}
            GROUP BY 1
        ), hijo AS (
            SELECT {child_key} AS clave
            FROM {child_table} h
            WHERE h.source_snapshot_id = %s AND {child_condition}
        ), hijo_por_clave AS (
            SELECT clave, count(*)::bigint AS n
            FROM hijo
            GROUP BY clave
        )
        SELECT
            (SELECT coalesce(sum(n), 0) FROM padre),
            (SELECT count(*) FROM padre),
            (SELECT count(*) FROM padre WHERE n > 1),
            (SELECT count(*) FROM hijo),
            (SELECT coalesce(sum(h.n), 0)
               FROM hijo_por_clave h JOIN padre p USING (clave)),
            (SELECT coalesce(sum(h.n), 0)
               FROM hijo_por_clave h LEFT JOIN padre p USING (clave)
              WHERE p.clave IS NULL),
            CASE WHEN coalesce((SELECT max(n) FROM hijo_por_clave), 0) > 1
                 THEN '1:N' ELSE '1:1' END
        """
    ).format(
        parent_key=parent_key,
        child_key=child_key,
        parent_table=_table(relacion.padre_raw),
        child_table=_table(relacion.hijo_raw),
        parent_condition=parent_condition,
        child_condition=child_condition,
    )
    cur.execute(query, (snapshot_id, snapshot_id))
    fila = cur.fetchone()
    valores = {
        "filas_padre": int(fila[0] or 0),
        "claves_padre": int(fila[1] or 0),
        "claves_padre_duplicadas": int(fila[2] or 0),
        "filas_hijo": int(fila[3] or 0),
        "filas_hijo_con_match": int(fila[4] or 0),
        "filas_hijo_huerfanas": int(fila[5] or 0),
        "cardinalidad_observada": str(fila[6]),
        "consulta": query.as_string(cur.connection),
    }
    valores["estado"] = (
        "con_huerfanos"
        if valores["filas_hijo_huerfanas"] or valores["claves_padre_duplicadas"]
        else "validada"
    )
    return valores


def perfilar_relaciones(
    cur,
    modelo_version: str,
    snapshot_id: int,
    *,
    solo: set[str] | None = None,
) -> int:
    realizadas = 0
    fuentes = {tabla.tabla_raw for tabla in TABLAS_MODELO}
    for relacion in RELACIONES_MODELO:
        if solo and relacion.padre_raw not in solo and relacion.hijo_raw not in solo:
            continue
        if relacion.padre_raw not in fuentes or relacion.hijo_raw not in fuentes:
            continue
        if not _tabla_disponible(cur, relacion.padre_raw) or not _tabla_disponible(
            cur, relacion.hijo_raw
        ):
            continue
        if relacion.metodo.startswith("directa_"):
            evidencia = _evaluar_relacion_directa(cur, relacion, snapshot_id)
        else:
            evidencia = {
                "estado": "no_evaluable",
                "filas_padre": None,
                "claves_padre": None,
                "claves_padre_duplicadas": None,
                "filas_hijo": None,
                "filas_hijo_con_match": None,
                "filas_hijo_huerfanas": None,
                "cardinalidad_observada": None,
                "consulta": None,
            }
        detalle = (
            "Relación evaluada sobre columnas normalizadas."
            if evidencia["estado"] == "validada"
            else "Requiere normalización de vocabularios y evidencia en stg.mapa_lote."
        )
        cur.execute(
            """
            INSERT INTO raw.migracion_relacion_evidencia
                (modelo_version, codigo_relacion, source_snapshot_id, estado,
                 filas_padre, claves_padre, claves_padre_duplicadas, filas_hijo,
                 filas_hijo_con_match, filas_hijo_huerfanas, cardinalidad_observada,
                 metodo, detalle, consulta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                modelo_version,
                relacion.codigo,
                snapshot_id,
                evidencia["estado"],
                evidencia["filas_padre"],
                evidencia["claves_padre"],
                evidencia["claves_padre_duplicadas"],
                evidencia["filas_hijo"],
                evidencia["filas_hijo_con_match"],
                evidencia["filas_hijo_huerfanas"],
                evidencia["cardinalidad_observada"],
                relacion.metodo,
                detalle,
                evidencia["consulta"],
            ),
        )
        realizadas += 1
    return realizadas


def perfilar_snapshot(
    config: Config,
    *,
    snapshot_id: int | None = None,
    campania: str | None = None,
    modelo_version: str | None = None,
    solo: set[str] | None = None,
) -> dict[str, Any]:
    """Calcula y guarda perfiles de tablas y relaciones para un snapshot Access."""
    if config.pg_database != "aquanqa_migracion":
        raise RuntimeError("El perfilado solo puede ejecutarse en aquanqa_migracion.")
    import psycopg

    with psycopg.connect(config.dsn, autocommit=False) as conexion:
        with conexion.cursor() as cur:
            version = _resolver_modelo(cur, modelo_version)
            snapshot = _resolver_snapshot(cur, snapshot_id, campania)
            seleccion = [tabla for tabla in TABLAS_MODELO if not solo or tabla.tabla_raw in solo]
            perfiles = []
            for tabla in seleccion:
                if not _tabla_disponible(cur, tabla.tabla_raw):
                    continue
                perfil = _perfil_tabla(cur, tabla, snapshot)
                _guardar_perfil(cur, version, snapshot, tabla.tabla_raw, perfil)
                perfiles.append({"tabla_raw": tabla.tabla_raw, **perfil})
            relaciones = perfilar_relaciones(cur, version, snapshot, solo=solo)
        conexion.commit()
    return {
        "modelo_version": version,
        "source_snapshot_id": snapshot,
        "tablas_perfiladas": len(perfiles),
        "relaciones_evaluadas": relaciones,
        "tablas_con_alertas": sum(1 for perfil in perfiles if perfil["estado"] == "con_alertas"),
        "perfiles": perfiles,
    }


def aprobar_relacion(
    config: Config,
    codigo: str,
    *,
    snapshot_id: int,
    usuario: str,
    motivo: str,
    modelo_version: str | None = None,
) -> None:
    """Aprueba manualmente una relación solo si la última evidencia es suficiente."""
    if config.pg_database != "aquanqa_migracion":
        raise RuntimeError("Las relaciones solo pueden aprobarse en aquanqa_migracion.")
    if not usuario.strip() or not motivo.strip():
        raise ValueError("La aprobación necesita usuario y motivo no vacíos.")
    import psycopg

    with psycopg.connect(config.dsn, autocommit=False) as conexion:
        with conexion.cursor() as cur:
            version = _resolver_modelo(cur, modelo_version)
            cur.execute(
                """
                SELECT estado, filas_hijo_huerfanas, claves_padre_duplicadas
                FROM raw.migracion_relacion_evidencia
                WHERE modelo_version = %s AND codigo_relacion = %s
                  AND source_snapshot_id = %s
                ORDER BY calculada_en DESC, evidencia_id DESC
                LIMIT 1
                """,
                (version, codigo, snapshot_id),
            )
            evidencia = cur.fetchone()
            if not evidencia:
                raise RuntimeError("No existe evidencia para esa relación y snapshot.")
            if evidencia[0] != "validada" or evidencia[1] or evidencia[2]:
                raise RuntimeError(
                    "La relación no puede aprobarse: la evidencia tiene huérfanos, claves "
                    "duplicadas o está pendiente de transformación."
                )
            cur.execute(
                """
                UPDATE raw.migracion_modelo_relacion
                   SET estado = 'aprobada',
                       notas = concat_ws(' | ', nullif(notas, ''),
                                         'Aprobada por ' || %s || ': ' || %s),
                       actualizado_en = now()
                 WHERE modelo_version = %s AND codigo = %s
                """,
                (usuario, motivo, version, codigo),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"No existe la relación {codigo} en el modelo {version}.")
        conexion.commit()


def mostrar_modelo() -> dict[str, Any]:
    from aquanqa_etl.modelo import hash_modelo, payload_modelo

    return {**payload_modelo(MODELO_VERSION), "hash_modelo": hash_modelo(MODELO_VERSION)}


__all__ = [
    "aprobar_relacion",
    "mostrar_modelo",
    "perfilar_snapshot",
    "perfilar_relaciones",
]
