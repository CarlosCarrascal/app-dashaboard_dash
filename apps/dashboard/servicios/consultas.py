"""Primitivas de lectura PostgreSQL compartidas por los servicios del dashboard."""

from __future__ import annotations

import pandas as pd


def consulta(conexion, sql: str, parametros=None) -> pd.DataFrame:
    """Ejecuta una consulta de solo lectura y conserva sus nombres de columna."""
    with conexion.cursor() as cursor:
        if parametros is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, parametros)
        columnas = [col.name for col in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=columnas)


def consulta_si_existe(
    conexion, relacion: str, sql: str, parametros=None
) -> pd.DataFrame:
    """Devuelve vacío durante una migración si todavía no existe la relación."""
    with conexion.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (relacion,))
        if cursor.fetchone()[0] is None:
            return pd.DataFrame()
    return consulta(conexion, sql, parametros)
