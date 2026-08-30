"""Persistencia de runs, predicciones y cierres nowcast."""

from __future__ import annotations

import csv
import io
import json

import numpy as np
import pandas as pd

from analitica.dominio.compartido import limpiar_valor as _limpio
from analitica.dominio.compartido import serializar_json as _json
from analitica.infraestructura import commit_actual


class RunsPrediccionesMixin:
    """Operaciones de corridas y sus salidas predictivas."""

    def crear_run(
        self, snapshot_id: int, tipo: str, configuracion: dict, mlflow_run_id: str | None = None
    ) -> int:
        with self.conexion() as con, con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics.forecast_run
                    (snapshot_id, mlflow_run_id, tipo, estado, codigo_commit, configuracion)
                VALUES (%s, %s, %s, 'running', %s, %s::jsonb) RETURNING run_id
            """,
                (snapshot_id, mlflow_run_id, tipo, commit_actual(), _json(configuracion)),
            )
            return int(cur.fetchone()[0])

    def finalizar_run(self, run_id: int, estado: str = "succeeded", error: str | None = None):
        with self.conexion() as con, con.cursor() as cur:
            cur.execute(
                "UPDATE analytics.forecast_run SET estado=%s, fin=now(), error=%s WHERE run_id=%s",
                (estado, error, run_id),
            )

    def guardar_predicciones(self, run_id: int, tabla: pd.DataFrame):
        columnas = [
            "modelo",
            "version_modelo",
            "campania",
            "empresa",
            "fundo",
            "modulo",
            "lote",
            "lote_id",
            "fecha_emision",
            "fecha_objetivo",
            "horizonte_semanas",
            "banda_horizonte",
            "version_fuente",
            "p10_kg",
            "p50_kg",
            "p90_kg",
            "real_kg",
            "plantas",
            "frutos_por_planta",
            "peso_baya_g",
            "confianza",
            "origen_emision",
            "tipo_prediccion",
            "es_replay_ciego",
            "es_curva_stitched",
            "estado_evaluacion",
        ]
        t = tabla.copy()
        for columna in columnas:
            if columna not in t:
                if columna == "origen_emision" and "fecha_emision" in t:
                    t[columna] = t.fecha_emision
                elif columna == "tipo_prediccion":
                    replay = t.get("es_replay_ciego", False)
                    t[columna] = np.where(replay, "replay", "operativa")
                elif columna == "es_replay_ciego" or columna == "es_curva_stitched":
                    t[columna] = False
                elif columna == "estado_evaluacion":
                    t[columna] = np.where(
                        t.get("real_kg", pd.Series(index=t.index)).notna(),
                        "evaluada",
                        "pendiente",
                    )
                else:
                    t[columna] = None
        # Al concatenar R09 con challengers, estas columnas pueden existir pero contener
        # NaN en las filas de la emisión publicada. El contrato SQL es NOT NULL: completar
        # explícitamente evita que la persistencia dependa del orden de los modelos.
        t["es_replay_ciego"] = t["es_replay_ciego"].astype("boolean").fillna(False).astype(bool)
        t["es_curva_stitched"] = t["es_curva_stitched"].astype("boolean").fillna(False).astype(bool)
        if "tipo_prediccion" in t:
            tipo_default = pd.Series(
                np.where(t["es_replay_ciego"], "replay", "operativa"), index=t.index
            )
            t["tipo_prediccion"] = t["tipo_prediccion"].where(
                t["tipo_prediccion"].notna(), tipo_default
            )
        if "estado_evaluacion" in t:
            estado_default = pd.Series(
                np.where(t["real_kg"].notna(), "evaluada", "pendiente"), index=t.index
            )
            t["estado_evaluacion"] = t["estado_evaluacion"].where(
                t["estado_evaluacion"].notna(), estado_default
            )
        extras = [c for c in t if c not in {*columnas, "componentes"}]
        if "componentes" not in t:
            t["componentes"] = [{} for _ in range(len(t))]
        # ``Series(fila._asdict())`` dentro del bucle era el coste dominante al persistir
        # corridas grandes: creaba un objeto pandas por cada lote-semana. COPY ya evita
        # los INSERT individuales; aquí conservamos COPY y eliminamos esa asignación
        # intermedia usando tuplas posicionales y un mapa de índices estable.
        orden = [*columnas, "componentes", *extras]
        posiciones = {columna: indice for indice, columna in enumerate(orden)}
        copy_sql = """
            COPY analytics.prediction
                (run_id, modelo, version_modelo, campania, empresa, fundo, modulo, lote, lote_id,
                 fecha_emision, fecha_objetivo, horizonte_semanas, banda_horizonte,
                 version_fuente, p10_kg, p50_kg, p90_kg, real_kg, plantas,
                 frutos_por_planta, peso_baya_g, confianza, origen_emision,
                 tipo_prediccion, es_replay_ciego, es_curva_stitched,
                 estado_evaluacion, componentes)
            FROM STDIN WITH (FORMAT CSV, NULL '')
        """
        with (
            self.conexion() as con,
            con.cursor() as cur,
            cur.copy(copy_sql) as copia,
        ):
            # ``write_row`` adapta cada celda mediante una llamada de psycopg. Para
            # corridas históricas de cientos de miles de lote-semana el coste de esas
            # llamadas domina a COPY. CSV por bloques mantiene la misma transacción y
            # el mismo esquema, pero reduce la comunicación Python↔driver a unos
            # cientos de bloques.
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            for fila in t[orden].itertuples(index=False, name=None):
                base_componentes = fila[posiciones["componentes"]]
                if isinstance(base_componentes, str):
                    try:
                        base_componentes = json.loads(base_componentes)
                    except json.JSONDecodeError:
                        base_componentes = {"detalle_original": base_componentes}
                componentes = dict(base_componentes) if isinstance(base_componentes, dict) else {}
                for columna in extras:
                    valor = _limpio(fila[posiciones[columna]])
                    if valor is not None:
                        componentes[columna] = valor
                writer.writerow(
                    [
                        run_id,
                        *[_limpio(fila[posiciones[c]]) for c in columnas],
                        _json(componentes),
                    ]
                )
                if buffer.tell() >= 1_000_000:
                    copia.write(buffer.getvalue())
                    buffer.seek(0)
                    buffer.truncate(0)
            if buffer.tell():
                copia.write(buffer.getvalue())

    def guardar_nowcast_semanal(self, run_id: int, tabla: pd.DataFrame) -> None:
        """Persiste cierres intra-semanales sin confundirlos con forecast h1.

        El contrato es una fila por empresa/fundo y semana. ``R09`` se guarda
        únicamente como columna comparativa; nunca participa en ``p50_kg``.
        """

        if tabla is None or tabla.empty:
            return
        columnas = [
            "modelo",
            "version_modelo",
            "campania",
            "semana_inicio",
            "semana_cierre",
            "fecha_corte",
            "fecha_emision",
            "fundo",
            "kg_lun_mar",
            "p50_kg",
            "real_kg",
            "macro_kg",
            "r09_presemana_kg",
            "r09_misma_semana_kg",
            "estado_evaluacion",
            "componentes",
        ]
        copia = tabla.copy()
        for columna in columnas:
            if columna not in copia:
                if columna == "estado_evaluacion":
                    copia[columna] = np.where(
                        copia.get("real_kg", pd.Series(index=copia.index)).notna(),
                        "evaluado",
                        "pendiente",
                    )
                elif columna == "componentes":
                    copia[columna] = [{} for _ in range(len(copia))]
                else:
                    copia[columna] = None
        filas = []
        for fila in copia[columnas].itertuples(index=False, name=None):
            valores = list(fila)
            valores[-1] = _json(valores[-1] if isinstance(valores[-1], (dict, list)) else {})
            filas.append((run_id, *(_limpio(valor) for valor in valores)))
        with self.conexion() as con, con.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO analytics.weekly_nowcast
                    (run_id, modelo, version_modelo, campania, semana_inicio,
                     semana_cierre, fecha_corte, fecha_emision, fundo,
                     kg_lun_mar, p50_kg, real_kg, macro_kg,
                     r09_presemana_kg, r09_misma_semana_kg,
                     estado_evaluacion, componentes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                """,
                filas,
            )
