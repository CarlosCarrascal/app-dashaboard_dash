"""Conexión PostgreSQL e identidad de snapshots del repositorio analítico."""

from __future__ import annotations

import re
from contextlib import contextmanager

import pandas as pd

from analitica import settings
from analitica.dominio.compartido import limpiar_valor as _limpio
from analitica.dominio.compartido import serializar_json as _json


class ConexionSnapshotsMixin:
    """Operaciones de conexión, snapshots y resolución de identidad física."""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or settings.postgres_dsn()
        if not self.dsn:
            raise RuntimeError("No hay DSN para persistir analytics.")

    @contextmanager
    def conexion(self):
        import psycopg

        with psycopg.connect(self.dsn) as conexion:
            yield conexion

    def snapshot(self, datos, esquema_version: str = "1.0.0") -> int:
        source_snapshot_id = getattr(datos.fuente, "source_snapshot_id", None)
        with self.conexion() as con, con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics.dataset_snapshot
                    (fuente, firma, corte_datos, esquema_version, tablas, cobertura, advertencias)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                ON CONFLICT (firma) DO UPDATE SET firma = EXCLUDED.firma
                RETURNING snapshot_id
            """,
                (
                    datos.fuente.nombre,
                    datos.fuente.firma,
                    datos.fuente.corte,
                    esquema_version,
                    _json(datos.fuente.conteos),
                    _json(
                        {
                            "fallback": datos.fuente.fallback,
                            **(
                                {"source_snapshot_id": int(source_snapshot_id)}
                                if source_snapshot_id is not None
                                else {}
                            ),
                        }
                    ),
                    _json(datos.fuente.advertencias),
                ),
            )
            return int(cur.fetchone()[0])

    def guardar_validacion_operativa(
        self,
        reporte: pd.DataFrame,
        *,
        run_id: int | None = None,
    ) -> None:
        """Persiste la paridad de los libros sin permitir publicarlos por accidente."""
        if reporte is None or reporte.empty:
            return
        columnas = [
            "archivo",
            "modelo",
            "estado",
            "sha256",
            "filas_fuente",
            "filas_motor",
            "diferencias_filas",
            "max_diferencia",
            "advertencias",
            "metadatos",
        ]
        tabla = reporte.copy()
        for columna in columnas:
            if columna not in tabla:
                tabla[columna] = None
        filas = []
        for fila in tabla[columnas].to_dict("records"):
            filas.append(
                (
                    run_id,
                    _limpio(fila["modelo"]),
                    _limpio(fila["estado"]),
                    _limpio(fila["archivo"]),
                    _limpio(fila["sha256"]),
                    int(_limpio(fila["filas_fuente"]) or 0),
                    int(_limpio(fila["filas_motor"]) or 0),
                    int(_limpio(fila["diferencias_filas"]) or 0),
                    _json(fila["max_diferencia"] or {}),
                    _json(fila["advertencias"] or []),
                    _json(fila["metadatos"] or {}),
                )
            )
        with self.conexion() as con, con.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO analytics.operational_model_validation
                    (run_id, modelo, estado, archivo, sha256, filas_fuente, filas_motor,
                     diferencias_filas, max_diferencia, advertencias, metadatos)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
                """,
                filas,
            )

    def resolver_lote_ids(self, tabla: pd.DataFrame) -> pd.DataFrame:
        """Resuelve la identidad física del lote para una corrida operativa.

        El código de lote se repite entre módulos y fundos; persistir la corrida con
        ``lote_id`` nulo mezclaría físicamente observaciones distintas. La consulta usa
        la clave completa del libro operativo y devuelve solo coincidencias únicas.
        """
        claves = tabla[["fundo", "modulo", "turno", "lote"]].dropna().astype(str).drop_duplicates()
        if claves.empty:
            return pd.DataFrame(columns=["fundo", "modulo", "turno", "lote", "lote_id"])

        # Algunos libros antiguos guardan L01B/L11B, mientras el maestro físico usa
        # L001B/L011B. La equivalencia solo se aplica a la parte numérica del código y
        # se conserva el código original en la salida para que la auditoría sea legible.
        def lote_maestro(valor: str) -> str:
            match = re.fullmatch(r"([A-Za-z]+)(\d+)([A-Za-z]*)", valor.strip())
            if not match:
                return valor.strip()
            return f"{match.group(1)}{int(match.group(2)):03d}{match.group(3)}"

        claves = claves.assign(lote_lookup=claves["lote"].map(lote_maestro))
        placeholders = ",".join(["(%s,%s,%s,%s,%s)"] * len(claves))
        valores = [valor for fila in claves.itertuples(index=False, name=None) for valor in fila]
        consulta = f"""
            SELECT v.fundo, v.modulo, v.turno, v.lote_origen AS lote, d.lote_id
            FROM dim.lote d
            JOIN (VALUES {placeholders}) AS v(fundo, modulo, turno, lote_origen, lote_lookup)
              ON v.fundo = d.fundo AND v.modulo = d.modulo
             AND v.turno = d.turno AND v.lote_lookup = d.lote
            WHERE NOT d.es_sentinel AND NOT d.es_ficticio
        """
        with self.conexion() as con, con.cursor() as cur:
            cur.execute(consulta, valores)
            columnas = [descripcion.name for descripcion in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=columnas)
